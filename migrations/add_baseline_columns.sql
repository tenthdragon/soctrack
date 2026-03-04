-- Add baseline columns to snapshots for intra-day delta tracking
-- Baseline = angka awal saat pertama kali di-scrape hari itu
-- Delta hari ini = views - baseline_views

ALTER TABLE snapshots ADD COLUMN IF NOT EXISTS baseline_views BIGINT NOT NULL DEFAULT 0;
ALTER TABLE snapshots ADD COLUMN IF NOT EXISTS baseline_likes BIGINT NOT NULL DEFAULT 0;
ALTER TABLE snapshots ADD COLUMN IF NOT EXISTS baseline_comments INTEGER NOT NULL DEFAULT 0;
ALTER TABLE snapshots ADD COLUMN IF NOT EXISTS baseline_shares INTEGER NOT NULL DEFAULT 0;

-- Backfill: set baseline = current values for existing snapshots
-- (karena kita tidak punya data awal, anggap baseline = current)
UPDATE snapshots SET
    baseline_views = views,
    baseline_likes = likes,
    baseline_comments = comments,
    baseline_shares = shares
WHERE baseline_views = 0 AND views > 0;
