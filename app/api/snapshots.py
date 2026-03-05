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
from app.models.user import User
from app.auth import get_current_user

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
    user: User = Depends(get_current_user),
):
    """List semua daily snapshots untuk post tertentu."""
    query = db.query(Snapshot).filter(Snapshot.post_id == post_id)

    if date_from:
        query = query.filter(Snapshot.recorded_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Snapshot.recorded_at <= datetime.combine(date_to, datetime.max.time()))

    return query.order_by(Snapshot.recorded_at.desc()).all()


@router.get("/brands/{brand_id}/stats", response_model=BrandStats)
def brand_stats(brand_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
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


class BrandDailySnapshot(BaseModel):
    date: str
    views: int
    likes: int
    comments: int
    shares: int
    delta_views: int
    delta_likes: int
    delta_comments: int
    delta_shares: int


@router.get("/brands/{brand_id}/stats/daily", response_model=list[BrandDailySnapshot])
def brand_daily_stats(
    brand_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Daily aggregated stats per brand — mirip tabel snapshot per post,
    tapi di-SUM dari semua post aktif brand tersebut per tanggal.
    Delta dihitung dari selisih total hari ini vs hari sebelumnya.
    """
    from sqlalchemy import cast, Date

    # Get all active post IDs for this brand
    active_posts = db.query(Post.id).filter(
        Post.brand_id == brand_id, Post.is_active == True
    ).all()

    if not active_posts:
        return []

    post_ids = [p.id for p in active_posts]

    # Aggregate snapshots by date: SUM views/likes/comments/shares per day
    # Use the latest snapshot per post per day (in case multiple scrapes in a day)
    from sqlalchemy.orm import aliased
    from sqlalchemy import text

    # Subquery: get the latest snapshot per post per day
    latest_per_day = (
        db.query(
            cast(Snapshot.recorded_at, Date).label("snap_date"),
            Snapshot.post_id,
            func.max(Snapshot.recorded_at).label("max_recorded"),
        )
        .filter(Snapshot.post_id.in_(post_ids))
        .group_by(cast(Snapshot.recorded_at, Date), Snapshot.post_id)
        .subquery()
    )

    # Join back to get the actual metric values from the latest snapshot per post per day
    rows = (
        db.query(
            latest_per_day.c.snap_date,
            func.sum(Snapshot.views).label("total_views"),
            func.sum(Snapshot.likes).label("total_likes"),
            func.sum(Snapshot.comments).label("total_comments"),
            func.sum(Snapshot.shares).label("total_shares"),
        )
        .join(
            Snapshot,
            and_(
                Snapshot.post_id == latest_per_day.c.post_id,
                Snapshot.recorded_at == latest_per_day.c.max_recorded,
            ),
        )
        .group_by(latest_per_day.c.snap_date)
        .order_by(latest_per_day.c.snap_date.asc())
        .all()
    )

    # Build result with deltas (current day vs previous day)
    result = []
    for i, row in enumerate(rows):
        if i == 0:
            dv, dl, dc, ds = 0, 0, 0, 0
        else:
            prev = rows[i - 1]
            dv = row.total_views - prev.total_views
            dl = row.total_likes - prev.total_likes
            dc = row.total_comments - prev.total_comments
            ds = row.total_shares - prev.total_shares

        result.append(BrandDailySnapshot(
            date=row.snap_date.isoformat(),
            views=row.total_views,
            likes=row.total_likes,
            comments=row.total_comments,
            shares=row.total_shares,
            delta_views=dv,
            delta_likes=dl,
            delta_comments=dc,
            delta_shares=ds,
        ))

    # Limit to last N days
    return result[-days:]


@router.get("/compare")
def compare_posts(
    post_ids: str = Query(..., description="Comma-separated post UUIDs"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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
