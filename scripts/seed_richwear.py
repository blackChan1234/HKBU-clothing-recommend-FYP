"""
seed_richwear.py
Import RichWear dataset images into admin's shared pool (user_id=1)
"""
import os
import sys
import shutil
import uuid
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import Garment, SessionLocal, init_db

# RichWear dataset path
DATASET_PATH = Path("sample-outfits/richwear~/RichWear")
UPLOADS_DIR = Path("uploads")

# Category mapping from RichWear classes
CATEGORY_MAP = {
    'Top': 'Tops', 'T-Shirt': 'Tops', 'Shirt': 'Tops', 'Cardigan': 'Tops',
    'Blazer': 'Outerwear', 'Sweatshirt': 'Tops', 'Vest': 'Tops',
    'Jacket': 'Outerwear', 'Coat': 'Outerwear',
    'Dress': 'Dress', 'Kimono_Yukata': 'Dress', 'Jumpsuit': 'Dress',
    'Skirt': 'Bottoms', 'Pants': 'Bottoms', 'Jeans': 'Bottoms',
    'Shoes': 'Shoes', 'Sandals': 'Shoes', 'Boots': 'Shoes',
    'Pumps': 'Shoes', 'Sneakers': 'Shoes',
    'Swimwear': 'Accessories', 'Stockings': 'Accessories',
    'Scarf': 'Accessories', 'Bag': 'Accessories',
}

COLORS = ['Black', 'Gray', 'White', 'Beige', 'Orange', 'Pink', 'Red',
          'Green', 'Brown', 'Blue', 'Yellow', 'Purple']


def load_txt(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines()]


def load_txt_mv(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return [line.strip().split(',') for line in f.readlines()]
