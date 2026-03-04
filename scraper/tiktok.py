"""
TikTok scraping logic using Playwright.
Core worker untuk semua data collection.
"""

import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from playwright.async_api import async_playwright, Page, BrowserContext

from scraper.selectors import POST_PAGE, PROFILE_PAGE, SEARCH_PAGE, WAIT
from scraper.anti_detect import (
    get_browser_context_options,
    random_delay,
)
from scraper.parser import parse_metric

logger = logging.getLogger("soctrack.scraper")


@dataclass
class PostMetrics:
    """Metrics extracted from a single TikTok post."""
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    title: Optional[str] = None
    author: Optional[str] = None


@dataclass
class DiscoveredPost:
    """Post found during account or keyword discovery."""
    url: str
    video_id: str
    views: int = 0
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
        self._max_pages_per_context = 50  # Fresh context every 50 posts

    async def start(self):
        """Launch browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
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
        self._pages_visited = 0
        logger.debug("New browser context created")

    async def _maybe_rotate_context(self):
        """Rotate context if page visit limit reached."""
        self._pages_visited += 1
        if self._pages_visited >= self._max_pages_per_context:
            logger.info(f"Rotating context after {self._pages_visited} visits")
            await self._new_context()

    # ── Scrape Single Post ───────────────────────────────

    async def scrape_post(self, url: str) -> PostMetrics:
        """
        Visit a TikTok post page and extract metrics.
        Returns PostMetrics with views, likes, comments, shares.
        """
        await self._maybe_rotate_context()
        page = await self._context.new_page()

        try:
            await page.goto(url, timeout=WAIT["navigation_timeout"])
            await page.wait_for_selector(
                POST_PAGE["video_player"],
                timeout=WAIT["element_timeout"],
            )

            metrics = PostMetrics()

            # Extract each metric
            for metric_name in ["views", "likes", "comments", "shares"]:
                selector = POST_PAGE[metric_name]
                try:
                    el = await page.query_selector(selector)
                    if el:
                        text = await el.inner_text()
                        setattr(metrics, metric_name, parse_metric(text))
                except Exception as e:
                    logger.warning(f"Failed to extract {metric_name} from {url}: {e}")

            # Extract title
            try:
                title_el = await page.query_selector(POST_PAGE["title"])
                if title_el:
                    metrics.title = await title_el.inner_text()
            except Exception:
                pass

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

    # ── Discover Posts from Account ──────────────────────

    async def discover_account(self, username: str) -> list[DiscoveredPost]:
        """
        Visit profile page, scroll feed, extract all post URLs.
        """
        await self._maybe_rotate_context()
        page = await self._context.new_page()
        url = f"https://www.tiktok.com/@{username.lstrip('@')}"

        try:
            await page.goto(url, timeout=WAIT["navigation_timeout"])
            await page.wait_for_selector(
                PROFILE_PAGE["video_items"],
                timeout=WAIT["element_timeout"],
            )

            # Scroll to load all posts (lazy loading)
            prev_count = 0
            max_scrolls = 20
            for _ in range(max_scrolls):
                items = await page.query_selector_all(PROFILE_PAGE["video_links"])
                if len(items) == prev_count:
                    break
                prev_count = len(items)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)

            # Extract video URLs
            links = await page.query_selector_all(PROFILE_PAGE["video_links"])
            discovered = []
            for link in links:
                href = await link.get_attribute("href")
                if href and "/video/" in href:
                    video_id = href.split("/video/")[-1].split("?")[0]
                    discovered.append(DiscoveredPost(
                        url=href if href.startswith("http") else f"https://www.tiktok.com{href}",
                        video_id=video_id,
                        creator=username.lstrip("@"),
                    ))

            logger.info(f"Discovered {len(discovered)} posts from @{username}")
            return discovered

        except Exception as e:
            logger.error(f"Failed to discover account @{username}: {e}")
            raise

        finally:
            await page.close()

    # ── Keyword Discovery (FYP Scanner) ──────────────────

    async def discover_keyword(
        self, keyword: str, max_results: int = 50
    ) -> list[DiscoveredPost]:
        """
        Search TikTok by keyword, scroll results, extract posts.
        """
        await self._maybe_rotate_context()
        page = await self._context.new_page()
        search_url = f"https://www.tiktok.com/search?q={keyword}"

        try:
            await page.goto(search_url, timeout=WAIT["navigation_timeout"])

            # Click Videos tab
            try:
                tab = await page.wait_for_selector(
                    SEARCH_PAGE["tab_videos"],
                    timeout=WAIT["element_timeout"],
                )
                if tab:
                    await tab.click()
                    await page.wait_for_timeout(2000)
            except Exception:
                pass

            # Scroll to load results
            discovered = []
            max_scrolls = max_results // 10
            for _ in range(max_scrolls):
                cards = await page.query_selector_all(SEARCH_PAGE["video_links"])
                if len(cards) >= max_results:
                    break
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)

            # Extract results
            cards = await page.query_selector_all(SEARCH_PAGE["video_cards"])
            for card in cards[:max_results]:
                try:
                    link_el = await card.query_selector("a")
                    href = await link_el.get_attribute("href") if link_el else None
                    if not href or "/video/" not in href:
                        continue

                    video_id = href.split("/video/")[-1].split("?")[0]
                    creator = href.split("/@")[-1].split("/")[0] if "/@" in href else None

                    discovered.append(DiscoveredPost(
                        url=href if href.startswith("http") else f"https://www.tiktok.com{href}",
                        video_id=video_id,
                        creator=creator,
                    ))
                except Exception:
                    continue

            logger.info(f"Discovered {len(discovered)} posts for keyword '{keyword}'")
            return discovered

        except Exception as e:
            logger.error(f"Failed keyword discovery for '{keyword}': {e}")
            raise

        finally:
            await page.close()
