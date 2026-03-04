"""
Batch Sync Engine — Smart metrics update for all tracked posts.

Key optimization: groups posts by platform + profile, then:
- Instagram: 1 API call per profile → updates ALL tracked posts from that profile
- TikTok: 1 browser session → sequential visits with short delays

This replaces the old approach of launching 1 browser per post.
"""

import re
import uuid
import asyncio
import logging
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.post import Post
from app.models.snapshot import Snapshot
from app.models.scrape_log import ScrapeLog

logger = logging.getLogger("soctrack.sync")


@dataclass
class SyncResult:
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def done(self):
        return self.success + self.failed + self.skipped


def _upsert_snapshot(db: Session, post_id: uuid.UUID, views: int, likes: int, comments: int, shares: int):
    """Insert or update snapshot for today. Keeps baseline on same-day update."""
    from sqlalchemy import cast, Date
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
    else:
        db.add(Snapshot(
            post_id=post_id,
            views=views,
            likes=likes,
            comments=comments,
            shares=shares,
            baseline_views=views,
            baseline_likes=likes,
            baseline_comments=comments,
            baseline_shares=shares,
            recorded_at=datetime.utcnow(),
        ))


def _extract_ig_username(url: str) -> str | None:
    """Extract Instagram username from a post/profile URL."""
    # For profile URLs: instagram.com/username/
    # For post URLs: we stored them as instagram.com/p/shortcode/ — no username
    # But the owner info might be in the post data
    match = re.search(r'instagram\.com/([A-Za-z0-9_.]+)', url)
    if match:
        name = match.group(1)
        if name not in ("p", "reel", "tv", "stories", "explore", "accounts", "api"):
            return name
    return None


async def sync_brand(db: Session, brand_id: uuid.UUID, on_progress=None) -> SyncResult:
    """
    Smart sync for all active posts in a brand.
    Groups by platform, then uses optimal strategy per platform.

    Args:
        db: SQLAlchemy session
        brand_id: Brand to sync
        on_progress: Optional callback(done, total) for progress tracking
    """
    posts = (
        db.query(Post)
        .filter(Post.brand_id == brand_id, Post.is_active == True)
        .all()
    )

    result = SyncResult(total=len(posts))
    if not posts:
        return result

    # Group by platform
    ig_posts = [p for p in posts if p.platform == "instagram"]
    tiktok_posts = [p for p in posts if p.platform == "tiktok"]

    logger.info(
        f"Sync brand {brand_id}: {len(ig_posts)} IG + {len(tiktok_posts)} TikTok = {len(posts)} total"
    )

    # ── INSTAGRAM: Group by profile, 1 API call per profile ──
    if ig_posts:
        await _sync_instagram_posts(db, ig_posts, result, on_progress)

    # ── TIKTOK: Single browser, sequential visits ──
    if tiktok_posts:
        await _sync_tiktok_posts(db, tiktok_posts, result, on_progress)

    logger.info(
        f"Sync complete: {result.success} success, {result.failed} failed, "
        f"{result.skipped} skipped out of {result.total}"
    )
    return result


async def _sync_instagram_posts(db: Session, posts: list, result: SyncResult, on_progress=None):
    """Sync all Instagram posts using profile-level batch fetching."""
    from scraper.instagram import InstagramScraper

    # Group posts by username (extracted from URL or stored data)
    # Since IG posts might not have username in URL (/p/shortcode/),
    # we need to group them. For now, try to extract from brand or URL.
    profiles: dict[str, list] = defaultdict(list)
    no_profile: list = []

    for post in posts:
        username = _extract_ig_username(post.tiktok_url)
        if username:
            profiles[username].append(post)
        else:
            no_profile.append(post)

    # If we can't group by username (posts stored as /p/shortcode/),
    # try to find the brand's associated username
    if no_profile and profiles:
        # Assign to the first known profile
        default_username = next(iter(profiles))
        profiles[default_username].extend(no_profile)
        no_profile = []

    scraper = InstagramScraper()
    try:
        await scraper.start()

        for username, profile_posts in profiles.items():
            start_time = datetime.utcnow()
            tracked_shortcodes = {p.tiktok_video_id for p in profile_posts}

            try:
                # ONE API call → metrics for all tracked posts
                metrics_map = await scraper.sync_profile_posts(username, tracked_shortcodes)

                for post in profile_posts:
                    shortcode = post.tiktok_video_id
                    if shortcode in metrics_map:
                        m = metrics_map[shortcode]
                        _upsert_snapshot(db, post.id, m.views, m.likes, m.comments, m.shares)

                        # Update title/thumbnail if missing
                        if not post.title and m.title:
                            post.title = m.title
                        if not post.thumbnail_url and m.thumbnail_url:
                            post.thumbnail_url = m.thumbnail_url
                        if not post.posted_at and m.posted_at:
                            post.posted_at = m.posted_at

                        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                        db.add(ScrapeLog(post_id=post.id, status="success", duration_ms=duration_ms))
                        result.success += 1
                    else:
                        # Post not in profile's recent posts (too old?)
                        db.add(ScrapeLog(
                            post_id=post.id,
                            status="success",
                            error_message="Not in profile's recent posts",
                        ))
                        result.skipped += 1

                db.commit()
                logger.info(
                    f"IG @{username}: synced {len(metrics_map)}/{len(profile_posts)} posts "
                    f"in {(datetime.utcnow() - start_time).total_seconds():.1f}s"
                )

            except Exception as e:
                for post in profile_posts:
                    db.add(ScrapeLog(
                        post_id=post.id, status="failed", error_message=str(e)
                    ))
                    result.failed += 1
                db.commit()
                logger.error(f"IG @{username} sync failed: {e}")

            if on_progress:
                on_progress(result.done, result.total)

        # Handle posts that couldn't be grouped (fallback: individual scrape)
        for post in no_profile:
            try:
                metrics = await scraper.scrape_post(post.tiktok_url)
                _upsert_snapshot(db, post.id, metrics.views, metrics.likes, metrics.comments, 0)
                db.add(ScrapeLog(post_id=post.id, status="success"))
                result.success += 1
            except Exception as e:
                db.add(ScrapeLog(post_id=post.id, status="failed", error_message=str(e)))
                result.failed += 1
            db.commit()
            if on_progress:
                on_progress(result.done, result.total)

    finally:
        await scraper.stop()


async def _sync_tiktok_posts(db: Session, posts: list, result: SyncResult, on_progress=None, quick=False):
    """Sync all TikTok posts using a single browser session.

    Args:
        quick: If True, use minimal delays (for user-initiated scraping).
               If False, use longer delays (for nightly cron to avoid rate-limits).
    """
    from scraper.tiktok import TikTokScraper
    from scraper.anti_detect import random_delay

    scraper = TikTokScraper()
    try:
        await scraper.start()

        for i, post in enumerate(posts):
            start_time = datetime.utcnow()
            logger.info(f"[TikTok {i+1}/{len(posts)}] {post.tiktok_url}")

            try:
                metrics = await asyncio.wait_for(
                    scraper.scrape_post(post.tiktok_url),
                    timeout=60  # 60 second max per post
                )
                _upsert_snapshot(db, post.id, metrics.views, metrics.likes, metrics.comments, metrics.shares)

                if not post.title and metrics.title:
                    post.title = metrics.title
                if metrics.video_id and post.tiktok_video_id.startswith("pending"):
                    post.tiktok_video_id = metrics.video_id

                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                db.add(ScrapeLog(post_id=post.id, status="success", duration_ms=duration_ms))
                result.success += 1

            except asyncio.TimeoutError:
                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                db.add(ScrapeLog(
                    post_id=post.id, status="failed",
                    error_message="Timeout after 60s", duration_ms=duration_ms,
                ))
                result.failed += 1
                logger.warning(f"  Timeout after 60s, skipping")

            except Exception as e:
                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                db.add(ScrapeLog(
                    post_id=post.id, status="failed",
                    error_message=str(e), duration_ms=duration_ms,
                ))
                result.failed += 1
                logger.error(f"  Failed: {e}")

            db.commit()
            if on_progress:
                on_progress(result.done, result.total)

            # Delay between posts to avoid rate-limiting
            if i < len(posts) - 1:
                if quick:
                    await random_delay(2, 4)   # User is waiting — minimal delay
                else:
                    await random_delay(5, 15)  # Nightly cron — safer delay

    finally:
        await scraper.stop()


async def sync_all_brands(db: Session) -> dict:
    """
    Sync all brands. Used by the nightly cron job.
    Returns summary dict.
    """
    from app.models.brand import Brand

    brands = db.query(Brand).all()
    total_result = SyncResult()

    for brand in brands:
        logger.info(f"=== Syncing brand: {brand.name} ===")
        brand_result = await sync_brand(db, brand.id)
        total_result.total += brand_result.total
        total_result.success += brand_result.success
        total_result.failed += brand_result.failed
        total_result.skipped += brand_result.skipped

    return {
        "brands": len(brands),
        "total": total_result.total,
        "success": total_result.success,
        "failed": total_result.failed,
        "skipped": total_result.skipped,
    }
