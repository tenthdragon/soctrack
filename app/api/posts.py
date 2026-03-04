"""Post management endpoints."""

import uuid
import re
import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.post import Post
from app.models.brand import Brand
from app.models.snapshot import Snapshot
from app.models.scrape_log import ScrapeLog

logger = logging.getLogger("soctrack.api.posts")

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────

class PostAddByLink(BaseModel):
    url: str  # works for both TikTok and Instagram
    brand_id: Optional[uuid.UUID] = None
    # Keep backward compat
    tiktok_url: Optional[str] = None

    def get_url(self) -> str:
        return self.url or self.tiktok_url or ""


class PostAddByAccount(BaseModel):
    tiktok_username: str
    brand_id: uuid.UUID


class PostResponse(BaseModel):
    id: uuid.UUID
    brand_id: uuid.UUID
    platform: str = "tiktok"
    tiktok_url: str
    tiktok_video_id: str
    title: Optional[str]
    thumbnail_url: Optional[str] = None
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


# ── Platform Detection ────────────────────────────────────

def detect_platform(url: str) -> str:
    """Detect whether URL is TikTok or Instagram."""
    if re.search(r'instagram\.com/', url, re.IGNORECASE):
        return "instagram"
    return "tiktok"


def extract_ig_shortcode(url: str) -> Optional[str]:
    """Extract shortcode from Instagram URL (/p/XXX/ or /reel/XXX/)."""
    match = re.search(r'/(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
    return match.group(1) if match else None


def extract_ig_username(url: str) -> Optional[str]:
    """Extract username from Instagram URL."""
    match = re.search(r'instagram\.com/([A-Za-z0-9_.]+)', url)
    if match:
        username = match.group(1)
        # Filter out known paths
        if username not in ("p", "reel", "tv", "stories", "explore", "accounts", "api"):
            return username
    return None


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


def _upsert_snapshot(db: Session, post_id: uuid.UUID, views: int, likes: int, comments: int, shares: int):
    """
    Insert or update snapshot for today's date.
    If a snapshot already exists for the same post on the same date, update it.
    Otherwise create a new one.
    """
    from sqlalchemy import func, cast, Date
    today = datetime.utcnow().date()

    existing = (
        db.query(Snapshot)
        .filter(
            Snapshot.post_id == post_id,
            cast(Snapshot.recorded_at, Date) == today,
        )
        .first()
    )

    if existing:
        existing.views = views
        existing.likes = likes
        existing.comments = comments
        existing.shares = shares
        existing.recorded_at = datetime.utcnow()
        logger.debug(f"Updated existing snapshot for post {post_id} on {today}")
        return existing
    else:
        snapshot = Snapshot(
            post_id=post_id,
            views=views,
            likes=likes,
            comments=comments,
            shares=shares,
            recorded_at=datetime.utcnow(),
        )
        db.add(snapshot)
        logger.debug(f"Created new snapshot for post {post_id} on {today}")
        return snapshot


async def _scrape_tiktok_and_save(post_id: uuid.UUID, url: str):
    """Background task: scrape a single TikTok post and save snapshot."""
    from scraper.tiktok import TikTokScraper
    from app.database import SessionLocal

    db = SessionLocal()
    scraper = TikTokScraper()
    try:
        await scraper.start()
        metrics = await scraper.scrape_post(url)

        _upsert_snapshot(db, post_id, metrics.views, metrics.likes, metrics.comments, metrics.shares)

        post = db.query(Post).filter(Post.id == post_id).first()
        if post and not post.title and metrics.title:
            post.title = metrics.title
        if post and metrics.video_id and post.tiktok_video_id == "pending":
            post.tiktok_video_id = metrics.video_id
            post.tiktok_url = f"https://www.tiktok.com/@{metrics.author}/video/{metrics.video_id}"

        db.add(ScrapeLog(post_id=post_id, status="success"))
        db.commit()
        logger.info(f"Scraped TikTok post {post_id}: views={metrics.views}")
    except Exception as e:
        db.add(ScrapeLog(post_id=post_id, status="failed", error_message=str(e)))
        db.commit()
        logger.error(f"Failed to scrape TikTok post {post_id}: {e}")
    finally:
        await scraper.stop()
        db.close()


async def _scrape_instagram_and_save(post_id: uuid.UUID, url: str):
    """Background task: scrape a single Instagram post and save snapshot."""
    from scraper.instagram import InstagramScraper
    from app.database import SessionLocal

    db = SessionLocal()
    scraper = InstagramScraper()
    try:
        await scraper.start()
        metrics = await scraper.scrape_post(url)

        _upsert_snapshot(db, post_id, metrics.views, metrics.likes, metrics.comments, metrics.shares)

        post = db.query(Post).filter(Post.id == post_id).first()
        if post:
            if not post.title and metrics.title:
                post.title = metrics.title
            if metrics.shortcode and post.tiktok_video_id == "pending":
                post.tiktok_video_id = metrics.shortcode
                post.tiktok_url = f"https://www.instagram.com/p/{metrics.shortcode}/"
            if metrics.thumbnail_url and not post.thumbnail_url:
                post.thumbnail_url = metrics.thumbnail_url
            if metrics.posted_at and not post.posted_at:
                post.posted_at = metrics.posted_at

        db.add(ScrapeLog(post_id=post_id, status="success"))
        db.commit()
        logger.info(f"Scraped IG post {post_id}: likes={metrics.likes}, views={metrics.views}")
    except Exception as e:
        db.add(ScrapeLog(post_id=post_id, status="failed", error_message=str(e)))
        db.commit()
        logger.error(f"Failed to scrape IG post {post_id}: {e}")
    finally:
        await scraper.stop()
        db.close()


async def _scrape_ig_profile_and_save(brand_id: uuid.UUID, username: str):
    """Background task: scrape Instagram profile and auto-add all discovered posts."""
    from scraper.instagram import InstagramScraper
    from app.database import SessionLocal

    db = SessionLocal()
    scraper = InstagramScraper()
    try:
        await scraper.start()
        profile_info, discovered = await scraper.discover_profile(username)

        added = 0
        for post_data in discovered:
            # Check duplicate
            existing = db.query(Post).filter(
                Post.tiktok_video_id == post_data.shortcode
            ).first()
            if existing:
                continue

            post = Post(
                brand_id=brand_id,
                platform="instagram",
                tiktok_url=post_data.url,
                tiktok_video_id=post_data.shortcode,
                title=post_data.title,
                thumbnail_url=post_data.thumbnail_url,
                posted_at=post_data.posted_at,
                source="discovery",
            )
            db.add(post)
            db.flush()

            # Save initial snapshot with the metrics from profile
            _upsert_snapshot(db, post.id, post_data.views, post_data.likes, post_data.comments, 0)
            added += 1

        db.commit()
        logger.info(
            f"IG profile @{username}: discovered {len(discovered)} posts, added {added} new"
        )
    except Exception as e:
        logger.error(f"Failed to scrape IG profile @{username}: {e}")
    finally:
        await scraper.stop()
        db.close()


# ── Endpoints ────────────────────────────────────────────

@router.get("/brands/{brand_id}/posts", response_model=list[PostResponse])
def list_posts(brand_id: uuid.UUID, db: Session = Depends(get_db)):
    """List semua tracked posts untuk brand tertentu."""
    return (
        db.query(Post)
        .filter(Post.brand_id == brand_id, Post.is_active == True)
        .all()
    )


@router.post("/posts/add-by-link", status_code=201)
def add_post_by_link(
    data: PostAddByLink,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Tambah post by URL (TikTok or Instagram) dan langsung scrape."""
    url = data.get_url()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    platform = detect_platform(url)

    if platform == "instagram":
        # Check if it's a profile URL (no /p/ or /reel/) → auto-discover mode
        shortcode = extract_ig_shortcode(url)
        ig_username = extract_ig_username(url)

        if not shortcode and ig_username:
            # It's a profile URL — trigger profile discovery
            brand_id = data.brand_id
            if not brand_id:
                raise HTTPException(
                    status_code=400,
                    detail="brand_id is required for Instagram profile discovery",
                )
            background_tasks.add_task(_scrape_ig_profile_and_save, brand_id, ig_username)
            return {
                "message": f"Instagram profile discovery started for @{ig_username}",
                "mode": "profile_discovery",
            }

        if not shortcode:
            raise HTTPException(
                status_code=400,
                detail="Could not extract post shortcode from Instagram URL",
            )

        post_id_str = shortcode

        # Check duplicate
        existing = db.query(Post).filter(Post.tiktok_video_id == shortcode).first()
        if existing:
            raise HTTPException(status_code=409, detail="Post already being tracked")

        brand_id = data.brand_id
        if not brand_id:
            raise HTTPException(
                status_code=400,
                detail="brand_id is required for Instagram posts",
            )

        post = Post(
            brand_id=brand_id,
            platform="instagram",
            tiktok_url=url,
            tiktok_video_id=shortcode,
            source="link",
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        background_tasks.add_task(_scrape_instagram_and_save, post.id, url)
        return {"message": "Instagram post added and scraping started", "post_id": str(post.id)}

    else:
        # TikTok flow (existing logic)
        try:
            video_id = extract_video_id(url)
        except ValueError:
            video_id = "pending"

        if video_id != "pending":
            existing = db.query(Post).filter(Post.tiktok_video_id == video_id).first()
            if existing:
                raise HTTPException(status_code=409, detail="Post already being tracked")

        brand_id = data.brand_id
        if not brand_id:
            username = extract_username(url)
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
            platform="tiktok",
            tiktok_url=url,
            tiktok_video_id=video_id,
            source="link",
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        background_tasks.add_task(_scrape_tiktok_and_save, post.id, url)
        return {"message": "Post added and scraping started", "post_id": str(post.id)}


@router.post("/posts/{post_id}/scrape", status_code=202)
def scrape_post_now(
    post_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger immediate scrape for a specific post."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.platform == "instagram":
        background_tasks.add_task(_scrape_instagram_and_save, post.id, post.tiktok_url)
    else:
        background_tasks.add_task(_scrape_tiktok_and_save, post.id, post.tiktok_url)

    return {"message": "Scraping started", "post_id": str(post.id)}


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
