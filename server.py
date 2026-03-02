import base64
import io
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

from PIL import Image

# rembg is imported lazily inside _remove_background to avoid slowing startup
# if the model weights have not yet been downloaded.

from auth import create_access_token, get_current_user, hash_password, verify_password
from database import Garment, SessionLocal, User, get_db, init_db
from apis.nano_banana_client import NanoBananaClient

logger = logging.getLogger(__name__)

# Ensure uploads and thumbnails directories exist before mounting
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)
THUMBNAILS_DIR = Path("thumbnails")
THUMBNAILS_DIR.mkdir(exist_ok=True)

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
# Serve thumbnails at /thumbnails/<filename>
app.mount("/thumbnails", StaticFiles(directory=str(THUMBNAILS_DIR)), name="thumbnails")

nano_client = NanoBananaClient()


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
THUMBNAIL_MAX_SIZE = (300, 400)  # width × height


def _make_thumbnail(image_bytes: bytes, dest_path: Path) -> None:
    """Generate a 300×400 max JPEG thumbnail, preserving aspect ratio."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail(THUMBNAIL_MAX_SIZE, Image.LANCZOS)
    img.save(dest_path, format="JPEG", quality=85, optimize=True)


def _remove_background(image_bytes: bytes) -> Optional[bytes]:
    """Remove background using rembg. Returns PNG bytes, or None on failure."""
    try:
        from rembg import remove as rembg_remove  # lazy import — model download on first call
        return rembg_remove(image_bytes)
    except Exception:
        logger.exception("Background removal failed — skipping")
        return None


def _auto_tag_garment(garment_id: int, image_bytes: bytes) -> None:
    """
    Background task: call Gemini Vision to extract category/color/material
    and write them back to the Garment row.
    Uses its own DB session — safe to run in a background thread.
    """
    import json
    import google.generativeai as genai  # bundled with langchain-google-genai

    try:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = (
            "Analyze this clothing item image. "
            "Reply with ONLY a raw JSON object (no markdown, no code fences):\n"
            '{"category": "<Top|Bottom|Outerwear|Dress|Shoes|Accessory>", '
            '"color": "<main color name, e.g. Black, Navy Blue, White>", '
            '"material": "<fabric type, e.g. Cotton|Denim|Polyester|Wool|Leather|Synthetic>"}'
        )
        img_part = {"mime_type": "image/jpeg", "data": image_bytes}
        response = model.generate_content([prompt, img_part])

        raw = response.text.strip()
        # Strip any accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        tags = json.loads(raw)

        db = SessionLocal()
        try:
            g = db.get(Garment, garment_id)
            if g:
                g.category = tags.get("category")
                g.color = tags.get("color")
                g.material = tags.get("material")
                db.commit()
                logger.info(
                    "Garment %s tagged: category=%s color=%s material=%s",
                    garment_id, g.category, g.color, g.material,
                )
        finally:
            db.close()

    except Exception:
        logger.exception("Auto-tagging failed for garment %s — skipping", garment_id)


@app.post("/api/wardrobe/upload", status_code=201)
async def wardrobe_upload(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    label: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Accept a garment image (auth required).
    Saves the original to uploads/, generates a thumbnail in thumbnails/,
    creates a Garment DB record, and returns URLs + garment_id.
    """
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{image.content_type}'. Must be an image.",
        )

    contents = await image.read()
    file_id = uuid.uuid4().hex
    original_name = Path(image.filename or "upload.jpg").name
    save_name = f"{file_id}_{original_name}"

    # Save original
    image_path = UPLOADS_DIR / save_name
    image_path.write_bytes(contents)

    # Generate thumbnail
    thumb_name = f"thumb_{file_id}.jpg"
    thumb_path = THUMBNAILS_DIR / thumb_name
    try:
        _make_thumbnail(contents, thumb_path)
    except Exception:
        logger.exception("Thumbnail generation failed for %s — skipping", save_name)
        thumb_name = None

    # Remove background (produces transparent PNG)
    nobg_name = None
    nobg_bytes = _remove_background(contents)
    if nobg_bytes is not None:
        nobg_name = f"nobg_{file_id}.png"
        (UPLOADS_DIR / nobg_name).write_bytes(nobg_bytes)

    # Persist Garment record
    garment = Garment(
        user_id=current_user.id,
        image_path=str(image_path),
        thumbnail_path=str(thumb_path) if thumb_name else None,
        nobg_path=str(UPLOADS_DIR / nobg_name) if nobg_name else None,
        label=label,
    )
    db.add(garment)
    db.commit()
    db.refresh(garment)

    # Schedule background auto-tagging (non-blocking)
    background_tasks.add_task(_auto_tag_garment, garment.id, contents)

    logger.info(
        "Garment %s saved for user %s: %s (thumb: %s, nobg: %s)",
        garment.id, current_user.username, save_name, thumb_name, nobg_name,
    )

    return {
        "garment_id": garment.id,
        "image_url": f"/uploads/{save_name}",
        "thumbnail_url": f"/thumbnails/{thumb_name}" if thumb_name else None,
        "nobg_url": f"/uploads/{nobg_name}" if nobg_name else None,
        "label": label,
        "size_bytes": len(contents),
    }


@app.get("/api/wardrobe/garments")
async def list_garments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all garments belonging to the authenticated user, newest first."""
    garments = (
        db.query(Garment)
        .filter(Garment.user_id == current_user.id)
        .order_by(Garment.created_at.desc())
        .all()
    )
    return {
        "count": len(garments),
        "garments": [
            {
                "id": g.id,
                "image_url": f"/uploads/{Path(g.image_path).name}",
                "thumbnail_url": f"/thumbnails/{Path(g.thumbnail_path).name}" if g.thumbnail_path else None,
                "nobg_url": f"/uploads/{Path(g.nobg_path).name}" if g.nobg_path else None,
                "label": g.label,
                "category": g.category,
                "color": g.color,
                "material": g.material,
                "created_at": g.created_at.isoformat(),
            }
            for g in garments
        ],
    }


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
        result = nano_client.blend_user_with_diagram(
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
