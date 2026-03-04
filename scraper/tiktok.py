"""
TikTok scraping logic using Playwright.
Core worker untuk semua data collection.

Approach: Extract data from __UNIVERSAL_DATA_FOR_REHYDRATION__ embedded JSON.
TikTok embeds full video metadata (including stats) in a <script> tag
during server-side rendering. This is more reliable than CSS selectors
which break when TikTok updates their layout.
"""

import json
import logging
import re
from typing import Optional
from dataclasses import dataclass

from playwright.async_api import async_playwright, BrowserContext

from scraper.anti_detect import (
    get_browser_context_options,
    random_delay,
)

logger = logging.getLogger("soctrack.scraper")


@dataclass
class PostMetrics:
    """Metrics extracted from a single TikTok post."""
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    title: Optional[str] = None
    author: Optional[str] = None
    video_id: Optional[str] = None


@dataclass
class DiscoveredPost:
    """Post found during account or keyword discovery."""
    url: str
    video_id: str
    views: int = 0
    likes: int = 0
    title: Optional[str] = None
    creator: Optional[str] = None


class TikTokScraper:
    """Headless browser scraper for TikTok public pages."""

    def __init__(self, proxy_url: Optional[str] = None):
        self.proxy_url = proxy_url
        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self._pages_visited = 0
        self._max_pages_per_context = 50

    async def start(self):
        """Launch browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        await self._new_context()
        logger.info("TikTok scraper started")

    async def stop(self):
        """Close browser and cleanup."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("TikTok scraper stopped")

    async def _new_context(self):
        """Create fresh browser context with randomized fingerprint."""
        if self._context:
            await self._context.close()
        options = get_browser_context_options(self.proxy_url)
        self._context = await self._browser.new_context(**options)
        # Remove webdriver flag
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        self._pages_visited = 0
        logger.debug("New browser context created")

    async def _maybe_rotate_context(self):
        """Rotate context if page visit limit reached."""
        self._pages_visited += 1
        if self._pages_visited >= self._max_pages_per_context:
            logger.info(f"Rotating context after {self._pages_visited} visits")
            await self._new_context()

    async def _extract_embedded_data(self, page) -> Optional[dict]:
        """
        Extract __UNIVERSAL_DATA_FOR_REHYDRATION__ JSON from page source.
        This is TikTok's SSR data that contains all video/user metadata.
        """
        try:
            data_str = await page.evaluate("""
                () => {
                    const el = document.querySelector('script#__UNIVERSAL_DATA_FOR_REHYDRATION__');
                    return el ? el.textContent : null;
                }
            """)
            if data_str:
                return json.loads(data_str)
        except Exception as e:
            logger.warning(f"Failed to extract embedded data: {e}")
        return None

    # ── Scrape Single Post ───────────────────────────────

    async def scrape_post(self, url: str) -> PostMetrics:
        """
        Visit a TikTok post page and extract metrics from embedded JSON.
        Supports both full URLs and short URLs (vt.tiktok.com).
        """
        await self._maybe_rotate_context()
        page = await self._context.new_page()

        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)  # SSR data is in initial HTML, no need to wait long

            data = await self._extract_embedded_data(page)
            if not data:
                raise Exception("No embedded data found on page")

            scope = data.get("__DEFAULT_SCOPE__", {})
            video_detail = scope.get("webapp.video-detail", {})
            item_info = video_detail.get("itemInfo", {})
            item = item_info.get("itemStruct", {})

            if not item:
                status_code = video_detail.get("statusCode", "unknown")
                status_msg = video_detail.get("statusMsg", "")
                raise Exception(f"Video not available: {status_code} {status_msg}")

            stats = item.get("stats", {})
            author = item.get("author", {})

            metrics = PostMetrics(
                views=stats.get("playCount", 0),
                likes=stats.get("diggCount", 0),
                comments=stats.get("commentCount", 0),
                shares=stats.get("shareCount", 0),
                saves=stats.get("collectCount", 0),
                title=item.get("desc", ""),
                author=author.get("uniqueId", ""),
                video_id=item.get("id", ""),
            )

            # Get the resolved URL (in case of short URL redirect)
            final_url = page.url
            if "/video/" in final_url:
                vid_match = re.search(r"/video/(\d+)", final_url)
                if vid_match and not metrics.video_id:
                    metrics.video_id = vid_match.group(1)

            logger.info(
                f"Scraped {url}: views={metrics.views}, likes={metrics.likes}, "
                f"comments={metrics.comments}, shares={metrics.shares}"
            )
            return metrics

        except Exception as e:
            logger.error(f"Failed to scrape {url}: {e}")
            raise

        finally:
            await page.close()

    # ── Scrape Multiple Posts (Batch) ────────────────────

    async def scrape_posts_batch(
        self, urls: list[str], delay_min: int = 30, delay_max: int = 90
    ) -> list[tuple[str, Optional[PostMetrics], Optional[str]]]:
        """
        Scrape a list of post URLs with staggered delays.
        Returns list of (url, metrics_or_none, error_or_none).
        """
        results = []
        for i, url in enumerate(urls):
            logger.info(f"[{i+1}/{len(urls)}] Scraping: {url}")
            try:
                metrics = await self.scrape_post(url)
                results.append((url, metrics, None))
            except Exception as e:
                results.append((url, None, str(e)))
                logger.error(f"  Failed: {e}")

            # Staggered delay between posts
            if i < len(urls) - 1:
                delay = await random_delay(delay_min, delay_max)
                logger.debug(f"  Waiting {delay:.0f}s before next post")

        return results

    # ── Discover Posts from Account ──────────────────────

    async def discover_account(self, username: str) -> list[DiscoveredPost]:
        """
        Visit profile page, extract video IDs from embedded HTML/JSON.
        Then visit each video to get full metadata.

        Note: TikTok profile pages don't include video list in SSR data.
        Video IDs are extracted from HTML source via regex.
        """
        await self._maybe_rotate_context()
        page = await self._context.new_page()
        clean_username = username.lstrip("@")
        url = f"https://www.tiktok.com/@{clean_username}"

        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            # Extract video IDs from HTML source
            html_content = await page.content()
            video_ids = list(set(re.findall(r'"id":"(\d{18,20})"', html_content)))

            if not video_ids:
                video_ids = list(set(re.findall(r"/video/(\d{18,20})", html_content)))

            logger.info(f"Found {len(video_ids)} video IDs from @{clean_username} profile HTML")

            # For each video ID, create a DiscoveredPost
            # We'll get full metrics later during the nightly scrape
            discovered = []
            for vid_id in video_ids:
                discovered.append(DiscoveredPost(
                    url=f"https://www.tiktok.com/@{clean_username}/video/{vid_id}",
                    video_id=vid_id,
                    creator=clean_username,
                ))

            # If we got very few from HTML, try scrolling to trigger more
            if len(discovered) < 5:
                logger.info("Few videos found in HTML, trying scroll approach...")
                for i in range(5):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(3000)

                html_content = await page.content()
                new_ids = list(set(re.findall(r'"id":"(\d{18,20})"', html_content)))
                existing = {d.video_id for d in discovered}
                for vid_id in new_ids:
                    if vid_id not in existing:
                        discovered.append(DiscoveredPost(
                            url=f"https://www.tiktok.com/@{clean_username}/video/{vid_id}",
                            video_id=vid_id,
                            creator=clean_username,
                        ))

            logger.info(f"Discovered {len(discovered)} posts from @{clean_username}")
            return discovered

        except Exception as e:
            logger.error(f"Failed to discover account @{clean_username}: {e}")
            raise

        finally:
            await page.close()

    # ── Keyword Discovery (FYP Scanner) ──────────────────

    async def discover_keyword(
        self, keyword: str, max_results: int = 50
    ) -> list[DiscoveredPost]:
        """
        Search TikTok by keyword, extract video data from embedded JSON.
        """
        await self._maybe_rotate_context()
        page = await self._context.new_page()
        search_url = f"https://www.tiktok.com/search?q={keyword}"

        try:
            await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            # Scroll to load more results
            for i in range(min(max_results // 10, 5)):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(3000)

            # Extract from embedded data
            data = await self._extract_embedded_data(page)
            discovered = []

            if data:
                scope = data.get("__DEFAULT_SCOPE__", {})
                # Try to find search results in various possible keys
                for key in scope:
                    if "search" in key.lower():
                        search_data = scope[key]
                        if isinstance(search_data, dict):
                            for sub_key in search_data:
                                items = search_data[sub_key]
                                if isinstance(items, list):
                                    for item in items:
                                        if isinstance(item, dict) and "id" in item:
                                            stats = item.get("stats", {})
                                            author = item.get("author", {})
                                            discovered.append(DiscoveredPost(
                                                url=f"https://www.tiktok.com/@{author.get('uniqueId', '')}/video/{item['id']}",
                                                video_id=item["id"],
                                                views=stats.get("playCount", 0),
                                                likes=stats.get("diggCount", 0),
                                                title=item.get("desc", ""),
                                                creator=author.get("uniqueId", ""),
                                            ))

            # Fallback: extract video IDs from HTML
            if not discovered:
                html_content = await page.content()
                video_ids = list(set(re.findall(r"/video/(\d{18,20})", html_content)))
                for vid_id in video_ids[:max_results]:
                    discovered.append(DiscoveredPost(
                        url=f"https://www.tiktok.com/video/{vid_id}",
                        video_id=vid_id,
                    ))

            logger.info(f"Discovered {len(discovered)} posts for keyword '{keyword}'")
            return discovered[:max_results]

        except Exception as e:
            logger.error(f"Failed keyword discovery for '{keyword}': {e}")
            raise

        finally:
            await page.close()
