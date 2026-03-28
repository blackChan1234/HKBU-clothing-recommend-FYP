"""Manually tag garments with simple categories"""
from database import SessionLocal, Garment

db = SessionLocal()

# Update garments with basic categories
# You can modify these based on what each garment actually is
updates = [
    (1, "Top", "Blue", "Cotton"),
    (2, "Bottom", "Black", "Denim"),
    (3, "Top", "White", "Cotton"),
    (4, "Bottom", "Navy", "Cotton"),
    (5, "Outerwear", "Gray", "Polyester"),
    (6, "Top", "Red", "Cotton"),
    (7, "Bottom", "Khaki", "Cotton"),
    (8, "Shoes", "Black", "Leather"),
    (9, "Accessories", "Brown", "Leather"),
]

for gid, cat, col, mat in updates:
    g = db.query(Garment).filter(Garment.id == gid).first()
    if g:
        g.category = cat
        g.color = col
        g.material = mat
        print(f"Updated garment {gid}: {cat} | {col} | {mat}")

db.commit()
db.close()
print("\nDone! Now try generating outfits again.")
