"""
Cron Job: Nightly Batch Sync (replaces scrape_posts.py)
Schedule: 30 0 * * * (setiap hari jam 00:30 WIB)

Uses profile-level batch sync:
- Instagram: 1 API call per profile → updates ALL tracked posts
- TikTok: 1 browser session → sequential visits with short delays

Much faster than the old approach of 1 browser per post.
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from scraper.batch_sync import sync_all_brands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("soctrack.jobs.daily_sync")


async def run():
    start = datetime.utcnow()
    logger.info("=== Nightly Batch Sync Started ===")

    db = SessionLocal()
    try:
        summary = await sync_all_brands(db)

        duration = (datetime.utcnow() - start).total_seconds()
        rate = (
            (summary["success"] / summary["total"] * 100)
            if summary["total"] > 0 else 0
        )

        logger.info(
            f"=== Nightly Sync Complete in {duration:.0f}s ===\n"
            f"  Brands: {summary['brands']}\n"
            f"  Total posts: {summary['total']}\n"
            f"  Success: {summary['success']}\n"
            f"  Failed: {summary['failed']}\n"
            f"  Skipped: {summary['skipped']}\n"
            f"  Success rate: {rate:.1f}%"
        )

        if rate < 90 and summary["total"] > 0:
            logger.warning(f"Success rate below 90%: {rate:.1f}%. Check scrape logs.")

    except Exception as e:
        logger.error(f"Nightly sync failed: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(run())
