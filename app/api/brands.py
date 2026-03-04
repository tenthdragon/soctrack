"""Brand CRUD endpoints."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.brand import Brand

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────

class BrandCreate(BaseModel):
    name: str
    tiktok_username: Optional[str] = None
    is_competitor: bool = False
    color: Optional[str] = None
    logo_emoji: Optional[str] = None
    auto_discover: bool = True


class BrandUpdate(BaseModel):
    name: Optional[str] = None
    tiktok_username: Optional[str] = None
    is_competitor: Optional[bool] = None
    color: Optional[str] = None
    logo_emoji: Optional[str] = None
    auto_discover: Optional[bool] = None


class BrandResponse(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    tiktok_username: Optional[str]
    is_competitor: bool
    color: Optional[str]
    logo_emoji: Optional[str]
    auto_discover: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Endpoints ────────────────────────────────────────────

@router.get("/brands", response_model=list[BrandResponse])
def list_brands(db: Session = Depends(get_db)):
    """List semua brands untuk business yang login."""
    return db.query(Brand).all()


@router.post("/brands", response_model=BrandResponse, status_code=201)
def create_brand(data: BrandCreate, db: Session = Depends(get_db)):
    """Tambah brand baru."""
    brand = Brand(
        name=data.name,
        tiktok_username=data.tiktok_username,
        is_competitor=data.is_competitor,
        color=data.color,
        logo_emoji=data.logo_emoji,
        auto_discover=data.auto_discover,
        # TODO: get business_id from auth context
        business_id=uuid.uuid4(),
    )
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


@router.put("/brands/{brand_id}", response_model=BrandResponse)
def update_brand(brand_id: uuid.UUID, data: BrandUpdate, db: Session = Depends(get_db)):
    """Update brand."""
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(brand, field, value)

    db.commit()
    db.refresh(brand)
    return brand


@router.delete("/brands/{brand_id}", status_code=204)
def delete_brand(brand_id: uuid.UUID, db: Session = Depends(get_db)):
    """Hapus brand dan semua posts/snapshots-nya."""
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    db.delete(brand)
    db.commit()
