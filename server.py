import base64
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Literal, Optional, TypedDict

# Fix Windows console encoding for Chinese characters
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import create_access_token, get_current_user, hash_password, verify_password
from database import User, get_db, init_db
from services.appearance_service import AppearanceGenerationService

logger = logging.getLogger(__name__)

# Ensure uploads directory exists before mounting
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Appearance Fusion API", version="0.1.0")

# Initialise DB tables on startup (idempotent — safe to call every run)
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded images as static files at /uploads/<filename>
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

service = AppearanceGenerationService()


# ---------------------------------------------------------------------------
# In-memory try-on job store
# ---------------------------------------------------------------------------

class TryOnJob(TypedDict):
    status: Literal["pending", "completed", "failed"]
    person_image_url: str
    garment_image_url: str
    result: Optional[Dict[str, Any]]
    error: Optional[Literal["content_violation", "api_error"]]
    detail: Optional[str]


_jobs: Dict[str, TryOnJob] = {}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class AuthRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/register", status_code=201)
async def register(body: AuthRequest, db: Session = Depends(get_db)):
    """
    Create a new user account and return a JWT so the client is logged in immediately.
    Returns 409 if the username is already taken.
    """
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=409, detail="Username already taken.")

    user = User(username=body.username, hashed_password=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user_id=user.id, username=user.username)
    logger.info("New user registered: %s (id=%s)", user.username, user.id)
    return {"access_token": token, "token_type": "bearer", "username": user.username}


@app.post("/api/auth/login")
async def login(body: AuthRequest, db: Session = Depends(get_db)):
    """
    Verify credentials and return a JWT.
    Returns 401 on wrong username or password (intentionally vague for security).
    """
    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    token = create_access_token(user_id=user.id, username=user.username)
    logger.info("User logged in: %s (id=%s)", user.username, user.id)
    return {"access_token": token, "token_type": "bearer", "username": user.username}


@app.get("/api/auth/me")
async def me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile (useful for token validation)."""
    return {"user_id": current_user.id, "username": current_user.username}


# ---------------------------------------------------------------------------
# Wardrobe Upload
# ---------------------------------------------------------------------------

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/heic"}


@app.post("/api/wardrobe/upload")
async def wardrobe_upload(
    image: UploadFile = File(...),
    label: str = Form(None),
):
    """
    Accept a garment image from the Expo app (multipart/form-data),
    save it to the local uploads/ directory, and return an accessible URL.
    """
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{image.content_type}'. Must be an image.",
        )

    original_name = Path(image.filename or "upload.jpg").name
    file_id = uuid.uuid4().hex
    save_name = f"{file_id}_{original_name}"
    save_path = UPLOADS_DIR / save_name

    contents = await image.read()
    save_path.write_bytes(contents)

    logger.info("Saved wardrobe upload: %s (%d bytes)", save_path, len(contents))

    return {
        "file_id": file_id,
        "filename": save_name,
        "label": label,
        "size_bytes": len(contents),
        "image_url": f"/uploads/{save_name}",
    }


@app.get("/api/wardrobe/uploads")
async def list_uploads():
    """Return a list of all uploaded garment images with their accessible URLs."""
    files = [
        {"filename": f.name, "image_url": f"/uploads/{f.name}", "size_bytes": f.stat().st_size}
        for f in sorted(UPLOADS_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
        if f.is_file()
    ]
    return {"count": len(files), "files": files}


# ---------------------------------------------------------------------------
# Virtual Try-On  (Async Job Queue)
# ---------------------------------------------------------------------------

TRYON_PROMPT = (
    "Virtual Try-On: Generate a single, realistic, high-quality photo of the person from the "
    "first image wearing the exact garment shown in the second image. "
    "Rules: (1) Preserve the person's body shape and pose exactly — the photo is headless for privacy. "
    "(2) Transfer the garment faithfully — keep its color, texture, and fit. "
    "(3) Use natural outdoor lighting, photorealistic quality, no compositing artifacts."
)

# Phrases that appear in Nano Banana content-violation responses
_CONTENT_VIOLATION_SIGNALS = [
    "content policy",
    "safety",
    "violated",
    "inappropriate",
    "blocked",
    "nsfw",
    "cannot generate",
    "can't generate",
    "unable to generate",
]


def _is_content_violation(text: str) -> bool:
    lowered = text.lower()
    return any(signal in lowered for signal in _CONTENT_VIOLATION_SIGNALS)


def _run_tryon_job(job_id: str, person_bytes: bytes, garment_bytes: bytes, garment_mime: str) -> None:
    """
    Background task: call Nano Banana and update the job store.
    Runs in a thread (FastAPI BackgroundTasks uses a thread pool for sync functions).
    """
    garment_data_uri = f"data:{garment_mime};base64,{base64.b64encode(garment_bytes).decode()}"
    try:
        result = service.nano_client.blend_user_with_diagram(
            user_image=person_bytes,
            diagram_image_data=garment_data_uri,
            promo_prompt=TRYON_PROMPT,
        )

        # Nano Banana may return a text-only response (no image) on content violation
        if result is None:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = "api_error"
            _jobs[job_id]["detail"] = "Nano Banana returned no image."
            logger.warning("Try-on job %s: no image returned", job_id)
            return

        # Check if result payload is a text-only content violation
        image_url = result.get("image_url")
        image_data = result.get("image_data")
        if not image_url and not image_data:
            raw_text = str(result)
            if _is_content_violation(raw_text):
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = "content_violation"
                _jobs[job_id]["detail"] = "Image blocked by content policy. Ensure the base photo is headless."
                logger.warning("Try-on job %s: content violation", job_id)
                return
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = "api_error"
            _jobs[job_id]["detail"] = "Nano Banana returned no image data."
            return

        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["result"] = result
        logger.info("Try-on job %s completed", job_id)

    except Exception as exc:
        err_msg = str(exc)
        if _is_content_violation(err_msg):
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = "content_violation"
            _jobs[job_id]["detail"] = "Image blocked by content policy. Ensure the base photo is headless."
        else:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = "api_error"
            _jobs[job_id]["detail"] = err_msg
        logger.exception("Try-on job %s failed: %s", job_id, exc)


@app.post("/api/try-on/generate", status_code=202)
async def try_on_generate(
    background_tasks: BackgroundTasks,
    person_image: UploadFile = File(..., description="Headless full-body photo of the person"),
    garment_image: UploadFile = File(..., description="Photo of the garment to try on"),
):
    """
    Accept a headless person photo and a garment photo.
    Saves both, schedules a background Nano Banana call, and immediately returns
    a job_id so the client can poll /api/try-on/status/{job_id}.
    """
    for upload, field in [(person_image, "person_image"), (garment_image, "garment_image")]:
        if upload.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=415,
                detail=f"'{field}' has unsupported type '{upload.content_type}'. Must be an image.",
            )

    person_bytes = await person_image.read()
    garment_bytes = await garment_image.read()

    job_id = uuid.uuid4().hex
    person_name = f"{job_id}_person_{Path(person_image.filename or 'person.jpg').name}"
    garment_name = f"{job_id}_garment_{Path(garment_image.filename or 'garment.jpg').name}"
    (UPLOADS_DIR / person_name).write_bytes(person_bytes)
    (UPLOADS_DIR / garment_name).write_bytes(garment_bytes)

    # Register the job immediately
    _jobs[job_id] = TryOnJob(
        status="pending",
        person_image_url=f"/uploads/{person_name}",
        garment_image_url=f"/uploads/{garment_name}",
        result=None,
        error=None,
        detail=None,
    )

    garment_mime = garment_image.content_type or "image/jpeg"
    background_tasks.add_task(_run_tryon_job, job_id, person_bytes, garment_bytes, garment_mime)

    logger.info("Try-on job %s queued: person=%s garment=%s", job_id, person_name, garment_name)

    return {
        "job_id": job_id,
        "status": "pending",
        "person_image_url": f"/uploads/{person_name}",
        "garment_image_url": f"/uploads/{garment_name}",
        "poll_url": f"/api/try-on/status/{job_id}",
    }


@app.get("/api/try-on/status/{job_id}")
async def try_on_status(job_id: str):
    """
    Poll the status of a try-on job.

    Possible responses:
      - {status: "pending"}
      - {status: "completed", result: {...}, person_image_url, garment_image_url}
      - {status: "failed", error: "content_violation"|"api_error", detail: "..."}
    """
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    if job["status"] == "pending":
        return {"job_id": job_id, "status": "pending"}

    if job["status"] == "completed":
        return {
            "job_id": job_id,
            "status": "completed",
            "person_image_url": job["person_image_url"],
            "garment_image_url": job["garment_image_url"],
            "result": job["result"],
        }

    # failed
    return {
        "job_id": job_id,
        "status": "failed",
        "error": job["error"],
        "detail": job["detail"],
    }


# ---------------------------------------------------------------------------
# Legacy plan/visuals endpoints (kept for backwards compat during transition)
# ---------------------------------------------------------------------------

@app.post("/api/generate-plan")
async def generate_plan(
    requirements: str = Form(...),
    style: str = Form(None),
    user_prompt: str = Form(None),
    budget: int = Form(500),
    location: str = Form("Hong Kong"),
    gender: str = Form("Men"),
    age: str = Form("Young Adult (20-35)")
):
    try:
        payload = service.generate_plan_only(
            requirements=requirements,
            selected_style=style,
            user_prompt=user_prompt,
            budget=budget,
            location=location,
            gender=gender,
            age=age
        )
        return payload
    except Exception as exc:
        logger.exception("Failed to generate plan")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/generate-visuals")
async def generate_visuals(
    image: UploadFile = File(...),
    internal_context: str = Form(...)
):
    try:
        image_bytes = await image.read()
        payload = service.generate_visuals_only(
            user_image_bytes=image_bytes,
            internal_context=internal_context
        )
        return payload
    except Exception as exc:
        logger.exception("Failed to generate visuals")
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
