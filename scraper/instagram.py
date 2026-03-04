"""
Instagram scraping logic using Playwright.

Approach: Navigate to Instagram profile page, then use fetch() from within
the page context to call Instagram's internal API (web_profile_info).
This works because the fetch inherits the page's cookies/session.

For individual posts, we extract metrics from the profile API response
(which includes the latest 12 posts), or scrape the post page directly
using embedded JSON data.
"""

import json
import re
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from playwright.async_api import async_playwright, BrowserContext

from scraper.anti_detect import get_browser_context_options, random_delay

logger = logging.getLogger("soctrack.scraper.instagram")

IG_APP_ID = "936619743392459"


@dataclass
class IGPostMetrics:
    """Metrics extracted from a single Instagram post."""
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0  # not available from IG, always 0
    saves: int = 0   # not available from public API
    title: Optional[str] = None
    author: Optional[str] = None
    shortcode: Optional[str] = None
    thumbnail_url: Optional[str] = None
    is_video: bool = False
    posted_at: Optional[datetime] = None


@dataclass
class IGDiscoveredPost:
    """Post found during Instagram profile scrape."""
    url: str
    shortcode: str
    post_type: str  # GraphImage, GraphVideo, GraphSidecar
    likes: int = 0
    comments: int = 0
    views: int = 0  # only for videos
    title: Optional[str] = None
    thumbnail_url: Optional[str] = None
    posted_at: Optional[datetime] = None


class InstagramScraper:
    """Headless browser scraper for Instagram public pages."""

    def __init__(self, proxy_url: Optional[str] = None):
        self.proxy_url = proxy_url
        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self._ig_page = None  # Keep a page on Instagram for API calls

    async def start(self):
        """Launch browser and load Instagram."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        options = get_browser_context_options(self.proxy_url)
        self._context = await self._browser.new_context(**options)
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {} };
        """)

        # Load Instagram homepage to establish session
        self._ig_page = await self._context.new_page()
        await self._ig_page.goto(
            "https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000
        )
        await self._ig_page.wait_for_timeout(3000)
        logger.info("Instagram scraper started")

    async def stop(self):
        """Close browser and cleanup."""
        if self._ig_page:
            await self._ig_page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Instagram scraper stopped")

    async def _fetch_profile_data(self, username: str) -> dict:
        """
        Fetch profile data using Instagram's internal API from within page context.
        Returns the full user data dict.
        """
        clean_username = username.lstrip("@")
        result = await self._ig_page.evaluate(f"""
            async () => {{
                try {{
                    const resp = await fetch(
                        '/api/v1/users/web_profile_info/?username={clean_username}',
                        {{
                            headers: {{
                                'X-IG-App-ID': '{IG_APP_ID}',
                                'X-Requested-With': 'XMLHttpRequest',
                            }}
                        }}
                    );
                    const text = await resp.text();
                    return {{ status: resp.status, body: text }};
                }} catch(e) {{
                    return {{ error: e.message }};
                }}
            }}
        """)

        if result.get("error"):
            raise Exception(f"Instagram API error: {result['error']}")

        if result.get("status") != 200:
            raise Exception(f"Instagram API returned status {result.get('status')}")

        body = json.loads(result["body"])
        user = body.get("data", {}).get("user")
        if not user:
            raise Exception(f"No user data found for @{clean_username}")

        return user

    def _parse_post_node(self, node: dict) -> IGPostMetrics:
        """Parse a post node from Instagram's GraphQL response into metrics."""
        shortcode = node.get("shortcode", "")
        typename = node.get("__typename", "")
        is_video = node.get("is_video", False)

        # Likes can be in different fields
        likes = (
            node.get("edge_liked_by", {}).get("count", 0)
            or node.get("edge_media_preview_like", {}).get("count", 0)
        )
        comments = node.get("edge_media_to_comment", {}).get("count", 0)
        views = node.get("video_view_count", 0) if is_video else 0

        # Caption
        caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
        caption = caption_edges[0]["node"]["text"] if caption_edges else ""

        # Timestamp
        timestamp = node.get("taken_at_timestamp")
        posted_at = datetime.utcfromtimestamp(timestamp) if timestamp else None

        # Thumbnail
        thumbnail = node.get("thumbnail_src") or node.get("display_url", "")

        # Author
        owner = node.get("owner", {})
        author = owner.get("username", "")

        return IGPostMetrics(
            views=views,
            likes=likes,
            comments=comments,
            shares=0,
            title=caption[:500] if caption else "",
            author=author,
            shortcode=shortcode,
            thumbnail_url=thumbnail,
            is_video=is_video,
            posted_at=posted_at,
        )

    # ── Scrape Single Post ───────────────────────────────

    async def scrape_post(self, url: str) -> IGPostMetrics:
        """
        Scrape metrics for a single Instagram post.
        First tries to find it in the profile's recent posts,
        then falls back to visiting the post page directly.
        """
        # Extract shortcode from URL
        shortcode = self._extract_shortcode(url)
        if not shortcode:
            raise ValueError(f"Could not extract shortcode from URL: {url}")

        # Try visiting the post page and extracting embedded data
        page = await self._context.new_page()
        try:
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(4000)

            # Try fetch from page context for the post's embedded data
            result = await page.evaluate(f"""
                async () => {{
                    try {{
                        const resp = await fetch(
                            '/api/v1/media/{shortcode}/web_info/',
                            {{
                                headers: {{
                                    'X-IG-App-ID': '{IG_APP_ID}',
                                    'X-Requested-With': 'XMLHttpRequest',
                                }}
                            }}
                        );
                        if (resp.ok) {{
                            const text = await resp.text();
                            return {{ status: resp.status, body: text }};
                        }}
                    }} catch(e) {{}}

                    // Fallback: try graphql info endpoint
                    try {{
                        const resp2 = await fetch(
                            '/graphql/query/?query_hash=b3055c01b4b222b8a47dc12b090e4e64&variables=' +
                            encodeURIComponent(JSON.stringify({{shortcode: "{shortcode}", child_comment_count: 0, fetch_comment_count: 0, parent_comment_count: 0, has_threaded_comments: true}})),
                            {{
                                headers: {{
                                    'X-IG-App-ID': '{IG_APP_ID}',
                                    'X-Requested-With': 'XMLHttpRequest',
                                }}
                            }}
                        );
                        if (resp2.ok) {{
                            const text2 = await resp2.text();
                            return {{ status: resp2.status, body: text2, source: 'graphql' }};
                        }}
                    }} catch(e) {{}}

                    return {{ error: 'No API endpoint returned data' }};
                }}
            """)

            if result.get("body"):
                body = json.loads(result["body"])

                # Handle media/web_info response
                items = body.get("items", [])
                if items:
                    item = items[0]
                    caption_text = ""
                    caption = item.get("caption")
                    if caption and isinstance(caption, dict):
                        caption_text = caption.get("text", "")

                    return IGPostMetrics(
                        views=item.get("play_count", item.get("view_count", 0)) or 0,
                        likes=item.get("like_count", 0),
                        comments=item.get("comment_count", 0),
                        shares=0,
                        title=caption_text[:500] if caption_text else "",
                        author=item.get("user", {}).get("username", ""),
                        shortcode=shortcode,
                        thumbnail_url=item.get("image_versions2", {}).get("candidates", [{}])[0].get("url", ""),
                        is_video=item.get("media_type") == 2,
                        posted_at=datetime.utcfromtimestamp(item["taken_at"]) if "taken_at" in item else None,
                    )

                # Handle graphql response
                shortcode_media = body.get("data", {}).get("shortcode_media")
                if shortcode_media:
                    return self._parse_post_node(shortcode_media)

            # Final fallback: extract from HTML source
            logger.warning(f"API endpoints failed for /p/{shortcode}/, trying HTML extraction")
            return await self._scrape_post_from_html(page, shortcode)

        finally:
            await page.close()

    async def _scrape_post_from_html(self, page, shortcode: str) -> IGPostMetrics:
        """Extract post metrics from the page HTML/meta tags as fallback."""
        # Try to extract from embedded JSON in page source first
        embedded = await page.evaluate("""
            () => {
                // Look for __additionalDataLoaded or shared data
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                for (const s of scripts) {
                    try {
                        const d = JSON.parse(s.textContent);
                        if (d.interactionStatistic || d.commentCount) return d;
                    } catch(e) {}
                }
                return null;
            }
        """)

        likes = 0
        comments = 0
        author = ""
        caption = ""

        if embedded:
            # LD+JSON format has interactionStatistic array
            for stat in (embedded.get("interactionStatistic") or []):
                itype = stat.get("interactionType", "")
                count = stat.get("userInteractionCount", 0)
                if "Like" in itype:
                    likes = int(count)
                elif "Comment" in itype:
                    comments = int(count)
            author = (embedded.get("author") or {}).get("identifier", {}).get("value", "")
            caption = embedded.get("articleBody") or embedded.get("name") or ""

        # Fallback to meta tags if LD+JSON didn't work
        if likes == 0 and comments == 0:
            og_desc = await page.evaluate("""
                () => {
                    const el = document.querySelector('meta[property="og:description"]');
                    return el ? el.content : '';
                }
            """)

            if og_desc:
                # Case-insensitive, supports formats: "123 likes", "1,234 Likes", "12K likes"
                likes_match = re.search(r'([\d,\.]+[KkMm]?)\s*likes?', og_desc, re.IGNORECASE)
                comments_match = re.search(r'([\d,\.]+[KkMm]?)\s*comments?', og_desc, re.IGNORECASE)
                if likes_match:
                    likes = self._parse_compact_number(likes_match.group(1))
                if comments_match:
                    comments = self._parse_compact_number(comments_match.group(1))

        if not caption:
            og_title = await page.evaluate("""
                () => {
                    const el = document.querySelector('meta[property="og:title"]');
                    return el ? el.content : '';
                }
            """)
            caption = og_title or ""

        return IGPostMetrics(
            likes=likes,
            comments=comments,
            title=caption[:500] if caption else "",
            author=author,
            shortcode=shortcode,
        )

    @staticmethod
    def _parse_compact_number(s: str) -> int:
        """Parse compact numbers like '1.2K', '3.5M', '1,234' into integers."""
        s = s.strip().replace(",", "")
        multiplier = 1
        if s[-1:].upper() == 'K':
            multiplier = 1000
            s = s[:-1]
        elif s[-1:].upper() == 'M':
            multiplier = 1_000_000
            s = s[:-1]
        try:
            return int(float(s) * multiplier)
        except ValueError:
            return 0

    # ── Discover Posts from Profile ───────────────────────

    async def discover_profile(self, username: str) -> tuple[dict, list[IGDiscoveredPost]]:
        """
        Fetch profile and return profile info + list of recent posts.
        Returns (profile_info, discovered_posts).
        """
        user = await self._fetch_profile_data(username)

        profile_info = {
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "biography": user.get("biography"),
            "followers": user.get("edge_followed_by", {}).get("count", 0),
            "following": user.get("edge_follow", {}).get("count", 0),
            "is_private": user.get("is_private", False),
            "is_verified": user.get("is_verified", False),
            "profile_pic_url": user.get("profile_pic_url_hd", ""),
            "post_count": user.get("edge_owner_to_timeline_media", {}).get("count", 0),
        }

        # Extract posts
        media = user.get("edge_owner_to_timeline_media", {})
        edges = media.get("edges", [])

        discovered = []
        for edge in edges:
            node = edge.get("node", {})
            shortcode = node.get("shortcode", "")
            typename = node.get("__typename", "")
            is_video = node.get("is_video", False)

            likes = (
                node.get("edge_liked_by", {}).get("count", 0)
                or node.get("edge_media_preview_like", {}).get("count", 0)
            )
            comments = node.get("edge_media_to_comment", {}).get("count", 0)
            views = node.get("video_view_count", 0) if is_video else 0

            caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
            caption = caption_edges[0]["node"]["text"][:200] if caption_edges else ""

            timestamp = node.get("taken_at_timestamp")
            posted_at = datetime.utcfromtimestamp(timestamp) if timestamp else None

            thumbnail = node.get("thumbnail_src") or node.get("display_url", "")

            discovered.append(IGDiscoveredPost(
                url=f"https://www.instagram.com/p/{shortcode}/",
                shortcode=shortcode,
                post_type=typename,
                likes=likes,
                comments=comments,
                views=views,
                title=caption,
                thumbnail_url=thumbnail,
                posted_at=posted_at,
            ))

        # Also get reels
        reels = user.get("edge_felix_video_timeline", {})
        reel_edges = reels.get("edges", [])
        existing_codes = {d.shortcode for d in discovered}

        for edge in reel_edges:
            node = edge.get("node", {})
            shortcode = node.get("shortcode", "")
            if shortcode in existing_codes:
                continue

            likes = (
                node.get("edge_liked_by", {}).get("count", 0)
                or node.get("edge_media_preview_like", {}).get("count", 0)
            )
            views = node.get("video_view_count", 0)

            caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
            caption = caption_edges[0]["node"]["text"][:200] if caption_edges else ""

            timestamp = node.get("taken_at_timestamp")
            posted_at = datetime.utcfromtimestamp(timestamp) if timestamp else None

            thumbnail = node.get("thumbnail_src") or node.get("display_url", "")

            discovered.append(IGDiscoveredPost(
                url=f"https://www.instagram.com/reel/{shortcode}/",
                shortcode=shortcode,
                post_type="GraphVideo",
                likes=likes,
                comments=0,
                views=views,
                title=caption,
                thumbnail_url=thumbnail,
                posted_at=posted_at,
            ))

        logger.info(
            f"Discovered {len(discovered)} posts from @{username} "
            f"(followers: {profile_info['followers']:,})"
        )
        return profile_info, discovered

    # ── Batch Sync (Profile-Level) ──────────────────────

    async def sync_profile_posts(
        self, username: str, tracked_shortcodes: set[str]
    ) -> dict[str, IGPostMetrics]:
        """
        Fetch profile data once and return metrics for all tracked posts.
        This is the key optimization: 1 API call updates N posts.

        Args:
            username: Instagram username (without @)
            tracked_shortcodes: set of shortcodes we're tracking

        Returns:
            dict mapping shortcode -> IGPostMetrics for matched posts
        """
        user = await self._fetch_profile_data(username)

        results = {}

        # Extract from timeline media
        media = user.get("edge_owner_to_timeline_media", {})
        for edge in media.get("edges", []):
            node = edge.get("node", {})
            shortcode = node.get("shortcode", "")
            if shortcode in tracked_shortcodes:
                results[shortcode] = self._parse_post_node(node)

        # Extract from reels
        reels = user.get("edge_felix_video_timeline", {})
        for edge in reels.get("edges", []):
            node = edge.get("node", {})
            shortcode = node.get("shortcode", "")
            if shortcode in tracked_shortcodes and shortcode not in results:
                results[shortcode] = self._parse_post_node(node)

        logger.info(
            f"Profile sync @{username}: matched {len(results)}/{len(tracked_shortcodes)} "
            f"tracked posts from API response"
        )
        return results

    @staticmethod
    def _extract_shortcode(url: str) -> Optional[str]:
        """Extract shortcode from Instagram URL (/p/XXX/ or /reel/XXX/)."""
        match = re.search(r'/(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
        return match.group(1) if match else None

    @staticmethod
    def detect_instagram_url(url: str) -> bool:
        """Check if a URL is an Instagram URL."""
        return bool(re.search(r'instagram\.com/', url, re.IGNORECASE))

    @staticmethod
    def extract_username_from_url(url: str) -> Optional[str]:
        """Extract username from an Instagram post/reel URL."""
        # Profile URL: instagram.com/username/
        # Post URL doesn't always contain username, but we can try
        match = re.search(r'instagram\.com/([A-Za-z0-9_.]+)', url)
        if match:
            name = match.group(1)
            if name not in ("p", "reel", "tv", "stories", "explore", "accounts", "api"):
                return name
        return None
