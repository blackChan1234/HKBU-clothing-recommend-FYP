"""
database.py
SQLAlchemy setup + all ORM models (User, Garment).
"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

DATABASE_URL = "sqlite:///./aura.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # required for SQLite
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    garments = relationship("Garment", back_populates="owner", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Garment
# ---------------------------------------------------------------------------

class Garment(Base):
    __tablename__ = "garments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Storage paths (relative to project root)
    image_path = Column(String, nullable=False)
    thumbnail_path = Column(String, nullable=True)   # populated by Task 2.2

    # Metadata — all nullable until auto-tagging (Task 2.4) fills them in
    label = Column(String(100), nullable=True)        # free-text user label
    category = Column(String(50), nullable=True)      # e.g. Top / Pants / Shoes
    color = Column(String(50), nullable=True)         # e.g. Black / Navy
    material = Column(String(50), nullable=True)      # e.g. Cotton / Denim

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    owner = relationship("User", back_populates="garments")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables. Idempotent — safe to call every server start."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency that yields a DB session and ensures it is closed."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
