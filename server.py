import logging
import os

# Fix Windows console encoding for Chinese characters
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from services.appearance_service import AppearanceGenerationService

logger = logging.getLogger(__name__)

app = FastAPI(title="Appearance Fusion API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = AppearanceGenerationService()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

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