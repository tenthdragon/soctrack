"""Snapshots & metrics endpoints."""

import uuid
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.snapshot import Snapshot
from app.models.post import Post

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────

class SnapshotResponse(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    views: int
    likes: int
    comments: int
    shares: int
    baseline_views: int = 0
    baseline_likes: int = 0
    baseline_comments: int = 0
    baseline_shares: int = 0
    recorded_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class BrandStats(BaseModel):
    total_views: int
    total_likes: int
    total_comments: int
    total_shares: int
    delta_views: int
    delta_likes: int
    delta_comments: int
    delta_shares: int


class ComparePostData(BaseModel):
    post_id: uuid.UUID
    title: Optional[str]
    brand_name: str
    current_views: int
    current_likes: int
    current_comments: int
    current_shares: int
    snapshots: list[SnapshotResponse]


# ── Endpoints ────────────────────────────────────────────

@router.get("/posts/{post_id}/snapshots", response_model=list[SnapshotResponse])
def list_snapshots(
    post_id: uuid.UUID,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """List semua daily snapshots untuk post tertentu."""
    query = db.query(Snapshot).filter(Snapshot.post_id == post_id)

    if date_from:
        query = query.filter(Snapshot.recorded_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Snapshot.recorded_at <= datetime.combine(date_to, datetime.max.time()))

    return query.order_by(Snapshot.recorded_at.desc()).all()


@router.get("/brands/{brand_id}/stats", response_model=BrandStats)
def brand_stats(brand_id: uuid.UUID, db: Session = Depends(get_db)):
    """Aggregated stats untuk brand: total views/likes/comments/shares + deltas."""
    active_posts = db.query(Post).filter(
        Post.brand_id == brand_id, Post.is_active == True
    ).all()

    if not active_posts:
        return BrandStats(
            total_views=0, total_likes=0, total_comments=0, total_shares=0,
            delta_views=0, delta_likes=0, delta_comments=0, delta_shares=0,
        )

    post_ids = [p.id for p in active_posts]
    totals = {"views": 0, "likes": 0, "comments": 0, "shares": 0}
    deltas = {"views": 0, "likes": 0, "comments": 0, "shares": 0}

    for post_id in post_ids:
        # Get latest snapshot — delta is current minus baseline (intra-day gain)
        latest = (
            db.query(Snapshot)
            .filter(Snapshot.post_id == post_id)
            .order_by(Snapshot.recorded_at.desc())
            .first()
        )
        if latest:
            totals["views"] += latest.views
            totals["likes"] += latest.likes
            totals["comments"] += latest.comments
            totals["shares"] += latest.shares

            deltas["views"] += latest.views - latest.baseline_views
            deltas["likes"] += latest.likes - latest.baseline_likes
            deltas["comments"] += latest.comments - latest.baseline_comments
            deltas["shares"] += latest.shares - latest.baseline_shares

    return BrandStats(
        total_views=totals["views"],
        total_likes=totals["likes"],
        total_comments=totals["comments"],
        total_shares=totals["shares"],
        delta_views=deltas["views"],
        delta_likes=deltas["likes"],
        delta_comments=deltas["comments"],
        delta_shares=deltas["shares"],
    )


@router.get("/brands/{brand_id}/stats/daily")
def brand_daily_stats(
    brand_id: uuid.UUID,
    days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """Daily aggregated stats untuk chart di brand level."""
    # TODO: implement daily aggregation query
    return {"message": "Not yet implemented", "brand_id": str(brand_id)}


@router.get("/compare")
def compare_posts(
    post_ids: str = Query(..., description="Comma-separated post UUIDs"),
    db: Session = Depends(get_db),
):
    """Data untuk compare view: metrics side by side."""
    ids = [uuid.UUID(pid.strip()) for pid in post_ids.split(",")]

    results = []
    for post_id in ids:
        post = db.query(Post).filter(Post.id == post_id).first()
        if not post:
            continue

        snapshots = (
            db.query(Snapshot)
            .filter(Snapshot.post_id == post_id)
            .order_by(Snapshot.recorded_at.desc())
            .limit(30)
            .all()
        )

        latest = snapshots[0] if snapshots else None
        results.append({
            "post_id": str(post.id),
            "title": post.title,
            "tiktok_url": post.tiktok_url,
            "current_views": latest.views if latest else 0,
            "current_likes": latest.likes if latest else 0,
            "current_comments": latest.comments if latest else 0,
            "current_shares": latest.shares if latest else 0,
            "snapshots": [
                {
                    "date": s.recorded_at.isoformat(),
                    "views": s.views,
                    "likes": s.likes,
                    "comments": s.comments,
                    "shares": s.shares,
                }
                for s in reversed(snapshots)
            ],
        })

    return results
