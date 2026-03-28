import base64
import io
import logging
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict

# Fix Windows console encoding for Chinese characters
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

from dotenv import load_dotenv
load_dotenv()

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from PIL import Image

# rembg is imported lazily inside _remove_background to avoid slowing startup
# if the model weights have not yet been downloaded.

from auth import create_access_token, get_current_user, hash_password, verify_password
from database import Garment, SessionLocal, User, UserFeedback, UserProfile, get_db, init_db
from apis.nano_banana_client import NanoBananaClient

# Reuse Uvicorn's logger so app logs appear in the same console as server startup logs.
logger = logging.getLogger("uvicorn.error")

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
# Serve RichWear dataset photos at /richwear/<filename>
RICHWEAR_DIR = Path("sample-outfits/richwear~/RichWear/photos")
if RICHWEAR_DIR.exists():
    app.mount("/richwear", StaticFiles(directory=str(RICHWEAR_DIR)), name="richwear")

nano_client = NanoBananaClient()


# ---------------------------------------------------------------------------
# In-memory try-on job store
# ---------------------------------------------------------------------------

class TryOnJob(TypedDict):
    status: Literal["pending", "completed", "failed"]
    person_image_url: str
    garment_image_url: str
    result: Optional[Dict[str, Any]]
    result_url: Optional[str]
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
async def register(body: AuthRequest, request: Request, db: Session = Depends(get_db)):
    """
    Create a new user account and return a JWT so the client is logged in immediately.
    Returns 409 if the username is already taken.
    """
    client_host = request.client.host if request.client else "unknown"
    logger.info("Register attempt from %s for username=%s", client_host, body.username)

    if db.query(User).filter(User.username == body.username).first():
        logger.info("Register rejected for username=%s: already taken", body.username)
        raise HTTPException(status_code=409, detail="Username already taken.")

    user = User(username=body.username, hashed_password=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("Register rejected for username=%s: duplicate detected on commit", body.username)
        raise HTTPException(status_code=409, detail="Username already taken.")
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to create user '%s'", body.username)
        raise HTTPException(status_code=500, detail="Failed to create account.")

    try:
        db.refresh(user)
        token = create_access_token(user_id=user.id, username=user.username)
    except Exception:
        logger.exception("User '%s' was created but automatic sign-in failed", body.username)
        raise HTTPException(
            status_code=500,
            detail="Account created, but automatic sign-in failed. Please log in manually.",
        )

    logger.info("New user registered: %s (id=%s) from %s", user.username, user.id, client_host)
    return {"access_token": token, "token_type": "bearer", "username": user.username}


@app.post("/api/auth/login")
async def login(body: AuthRequest, request: Request, db: Session = Depends(get_db)):
    """
    Verify credentials and return a JWT.
    Returns 401 on wrong username or password (intentionally vague for security).
    """
    client_host = request.client.host if request.client else "unknown"
    logger.info("Login attempt from %s for username=%s", client_host, body.username)

    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not verify_password(body.password, user.hashed_password):
        logger.info("Login rejected for username=%s from %s", body.username, client_host)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    token = create_access_token(user_id=user.id, username=user.username)
    logger.info("User logged in: %s (id=%s) from %s", user.username, user.id, client_host)
    return {"access_token": token, "token_type": "bearer", "username": user.username}


@app.get("/api/auth/me")
async def me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile (useful for token validation)."""
    return {"user_id": current_user.id, "username": current_user.username}


# ---------------------------------------------------------------------------
# User Profile
# ---------------------------------------------------------------------------

class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    gender: Optional[str] = None
    height_cm: Optional[int] = None
    weight_kg: Optional[int] = None
    skin_tone: Optional[str] = None
    preferred_styles: Optional[List[str]] = None
    preferred_colors: Optional[List[str]] = None
    preferred_patterns: Optional[List[str]] = None
    budget_range: Optional[str] = None
    favorite_brands: Optional[str] = None
    liked_outfit_tags: Optional[List[str]] = None


def _json_list_or_empty(raw_value: Optional[str]) -> List[str]:
    import json as _j

    if not raw_value:
        return []
    try:
        parsed = _j.loads(raw_value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _profile_to_dict(p: UserProfile) -> dict:
    return {
        "display_name": p.display_name,
        "gender": p.gender,
        "height_cm": p.height_cm,
        "weight_kg": p.weight_kg,
        "skin_tone": p.skin_tone,
        "preferred_styles": _json_list_or_empty(getattr(p, "preferred_styles", None)),
        "preferred_colors": _json_list_or_empty(getattr(p, "preferred_colors", None)),
        "preferred_patterns": _json_list_or_empty(getattr(p, "preferred_patterns", None)),
        "budget_range": p.budget_range,
        "favorite_brands": p.favorite_brands,
        "liked_outfit_tags": _json_list_or_empty(getattr(p, "liked_outfit_tags", None)),
    }


@app.get("/api/auth/profile")
def get_profile(current_user: User = Depends(get_current_user)):
    """Return the user's profile or empty defaults."""
    db = SessionLocal()
    try:
        p = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
        if not p:
            return {
                "display_name": "", "gender": "", "height_cm": None, "weight_kg": None,
                "skin_tone": "", "preferred_styles": [], "preferred_colors": [],
                "preferred_patterns": [], "budget_range": "", "favorite_brands": "",
                "liked_outfit_tags": [],
            }
        return _profile_to_dict(p)
    finally:
        db.close()


@app.put("/api/auth/profile")
def update_profile(body: ProfileUpdate, current_user: User = Depends(get_current_user)):
    """Create or update the user's profile."""
    import json as _j
    db = SessionLocal()
    try:
        p = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
        if not p:
            p = UserProfile(user_id=current_user.id)
            db.add(p)

        if body.display_name is not None:
            p.display_name = body.display_name
        if body.gender is not None:
            p.gender = body.gender
        if body.height_cm is not None:
            p.height_cm = body.height_cm
        if body.weight_kg is not None:
            p.weight_kg = body.weight_kg
        if body.skin_tone is not None:
            p.skin_tone = body.skin_tone
        if body.preferred_styles is not None:
            p.preferred_styles = _j.dumps(body.preferred_styles)
        if body.preferred_colors is not None:
            p.preferred_colors = _j.dumps(body.preferred_colors)
        if body.preferred_patterns is not None:
            p.preferred_patterns = _j.dumps(body.preferred_patterns)
        if body.budget_range is not None:
            p.budget_range = body.budget_range
        if body.favorite_brands is not None:
            p.favorite_brands = body.favorite_brands
        if body.liked_outfit_tags is not None and hasattr(p, "liked_outfit_tags"):
            p.liked_outfit_tags = _j.dumps(body.liked_outfit_tags)

        db.commit()
        db.refresh(p)
        return _profile_to_dict(p)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


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
    Background task: call HKBU GenAI (gemini-2.5-flash) via OpenAI-compatible API
    to extract category/color/material and write them back to the Garment row.
    Uses its own DB session — safe to run in a background thread.
    """
    import base64
    import json
    import requests as _requests

    try:
        api_key = os.environ.get("HKBU_API_KEY", "")
        base_url = os.environ.get("HKBU_BASE_URL", "https://genai.hkbu.edu.hk/api/v0/rest")
        if not api_key:
            logger.warning("HKBU_API_KEY not set — skipping auto-tagging for garment %s", garment_id)
            return

        img_b64 = base64.b64encode(image_bytes).decode()
        prompt = (
            "Analyze this clothing item image. "
            "Reply with ONLY a raw JSON object (no markdown, no code fences):\n"
            '{"category": "<Top|Bottom|Outerwear|Dress|Shoes|Accessory>", '
            '"color": "<main color name, e.g. Black, Navy Blue, White>", '
            '"material": "<fabric type, e.g. Cotton|Denim|Polyester|Wool|Leather|Synthetic>"}'
        )

        payload = {
            "model": "gemini-2.5-flash",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    ],
                }
            ],
            "max_tokens": 256,
            "temperature": 0,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        resp = _requests.post(
            f"{base_url}/deployments/gemini-2.5-flash/chat/completions",
            json=payload,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()

        raw = resp.json()["choices"][0]["message"]["content"].strip()
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
                "user_id": g.user_id,
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


@app.delete("/api/wardrobe/garments/{garment_id}", status_code=200)
async def delete_garment(
    garment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a garment and its associated files. Users can only delete their own garments."""
    garment = db.query(Garment).filter(Garment.id == garment_id).first()

    if not garment:
        raise HTTPException(status_code=404, detail="Garment not found")

    if garment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this garment")

    # Delete physical files from disk
    files_to_delete = [garment.image_path, garment.thumbnail_path, garment.nobg_path]
    for file_path in files_to_delete:
        if file_path:
            try:
                full_path = Path(file_path)
                if full_path.exists():
                    os.remove(full_path)
            except Exception as e:
                logger.warning(f"Failed to delete file {file_path}: {e}")

    db.delete(garment)
    db.commit()

    return {"message": "Garment deleted successfully"}


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


def _guess_image_extension(content_type: Optional[str], fallback: str = ".png") -> str:
    ext = mimetypes.guess_extension(content_type or "")
    if not ext:
        return fallback
    if ext == ".jpe":
        return ".jpg"
    return ext


def _decode_data_uri(data_uri: str) -> tuple[Optional[str], bytes]:
    header, payload = data_uri.split(",", 1)
    mime = None
    if ";" in header and ":" in header:
        mime = header.split(":", 1)[1].split(";", 1)[0].strip() or None
    return mime, base64.b64decode(payload)


def _persist_tryon_asset(job_id: str, image_bytes: bytes, content_type: Optional[str]) -> str:
    ext = _guess_image_extension(content_type, fallback=".png")
    file_name = f"{job_id}_tryon{ext}"
    output_path = UPLOADS_DIR / file_name
    output_path.write_bytes(image_bytes)
    return f"/uploads/{file_name}"


def _normalize_tryon_result(job_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(result)
    image_url = normalized.get("image_url")
    image_data = normalized.get("image_data")
    result_url = None

    if isinstance(image_data, str) and image_data.startswith("data:"):
        content_type, image_bytes = _decode_data_uri(image_data)
        result_url = _persist_tryon_asset(job_id, image_bytes, content_type)
        normalized["image_data"] = None
        normalized["storage"] = "server_upload"
    elif isinstance(image_url, str) and image_url.startswith("data:"):
        content_type, image_bytes = _decode_data_uri(image_url)
        result_url = _persist_tryon_asset(job_id, image_bytes, content_type)
        normalized["image_url"] = None
        normalized["storage"] = "server_upload"
    elif isinstance(image_url, str) and image_url.startswith("http"):
        try:
            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type")
            result_url = _persist_tryon_asset(job_id, response.content, content_type)
            normalized["source_image_url"] = image_url
            normalized["storage"] = "server_upload"
        except Exception:
            logger.warning("Try-on job %s: failed to persist remote image, using provider URL", job_id)
            result_url = image_url
            normalized["storage"] = "provider_url"

    if result_url:
        normalized["image_url"] = result_url

    normalized["result_url"] = normalized.get("image_url") or normalized.get("image_data")
    return normalized


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

        normalized = _normalize_tryon_result(job_id, result)
        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["result"] = normalized
        _jobs[job_id]["result_url"] = normalized.get("result_url")
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
        _jobs[job_id]["result_url"] = None
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
        result_url=None,
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
            "result_url": job["result_url"],
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
# Recommendation endpoints
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    garment_ids: List[int]
    liked: bool
    occasion: Optional[str] = None


@app.post("/api/recommend/daily")
def recommend_daily(
    occasion: str = Form("casual"),
    wardrobe_only: str = Form("true"),
    current_user: User = Depends(get_current_user),
):
    """
    Run the wardrobe recommendation agent for the current user.
    Returns 3 outfit combinations (JSON + image URLs only — no Nano Banana calls).
    Runs synchronously in FastAPI's thread pool.
    """
    from services.wardrobe_agent import run_wardrobe_recommendation
    try:
        use_samples = wardrobe_only.lower() == "false"
        return run_wardrobe_recommendation(user_id=current_user.id, occasion=occasion, include_samples=use_samples)
    except Exception as exc:
        logger.exception("Recommend daily failed for user %s", current_user.username)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/recommend/feedback", status_code=200)
async def recommend_feedback(
    body: FeedbackRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Persist a like/pass decision for a specific outfit's garments.
    Payload: {"garment_ids": [4, 7], "liked": true, "occasion": "casual"}
    Used by the Personal Preference Agent for personalized recommendations.
    """
    import json as _json
    action = "LIKED" if body.liked else "PASSED"
    logger.info(
        "Feedback | user=%s action=%s garment_ids=%s",
        current_user.username, action, body.garment_ids,
    )
    if not body.garment_ids:
        return {"status": "ignored", "reason": "no_garment_ids"}
    db = SessionLocal()
    try:
        fb = UserFeedback(
            user_id=current_user.id,
            garment_ids=_json.dumps(body.garment_ids),
            liked=1 if body.liked else 0,
            occasion=body.occasion,
        )
        db.add(fb)
        db.commit()
    except Exception:
        logger.exception("Failed to persist feedback")
        db.rollback()
    finally:
        db.close()
    return {"status": "recorded"}


@app.post("/api/try-on/from-sample", status_code=202)
async def try_on_from_sample(
    background_tasks: BackgroundTasks,
    person_image: UploadFile = File(..., description="Headless full-body photo"),
    sample_image_url: str = Form(..., description="RichWear image path, e.g. /richwear/6-4/xxx.jpg"),
    current_user: User = Depends(get_current_user),
):
    """
    Virtual try-on using a RichWear sample image.
    Reads the sample image from the dataset photos directory on disk.
    """
    # Validate person image type
    if person_image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported image type '{person_image.content_type}'.")

    # Resolve sample image path safely (prevent path traversal)
    # sample_image_url is like "/richwear/6-4/20180728104316845_500.jpg"
    relative = sample_image_url.lstrip("/").removeprefix("richwear/")
    sample_path = RICHWEAR_DIR / relative
    if not sample_path.exists() or not sample_path.is_file():
        raise HTTPException(status_code=404, detail=f"Sample image not found: {sample_image_url}")
    # Security: ensure resolved path is inside RICHWEAR_DIR
    try:
        sample_path.resolve().relative_to(RICHWEAR_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid sample image path.")

    person_bytes = await person_image.read()
    garment_bytes = sample_path.read_bytes()
    garment_mime = mimetypes.guess_type(sample_path.name)[0] or "image/jpeg"

    job_id = uuid.uuid4().hex
    person_name = f"{job_id}_person_{Path(person_image.filename or 'person.jpg').name}"
    (UPLOADS_DIR / person_name).write_bytes(person_bytes)

    _jobs[job_id] = TryOnJob(
        status="pending",
        person_image_url=f"/uploads/{person_name}",
        garment_image_url=sample_image_url,
        result=None,
        result_url=None,
        error=None,
        detail=None,
    )

    background_tasks.add_task(_run_tryon_job, job_id, person_bytes, garment_bytes, garment_mime)

    logger.info("Try-on (from sample) job %s queued: user=%s sample=%s", job_id, current_user.username, sample_image_url)
    return {
        "job_id": job_id,
        "status": "pending",
        "poll_url": f"/api/try-on/status/{job_id}",
    }


@app.post("/api/try-on/from-wardrobe", status_code=202)
async def try_on_from_wardrobe(
    background_tasks: BackgroundTasks,
    person_image: UploadFile = File(..., description="Headless full-body photo"),
    garment_id: int = Form(..., description="ID of the garment from the user's wardrobe"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Virtual try-on using a garment already stored in the user's wardrobe.
    Reads the garment image from disk (no re-upload needed from the frontend).
    Returns a job_id to poll via GET /api/try-on/status/{job_id}.
    """
    garment = (
        db.query(Garment)
        .filter(Garment.id == garment_id, Garment.user_id == current_user.id)
        .first()
    )
    if not garment:
        raise HTTPException(status_code=404, detail=f"Garment {garment_id} not found.")

    for upload in [person_image]:
        if upload.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported image type '{upload.content_type}'.",
            )

    person_bytes = await person_image.read()
    garment_bytes = Path(garment.image_path).read_bytes()
    garment_mime = mimetypes.guess_type(str(garment.image_path))[0] or "image/jpeg"

    job_id = uuid.uuid4().hex
    person_name = f"{job_id}_person_{Path(person_image.filename or 'person.jpg').name}"
    (UPLOADS_DIR / person_name).write_bytes(person_bytes)

    _jobs[job_id] = TryOnJob(
        status="pending",
        person_image_url=f"/uploads/{person_name}",
        garment_image_url=f"/uploads/{Path(garment.image_path).name}",
        result=None,
        result_url=None,
        error=None,
        detail=None,
    )

    background_tasks.add_task(_run_tryon_job, job_id, person_bytes, garment_bytes, garment_mime)

    logger.info(
        "Try-on (from wardrobe) job %s queued: user=%s garment_id=%s",
        job_id, current_user.username, garment_id,
    )
    return {
        "job_id": job_id,
        "status": "pending",
        "poll_url": f"/api/try-on/status/{job_id}",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
