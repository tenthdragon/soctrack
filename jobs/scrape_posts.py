"""
Cron Job: Nightly Post Metrics Scrape
Schedule: 30 0 * * * (setiap hari jam 00:30 WIB)

Visit semua tracked posts (staggered) dan catat metrics snapshot.
~250-350 posts dengan delay 30-90 detik antar post.
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models.post import Post
from app.models.snapshot import Snapshot
from app.models.scrape_log import ScrapeLog
from app.config import settings
from scraper.tiktok import TikTokScraper
from scraper.anti_detect import random_delay

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("soctrack.jobs.scrape_posts")


async def run():
    logger.info("=== Nightly Metrics Scrape Started ===")
    db = SessionLocal()
    scraper = TikTokScraper(
        proxy_url=settings.proxy_url if settings.proxy_enabled else None
    )

    try:
        await scraper.start()

        # Get all active tracked posts
        active_posts = (
            db.query(Post)
            .filter(Post.is_active == True)
            .limit(settings.scrape_max_posts_per_cycle)
            .all()
        )
        logger.info(f"Found {len(active_posts)} active posts to scrape")

        success_count = 0
        fail_count = 0

        for i, post in enumerate(active_posts):
            start_time = datetime.utcnow()
            logger.info(f"[{i+1}/{len(active_posts)}] Scraping: {post.tiktok_url}")

            try:
                metrics = await scraper.scrape_post(post.tiktok_url)

                # Save snapshot
                snapshot = Snapshot(
                    post_id=post.id,
                    views=metrics.views,
                    likes=metrics.likes,
                    comments=metrics.comments,
                    shares=metrics.shares,
                    recorded_at=datetime.utcnow(),
                )
                db.add(snapshot)

                # Update post title if empty
                if not post.title and metrics.title:
                    post.title = metrics.title

                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                db.add(ScrapeLog(
                    post_id=post.id,
                    status="success",
                    duration_ms=duration_ms,
                ))
                db.commit()
                success_count += 1

            except Exception as e:
                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                db.add(ScrapeLog(
                    post_id=post.id,
                    status="failed",
                    error_message=str(e),
                    duration_ms=duration_ms,
                ))
                db.commit()
                fail_count += 1
                logger.error(f"  → Failed: {e}")

            # Staggered delay
            delay = await random_delay(settings.scrape_delay_min, settings.scrape_delay_max)
            logger.debug(f"  → Waiting {delay:.0f}s before next post")

        total = success_count + fail_count
        rate = (success_count / total * 100) if total > 0 else 0
        logger.info(
            f"=== Nightly Scrape Complete: {success_count}/{total} success ({rate:.1f}%) ==="
        )

        if rate < 90:
            logger.warning(f"⚠️ Success rate below 90%: {rate:.1f}%. Review scrape logs.")

    finally:
        await scraper.stop()
        db.close()


if __name__ == "__main__":
    asyncio.run(run())
