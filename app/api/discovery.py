"""Discovery (FYP Scanner) endpoints."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.discovery import DiscoveryResult
from app.models.post import Post

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────

class DiscoverySearchRequest(BaseModel):
    keyword: str
    max_results: int = 50


class DiscoveryResultResponse(BaseModel):
    id: uuid.UUID
    keyword: str
    tiktok_url: str
    tiktok_video_id: str
    creator_username: Optional[str]
    views_at_discovery: int
    likes_at_discovery: int
    is_tracked: bool
    discovered_at: datetime

    class Config:
        from_attributes = True


class TrackDiscoveryRequest(BaseModel):
    brand_id: uuid.UUID


# ── Endpoints ────────────────────────────────────────────

@router.post("/discovery/search", status_code=202)
def search_discovery(
    data: DiscoverySearchRequest,
    background_tasks: BackgroundTasks,
):
    """Trigger keyword search di TikTok. Async job."""
    # TODO: trigger scraper in background
    # background_tasks.add_task(run_discovery_search, data.keyword, data.max_results)

    return {
        "message": f"Discovery search started for keyword: '{data.keyword}'",
        "max_results": data.max_results,
    }


@router.get("/discovery/results", response_model=list[DiscoveryResultResponse])
def list_discovery_results(
    keyword: Optional[str] = Query(None),
    is_tracked: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    """List discovery results with optional filters."""
    query = db.query(DiscoveryResult)

    if keyword:
        query = query.filter(DiscoveryResult.keyword.ilike(f"%{keyword}%"))
    if is_tracked is not None:
        query = query.filter(DiscoveryResult.is_tracked == is_tracked)

    return query.order_by(DiscoveryResult.views_at_discovery.desc()).all()


@router.post("/discovery/track/{result_id}", status_code=201)
def track_discovery_result(
    result_id: uuid.UUID,
    data: TrackDiscoveryRequest,
    db: Session = Depends(get_db),
):
    """Pindahkan discovery result ke tracked posts."""
    result = db.query(DiscoveryResult).filter(DiscoveryResult.id == result_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Discovery result not found")

    if result.is_tracked:
        raise HTTPException(status_code=409, detail="Already tracked")

    # Check duplicate
    existing = db.query(Post).filter(Post.tiktok_video_id == result.tiktok_video_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Post already being tracked")

    # Create post from discovery result
    post = Post(
        brand_id=data.brand_id,
        tiktok_url=result.tiktok_url,
        tiktok_video_id=result.tiktok_video_id,
        source="discovery",
    )
    db.add(post)

    # Mark as tracked
    result.is_tracked = True
    db.commit()
    db.refresh(post)

    return {"message": "Post added to tracking", "post_id": str(post.id)}
