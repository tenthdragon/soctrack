"""
Cron Job: Account Discovery
Schedule: 0 0 * * * (setiap hari jam 00:00 WIB)

Cek semua brands dengan auto_discover=True.
Visit profile page masing-masing, cari post baru yang belum di-track.
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models.brand import Brand
from app.models.post import Post
from app.models.scrape_log import ScrapeLog
from app.config import settings
from scraper.tiktok import TikTokScraper
from scraper.anti_detect import random_delay

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("soctrack.jobs.account_discover")


async def run():
    logger.info("=== Account Discovery Job Started ===")
    db = SessionLocal()
    scraper = TikTokScraper(
        proxy_url=settings.proxy_url if settings.proxy_enabled else None
    )

    try:
        await scraper.start()

        # Get all brands with auto_discover enabled
        brands = (
            db.query(Brand)
            .filter(Brand.auto_discover == True, Brand.tiktok_username.isnot(None))
            .all()
        )
        logger.info(f"Found {len(brands)} brands with auto-discover enabled")

        total_new = 0
        for brand in brands:
            start_time = datetime.utcnow()
            try:
                logger.info(f"Discovering posts for {brand.tiktok_username} ({brand.name})")
                discovered = await scraper.discover_account(brand.tiktok_username)

                # Filter out already-tracked posts
                new_count = 0
                for post_data in discovered:
                    existing = (
                        db.query(Post)
                        .filter(Post.tiktok_video_id == post_data.video_id)
                        .first()
                    )
                    if not existing:
                        post = Post(
                            brand_id=brand.id,
                            tiktok_url=post_data.url,
                            tiktok_video_id=post_data.video_id,
                            title=post_data.title,
                            source="account",
                        )
                        db.add(post)
                        new_count += 1

                db.commit()
                total_new += new_count
                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

                db.add(ScrapeLog(
                    status="success",
                    error_message=f"Discovered {new_count} new posts for {brand.name}",
                    duration_ms=duration_ms,
                ))
                db.commit()

                logger.info(f"  → {new_count} new posts added for {brand.name}")

                # Random delay between accounts
                await random_delay(10, 30)

            except Exception as e:
                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                db.add(ScrapeLog(
                    status="failed",
                    error_message=f"Account discover failed for {brand.name}: {str(e)}",
                    duration_ms=duration_ms,
                ))
                db.commit()
                logger.error(f"  → Failed for {brand.name}: {e}")

        logger.info(f"=== Account Discovery Complete: {total_new} new posts total ===")

    finally:
        await scraper.stop()
        db.close()


if __name__ == "__main__":
    asyncio.run(run())
