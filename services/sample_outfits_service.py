"""
Sample Outfits Service - Search RichWear dataset for matching outfits
"""
from pathlib import Path
from typing import List, Dict
from database import SessionLocal
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class SampleOutfit(Base):
    """RichWear dataset sample outfits"""
    __tablename__ = "sample_outfits"
    id = Column(Integer, primary_key=True, index=True)
    photo_filename = Column(String, nullable=False, index=True)
    tags = Column(String, nullable=False)
    gender = Column(String(10), nullable=True, index=True)
    date = Column(String(10), nullable=True)

PHOTOS_DIR = Path(__file__).parent.parent / "sample-outfits" / "richwear~" / "RichWear" / "photos" / "1-1"

def search_sample_outfits(preferred_colors: List[str], preferred_styles: List[str], limit: int = 5) -> List[Dict]:
    """Search RichWear dataset for outfits matching user preferences."""
    db = SessionLocal()
    try:
        outfits = db.query(SampleOutfit).all()
        if not outfits:
            return []

        scored = []
        for outfit in outfits:
            tags = [t.strip().lower() for t in outfit.tags.split(',')]
            score = sum(2 for c in preferred_colors if c.lower() in tags)
            score += sum(1 for s in preferred_styles if s.lower() in tags)

            if score > 0:
                photo_path = PHOTOS_DIR / outfit.photo_filename
                scored.append({
                    "photo": outfit.photo_filename,
                    "photo_path": str(photo_path) if photo_path.exists() else None,
                    "tags": outfit.tags.split(','),
                    "match_score": score,
                })

        scored.sort(key=lambda x: x["match_score"], reverse=True)
        return scored[:limit]
    finally:
        db.close()
