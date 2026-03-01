import logging
import os
import uuid
from pathlib import Path

# Fix Windows console encoding for Chinese characters
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from services.appearance_service import AppearanceGenerationService

logger = logging.getLogger(__name__)

# Ensure uploads directory exists before mounting
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Appearance Fusion API", version="0.1.0")

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

@app.get("/health")
async def health_check():
    return {"status": "ok"}

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

    # Build a unique filename, preserving the original extension
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
        # just call the service method not gen image
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
    internal_context: str = Form(...) # receive first step generated Context
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