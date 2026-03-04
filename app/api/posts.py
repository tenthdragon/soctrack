"""Post management endpoints."""

import uuid
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.post import Post
from app.models.brand import Brand

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────

class PostAddByLink(BaseModel):
    tiktok_url: str
    brand_id: Optional[uuid.UUID] = None


class PostAddByAccount(BaseModel):
    tiktok_username: str
    brand_id: uuid.UUID


class PostResponse(BaseModel):
    id: uuid.UUID
    brand_id: uuid.UUID
    tiktok_url: str
    tiktok_video_id: str
    title: Optional[str]
    posted_at: Optional[datetime]
    tracking_since: datetime
    is_active: bool
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class PostUpdate(BaseModel):
    is_active: Optional[bool] = None
    title: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────

def extract_video_id(url: str) -> str:
    """Extract video ID from TikTok URL."""
    match = re.search(r"/video/(\d+)", url)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract video ID from URL: {url}")


def extract_username(url: str) -> Optional[str]:
    """Extract username from TikTok URL."""
    match = re.search(r"@([\w.]+)", url)
    return match.group(1) if match else None


# ── Endpoints ────────────────────────────────────────────

@router.get("/brands/{brand_id}/posts", response_model=list[PostResponse])
def list_posts(brand_id: uuid.UUID, db: Session = Depends(get_db)):
    """List semua tracked posts untuk brand tertentu."""
    return (
        db.query(Post)
        .filter(Post.brand_id == brand_id, Post.is_active == True)
        .all()
    )


@router.post("/posts/add-by-link", response_model=PostResponse, status_code=201)
def add_post_by_link(data: PostAddByLink, db: Session = Depends(get_db)):
    """Tambah post by URL."""
    try:
        video_id = extract_video_id(data.tiktok_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check duplicate
    existing = db.query(Post).filter(Post.tiktok_video_id == video_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Post already being tracked")

    # Auto-detect brand from username if not provided
    brand_id = data.brand_id
    if not brand_id:
        username = extract_username(data.tiktok_url)
        if username:
            brand = (
                db.query(Brand)
                .filter(Brand.tiktok_username.ilike(f"@{username}"))
                .first()
            )
            if brand:
                brand_id = brand.id

    if not brand_id:
        raise HTTPException(
            status_code=400,
            detail="Could not auto-detect brand. Please provide brand_id.",
        )

    post = Post(
        brand_id=brand_id,
        tiktok_url=data.tiktok_url,
        tiktok_video_id=video_id,
        source="link",
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@router.post("/posts/add-by-account", status_code=202)
def add_post_by_account(
    data: PostAddByAccount,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger account discovery: scrape profile, tambah semua post."""
    brand = db.query(Brand).filter(Brand.id == data.brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    # TODO: trigger scraper in background
    # background_tasks.add_task(discover_account_posts, data.tiktok_username, data.brand_id)

    return {
        "message": f"Account discovery started for {data.tiktok_username}",
        "brand_id": str(data.brand_id),
    }


@router.put("/posts/{post_id}", response_model=PostResponse)
def update_post(post_id: uuid.UUID, data: PostUpdate, db: Session = Depends(get_db)):
    """Update post (e.g., untrack)."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(post, field, value)

    db.commit()
    db.refresh(post)
    return post


@router.delete("/posts/{post_id}", status_code=204)
def delete_post(post_id: uuid.UUID, db: Session = Depends(get_db)):
    """Hapus post dan semua snapshots-nya."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    db.delete(post)
    db.commit()
