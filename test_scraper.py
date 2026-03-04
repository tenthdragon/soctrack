"""
SocTrack Scraper Test v4
Approach:
1. Get video list via HTTP request to TikTok API
2. Scrape individual video page for metrics (embedded JSON)
"""

import asyncio
import json
import re
from playwright.async_api import async_playwright


async def test_scrape():
    print("=" * 60)
    print("SocTrack Scraper Test v4 (Video Page Approach)")
    print("=" * 60)

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="id-ID",
        timezone_id="Asia/Jakarta",
    )
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)

    # ── Step 1: Get video list via API ───────────────────
    print("\n[1] Fetching video list for @roove.co.id...")
    page = await context.new_page()

    video_ids = []

    # Method A: Intercept XHR while browsing profile
    captured_items = []

    async def capture_api(response):
        if "api/post/item_list" in response.url:
            try:
                data = await response.json()
                items = data.get("itemList", [])
                captured_items.extend(items)
                print(f"    ✓ Captured {len(items)} videos from API")
            except:
                pass

    page.on("response", capture_api)

    await page.goto("https://www.tiktok.com/@roove.co.id", timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(5000)

    # Scroll aggressively to trigger API calls
    for i in range(8):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        if captured_items:
            print(f"    Scroll {i+1}: total {len(captured_items)} videos captured")
            break
        print(f"    Scroll {i+1}: waiting...")

    await page.close()

    # Method B: If API intercept didn't work, try direct API call
    if not captured_items:
        print("\n    API intercept didn't capture videos.")
        print("    Trying direct page scrape for video links...")

        page2 = await context.new_page()
        await page2.goto("https://www.tiktok.com/@roove.co.id", timeout=30000, wait_until="domcontentloaded")
        await page2.wait_for_timeout(5000)

        # Try to find video links from the page HTML source
        html_content = await page2.content()

        # Extract video IDs from HTML using regex
        video_id_matches = re.findall(r'"id":"(\d{18,20})"', html_content)
        video_ids = list(set(video_id_matches))

        if not video_ids:
            # Try another pattern
            video_id_matches = re.findall(r'/video/(\d{18,20})', html_content)
            video_ids = list(set(video_id_matches))

        print(f"    Found {len(video_ids)} video IDs from HTML source")
        await page2.close()
    else:
        video_ids = [item.get("id") for item in captured_items if item.get("id")]
        # Print stats from captured items
        print(f"\n    Videos from API with stats:")
        for i, item in enumerate(captured_items[:5]):
            stats = item.get("stats", {})
            desc = item.get("desc", "No title")[:50]
            print(f"      [{i+1}] {desc}")
            print(f"          Views: {stats.get('playCount', 0):,}")
            print(f"          Likes: {stats.get('diggCount', 0):,}")
            print(f"          Comments: {stats.get('commentCount', 0):,}")
            print(f"          Shares: {stats.get('shareCount', 0):,}")

    # ── Step 2: Scrape individual video page ─────────────
    if video_ids:
        test_vid_id = video_ids[0]
        test_url = f"https://www.tiktok.com/@roove.co.id/video/{test_vid_id}"
        print(f"\n[2] Scraping individual video page...")
        print(f"    URL: {test_url}")

        page3 = await context.new_page()
        try:
            await page3.goto(test_url, timeout=30000, wait_until="domcontentloaded")
            await page3.wait_for_timeout(5000)

            # Extract embedded JSON data
            data_str = await page3.evaluate("""
                () => {
                    const el = document.querySelector('script#__UNIVERSAL_DATA_FOR_REHYDRATION__');
                    return el ? el.textContent : null;
                }
            """)

            if data_str:
                data = json.loads(data_str)
                scope = data.get("__DEFAULT_SCOPE__", {})

                # Try video detail
                video_detail = scope.get("webapp.video-detail", {})
                if video_detail:
                    item_info = video_detail.get("itemInfo", {})
                    item_struct = item_info.get("itemStruct", {})

                    if item_struct:
                        stats = item_struct.get("stats", {})
                        desc = item_struct.get("desc", "No title")[:80]
                        author = item_struct.get("author", {})

                        print(f"\n    ✓ VIDEO METRICS EXTRACTED!")
                        print(f"      Title: {desc}")
                        print(f"      Author: @{author.get('uniqueId', 'N/A')}")
                        print(f"      Views: {stats.get('playCount', 0):,}")
                        print(f"      Likes: {stats.get('diggCount', 0):,}")
                        print(f"      Comments: {stats.get('commentCount', 0):,}")
                        print(f"      Shares: {stats.get('shareCount', 0):,}")
                        print(f"      Saves: {stats.get('collectCount', 0):,}")
                        print(f"\n    ✅ SCRAPER WORKS!")
                    else:
                        print("    itemStruct not found")
                        print(f"    video-detail keys: {list(video_detail.keys())}")
                else:
                    print("    webapp.video-detail not found")
                    print(f"    Available keys: {list(scope.keys())}")

                    # Save for debugging
                    with open("debug_video.json", "w") as f:
                        json.dump(data, f, indent=2, default=str)
                    print("    Debug data saved: debug_video.json")
            else:
                print("    No embedded data found on video page")
                # Try direct DOM extraction as fallback
                print("    Trying DOM extraction...")
                for sel_name, sel in [
                    ("likes", '[data-e2e="like-count"]'),
                    ("comments", '[data-e2e="comment-count"]'),
                    ("shares", '[data-e2e="share-count"]'),
                ]:
                    el = await page3.query_selector(sel)
                    if el:
                        text = await el.inner_text()
                        print(f"      {sel_name}: {text}")

        except Exception as e:
            print(f"    ✗ Failed: {e}")
        finally:
            await page3.screenshot(path="debug_video.png")
            await page3.close()
    else:
        print("\n[2] Skipped — no video IDs found")
        print("    Trying one known video URL directly...")

        # Hardcode fallback: try visiting any roove video
        page4 = await context.new_page()
        try:
            # Use oembed to find a valid video URL
            await page4.goto(
                "https://www.tiktok.com/oembed?url=https://www.tiktok.com/@roove.co.id",
                timeout=15000,
            )
            oembed_text = await page4.evaluate("document.body.innerText")
            oembed_data = json.loads(oembed_text)
            print(f"    oembed title: {oembed_data.get('title', 'N/A')}")
            print(f"    oembed author: {oembed_data.get('author_name', 'N/A')}")

            # oembed gives us the embed HTML which has a video URL
            embed_html = oembed_data.get("html", "")
            vid_match = re.search(r'/video/(\d+)', embed_html)
            if vid_match:
                found_vid_id = vid_match.group(1)
                print(f"    Found video ID from oembed: {found_vid_id}")
                print(f"    Now scraping that video...")

                await page4.goto(
                    f"https://www.tiktok.com/@roove.co.id/video/{found_vid_id}",
                    timeout=30000,
                    wait_until="domcontentloaded",
                )
                await page4.wait_for_timeout(5000)

                data_str = await page4.evaluate("""
                    () => {
                        const el = document.querySelector('script#__UNIVERSAL_DATA_FOR_REHYDRATION__');
                        return el ? el.textContent : null;
                    }
                """)
                if data_str:
                    data = json.loads(data_str)
                    scope = data.get("__DEFAULT_SCOPE__", {})
                    vd = scope.get("webapp.video-detail", {})
                    item = vd.get("itemInfo", {}).get("itemStruct", {})
                    if item:
                        stats = item.get("stats", {})
                        print(f"\n    ✓ VIDEO METRICS EXTRACTED!")
                        print(f"      Title: {item.get('desc', 'N/A')[:80]}")
                        print(f"      Views: {stats.get('playCount', 0):,}")
                        print(f"      Likes: {stats.get('diggCount', 0):,}")
                        print(f"      Comments: {stats.get('commentCount', 0):,}")
                        print(f"      Shares: {stats.get('shareCount', 0):,}")
                        print(f"\n    ✅ SCRAPER WORKS!")
        except Exception as e:
            print(f"    ✗ Fallback failed: {e}")
        finally:
            await page4.close()

    await browser.close()
    await pw.stop()
    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_scrape())
