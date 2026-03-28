"""Manually tag all garments that have category=None"""
from database import SessionLocal, Garment
from apis.api_clients import HKBUAPIClient
from pathlib import Path
import base64
import json

db = SessionLocal()
api = HKBUAPIClient()

garments = db.query(Garment).filter(Garment.category == None).all()
print(f"Found {len(garments)} untagged garments")

for g in garments:
    try:
        img_path = Path(g.image_path)
        if not img_path.exists():
            print(f"  [{g.id}] File not found: {img_path}")
            continue

        img_b64 = base64.b64encode(img_path.read_bytes()).decode()

        prompt = f"""Analyze this clothing item image and return ONLY a JSON object:
{{"category": "Top|Bottom|Dress|Outerwear|Shoes|Accessories", "color": "color name", "material": "fabric type"}}"""

        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
            ]}
        ]

        raw = api.call_chatgpt(messages, model="gemini-2.5-flash", temperature=0.3)

        # Parse JSON
        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1:
            data = json.loads(raw[start:end+1])
            g.category = data.get("category", "Unknown")
            g.color = data.get("color", "Unknown")
            g.material = data.get("material", "Unknown")
            db.commit()
            print(f"  [{g.id}] Tagged: {g.category} | {g.color} | {g.material}")
        else:
            print(f"  [{g.id}] Failed to parse: {raw[:100]}")
    except Exception as e:
        print(f"  [{g.id}] Error: {e}")

db.close()
print("Done!")
