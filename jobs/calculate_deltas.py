"""
Cron Job: Calculate Daily Deltas
Schedule: 0 3 * * * (setiap hari jam 03:00 WIB)

Hitung selisih antara snapshot hari ini dan kemarin untuk semua posts.
Generate summary log: berapa post berhasil, berapa gagal, error patterns.
"""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, and_
from app.database import SessionLocal
from app.models.post import Post
from app.models.snapshot import Snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("soctrack.jobs.calculate_deltas")


def run():
    logger.info("=== Delta Calculation Started ===")
    db = SessionLocal()

    try:
        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)

        active_posts = db.query(Post).filter(Post.is_active == True).all()
        logger.info(f"Processing deltas for {len(active_posts)} active posts")

        posts_with_data = 0
        posts_missing = 0
        notable_gains = []

        for post in active_posts:
            # Get today's snapshot
            today_snap = (
                db.query(Snapshot)
                .filter(
                    Snapshot.post_id == post.id,
                    func.date(Snapshot.recorded_at) == today,
                )
                .order_by(Snapshot.recorded_at.desc())
                .first()
            )

            # Get yesterday's snapshot
            yesterday_snap = (
                db.query(Snapshot)
                .filter(
                    Snapshot.post_id == post.id,
                    func.date(Snapshot.recorded_at) == yesterday,
                )
                .order_by(Snapshot.recorded_at.desc())
                .first()
            )

            if not today_snap:
                posts_missing += 1
                continue

            posts_with_data += 1

            if yesterday_snap:
                delta_views = today_snap.views - yesterday_snap.views
                delta_likes = today_snap.likes - yesterday_snap.likes
                delta_comments = today_snap.comments - yesterday_snap.comments
                delta_shares = today_snap.shares - yesterday_snap.shares

                # Track notable gains (>10K views in a day)
                if delta_views > 10000:
                    notable_gains.append({
                        "post_id": str(post.id),
                        "title": post.title or "Untitled",
                        "delta_views": delta_views,
                        "delta_likes": delta_likes,
                    })

        # Summary log
        logger.info(f"Posts with today's data: {posts_with_data}")
        logger.info(f"Posts missing today's snapshot: {posts_missing}")

        if notable_gains:
            logger.info(f"Notable gains (>10K views/day):")
            for g in notable_gains:
                logger.info(
                    f"  → {g['title'][:50]}: +{g['delta_views']:,} views, +{g['delta_likes']:,} likes"
                )

        logger.info("=== Delta Calculation Complete ===")

    finally:
        db.close()


if __name__ == "__main__":
    run()
