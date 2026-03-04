"""
Quick test: scrape satu akun TikTok untuk verifikasi Playwright bisa jalan dari server.
Jalankan: python test_scraper.py
"""

import asyncio
import json
from playwright.async_api import async_playwright


async def test_scrape():
    print("=" * 60)
    print("SocTrack Scraper Test")
    print("=" * 60)

    print("\n[1] Launching Chromium...")
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="id-ID",
    )
    page = await context.new_page()

    # ── Test 1: Buka profile page ────────────────────────
    profile_url = "https://www.tiktok.com/@roove.co.id"
    print(f"\n[2] Opening profile: {profile_url}")

    try:
        await page.goto(profile_url, timeout=30000, wait_until="networkidle")
        print(f"    ✓ Page loaded. Title: {await page.title()}")
    except Exception as e:
        print(f"    ✗ Failed to load profile: {e}")
        # Coba ambil screenshot untuk debug
        await page.screenshot(path="debug_profile.png")
        print("    Screenshot saved: debug_profile.png")
        await browser.close()
        await pw.stop()
        return

    # ── Test 2: Extract video links dari profile ─────────
    print("\n[3] Scrolling to load posts...")
    prev_count = 0
    for i in range(5):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        links = await page.query_selector_all('a[href*="/video/"]')
        count = len(links)
        print(f"    Scroll {i+1}: found {count} video links")
        if count == prev_count and count > 0:
            break
        prev_count = count

    # Extract unique video URLs
    all_links = await page.query_selector_all('a[href*="/video/"]')
    video_urls = set()
    for link in all_links:
        href = await link.get_attribute("href")
        if href and "/video/" in href:
            if not href.startswith("http"):
                href = f"https://www.tiktok.com{href}"
            video_urls.add(href)

    print(f"\n    ✓ Total unique videos found: {len(video_urls)}")
    if video_urls:
        print("\n    First 5 videos:")
        for i, url in enumerate(list(video_urls)[:5]):
            print(f"      {i+1}. {url}")

    # ── Test 3: Scrape metrics dari satu video ───────────
    if video_urls:
        test_url = list(video_urls)[0]
        print(f"\n[4] Scraping metrics from: {test_url}")

        page2 = await context.new_page()
        try:
            await page2.goto(test_url, timeout=30000, wait_until="networkidle")
            await page2.wait_for_timeout(3000)

            metrics = {}
            selectors = {
                "likes": '[data-e2e="like-count"]',
                "comments": '[data-e2e="comment-count"]',
                "shares": '[data-e2e="share-count"]',
            }

            # Try to get views from browse-video or video-views
            for views_sel in ['[data-e2e="video-views"]', '[data-e2e="browse-video-count"]']:
                el = await page2.query_selector(views_sel)
                if el:
                    metrics["views"] = await el.inner_text()
                    break

            for name, sel in selectors.items():
                el = await page2.query_selector(sel)
                if el:
                    metrics[name] = await el.inner_text()
                else:
                    metrics[name] = "not found"

            # Try to get title
            for title_sel in ['[data-e2e="video-desc"]', '[data-e2e="browse-video-desc"]', 'h1']:
                el = await page2.query_selector(title_sel)
                if el:
                    metrics["title"] = (await el.inner_text())[:100]
                    break

            print(f"    ✓ Metrics extracted:")
            for k, v in metrics.items():
                print(f"      {k}: {v}")

        except Exception as e:
            print(f"    ✗ Failed to scrape video: {e}")
            await page2.screenshot(path="debug_video.png")
            print("    Screenshot saved: debug_video.png")
        finally:
            await page2.close()
    else:
        print("\n[4] Skipped — no video URLs found")

    # ── Save screenshot for review ───────────────────────
    await page.screenshot(path="debug_profile.png", full_page=False)
    print("\n[5] Profile screenshot saved: debug_profile.png")

    await browser.close()
    await pw.stop()
    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_scrape())
