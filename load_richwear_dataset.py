"""
Load RichWear dataset into database for fast sample outfit search.
Creates a new table: sample_outfits
"""
from pathlib import Path
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./aura.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class SampleOutfit(Base):
    """RichWear dataset sample outfits"""
    __tablename__ = "sample_outfits"

    id = Column(Integer, primary_key=True, index=True)
    photo_filename = Column(String, nullable=False, index=True)
    tags = Column(String, nullable=False)  # comma-separated
    gender = Column(String(10), nullable=True, index=True)
    date = Column(String(10), nullable=True)


# Create table
Base.metadata.create_all(bind=engine)

# Load dataset
RICHWEAR_ROOT = Path(__file__).parent / "sample-outfits" / "richwear~" / "RichWear"

print("Loading RichWear dataset...")
print(f"Dataset path: {RICHWEAR_ROOT}")

if not RICHWEAR_ROOT.exists():
    print("ERROR: RichWear dataset not found!")
    exit(1)

# Load files
photos_file = RICHWEAR_ROOT / "photos.txt"
labels_file = RICHWEAR_ROOT / "label_verified.txt"
gender_file = RICHWEAR_ROOT / "gender.txt"
date_file = RICHWEAR_ROOT / "date.txt"

print(f"Loading photos from {photos_file}...")
with open(photos_file, 'r', encoding='utf-8') as f:
    photos = [line.strip() for line in f if line.strip()]

print(f"Loading labels from {labels_file}...")
with open(labels_file, 'r', encoding='utf-8') as f:
    labels = [line.strip() for line in f if line.strip()]

print(f"Loading genders from {gender_file}...")
with open(gender_file, 'r', encoding='utf-8') as f:
    genders = [line.strip() for line in f if line.strip()]

print(f"Loading dates from {date_file}...")
with open(date_file, 'r', encoding='utf-8') as f:
    dates = [line.strip() for line in f if line.strip()]

print(f"\nDataset stats:")
print(f"  Total photos: {len(photos)}")
print(f"  Verified labels: {len(labels)}")
print(f"  Genders: {len(genders)}")
print(f"  Dates: {len(dates)}")

# Insert into database (verified subset only)
db = SessionLocal()

# Clear existing data
print("\nClearing existing sample outfits...")
db.query(SampleOutfit).delete()
db.commit()

print("Inserting verified outfits into database...")
inserted = 0

for i, label in enumerate(labels):
    if i >= len(photos):
        break

    outfit = SampleOutfit(
        photo_filename=photos[i],
        tags=label,
        gender=genders[i] if i < len(genders) else None,
        date=dates[i] if i < len(dates) else None,
    )
    db.add(outfit)
    inserted += 1

    if inserted % 500 == 0:
        print(f"  Inserted {inserted} outfits...")
        db.commit()

db.commit()
print(f"\n✓ Successfully loaded {inserted} sample outfits into database!")

# Show sample
print("\nSample outfits:")
samples = db.query(SampleOutfit).limit(5).all()
for s in samples:
    print(f"  {s.id}: {s.photo_filename} | {s.tags[:50]}... | {s.gender}")

db.close()
print("\nDone!")
