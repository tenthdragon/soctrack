-- Migration: Add Instagram support
-- Adds 'platform' and 'thumbnail_url' columns to posts table

-- Add platform column (default 'tiktok' for existing posts)
ALTER TABLE posts ADD COLUMN IF NOT EXISTS platform VARCHAR(20) NOT NULL DEFAULT 'tiktok';

-- Add thumbnail_url column
ALTER TABLE posts ADD COLUMN IF NOT EXISTS thumbnail_url TEXT;

-- Update the unique constraint to be platform-aware
-- (shortcodes from IG and video IDs from TikTok won't collide in practice,
--  but this makes it explicit)
-- DROP CONSTRAINT IF EXISTS uq_posts_tiktok_video_id;
-- ALTER TABLE posts ADD CONSTRAINT uq_posts_platform_video_id UNIQUE (platform, tiktok_video_id);
