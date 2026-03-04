"""
CSS Selectors config for TikTok scraping.

Disimpan terpisah agar mudah di-update jika TikTok ubah layout HTML.
Cukup update file ini tanpa mengubah core scraping logic.
"""

# ── Post Page Selectors ──────────────────────────────────

POST_PAGE = {
    # Metrics visible on public post page
    "views": '[data-e2e="video-views"]',
    "likes": '[data-e2e="like-count"]',
    "comments": '[data-e2e="comment-count"]',
    "shares": '[data-e2e="share-count"]',

    # Post metadata
    "title": '[data-e2e="video-desc"]',
    "author": '[data-e2e="video-author-uniqueid"]',
    "date": '[data-e2e="browser-nickname"] span',

    # Video element (untuk wait hingga page loaded)
    "video_player": '[data-e2e="video-player"]',
}

# ── Profile Page Selectors ───────────────────────────────

PROFILE_PAGE = {
    # Video grid pada profile page
    "video_items": '[data-e2e="user-post-item"]',
    "video_links": '[data-e2e="user-post-item"] a',

    # Profile info
    "display_name": '[data-e2e="user-subtitle"]',
    "follower_count": '[data-e2e="followers-count"]',
    "following_count": '[data-e2e="following-count"]',
    "likes_count": '[data-e2e="likes-count"]',
}

# ── Search Page Selectors ────────────────────────────────

SEARCH_PAGE = {
    # Search results
    "video_cards": '[data-e2e="search_video-item"]',
    "video_links": '[data-e2e="search_video-item"] a',
    "video_views": '[data-e2e="search-card-like-container"]',

    # Tabs
    "tab_videos": '[data-e2e="search_videos-tab"]',
}

# ── Wait Conditions ──────────────────────────────────────

WAIT = {
    "page_load_timeout": 30000,  # 30 seconds
    "element_timeout": 15000,    # 15 seconds
    "navigation_timeout": 30000,
}
