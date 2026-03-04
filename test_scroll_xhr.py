"""
Test: Aggressive scroll + XHR intercept approach (inspired by ScrapFly).
Scroll profile page aggressively, wait longer, intercept /api/post/item_list/.
"""

import asyncio
import json
import sys
from playwright.async_api import async_playwright

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "@roove.co.id"
USERNAME = USERNAME.lstrip("@")
PROFILE_URL = f"https://www.tiktok.com/@{USERNAME}"

# Store intercepted XHR data
xhr_data = []


async def main():
    print(f"\n{'='*60}")
    print(f"Aggressive scroll + XHR intercept for: @{USERNAME}")
    print(f"{'='*60}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )

        # Stealth
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
        """)

        page = await context.new_page()

        # Intercept ALL responses
        async def on_response(response):
            url = response.url
            if "/api/post/item_list/" in url or "/api/recommend/" in url:
                try:
                    body = await response.body()
                    text = body.decode('utf-8', errors='ignore')
                    if text and len(text) > 10:
                        xhr_data.append({
                            "url": url[:120],
                            "status": response.status,
                            "size": len(text),
                            "text": text,
                        })
                        print(f"  [XHR] {url[:80]}... size={len(text)}")
                    else:
                        print(f"  [XHR] {url[:80]}... EMPTY (size={len(text)})")
                except Exception as e:
                    print(f"  [XHR] {url[:80]}... ERROR: {e}")

        page.on("response", on_response)

        # Step 1: Load profile
        print("[1] Loading profile page...")
        await page.goto(PROFILE_URL, wait_until="networkidle", timeout=60000)
        print("  Page loaded. Waiting 10s for JS to render...")
        await page.wait_for_timeout(10000)

        # Check if video grid loaded
        video_grid = await page.query_selector('[data-e2e="user-post-item-list"]')
        print(f"  Video grid element found: {video_grid is not None}")

        # Check for video links in DOM
        links = await page.evaluate("""
            () => {
                const items = document.querySelectorAll('[data-e2e="user-post-item"] a, a[href*="/video/"]');
                return Array.from(items).map(a => a.href).filter(h => h.includes('/video/'));
            }
        """)
        print(f"  Video links in DOM: {len(links)}")
        for link in links[:5]:
            print(f"    {link}")

        # Step 2: Aggressive scroll with pauses
        print(f"\n[2] Aggressive scrolling (15 iterations, 8s pause)...")
        for i in range(15):
            # Scroll to bottom
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(8000)

            # Check DOM for new video links
            new_links = await page.evaluate("""
                () => {
                    const items = document.querySelectorAll('a[href*="/video/"]');
                    return Array.from(items).map(a => a.href).filter(h => h.includes('/video/'));
                }
            """)
            print(f"  Scroll {i+1}/15: {len(new_links)} video links in DOM, {len(xhr_data)} XHR captured")

            # If we got data, we can check if we want to continue
            if len(new_links) > 0 and i >= 3:
                print(f"  Got video links, doing 2 more scrolls to get more...")
                for j in range(2):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(8000)
                new_links = await page.evaluate("""
                    () => {
                        const items = document.querySelectorAll('a[href*="/video/"]');
                        return Array.from(items).map(a => a.href).filter(h => h.includes('/video/'));
                    }
                """)
                print(f"  Final: {len(new_links)} video links in DOM")
                break

        # Step 3: Results
        print(f"\n{'='*60}")
        print(f"RESULTS")
        print(f"{'='*60}\n")

        # From DOM
        all_links = await page.evaluate("""
            () => {
                const items = document.querySelectorAll('a[href*="/video/"]');
                return [...new Set(Array.from(items).map(a => a.href).filter(h => h.includes('/video/')))];
            }
        """)
        print(f"Video URLs from DOM: {len(all_links)}")
        for link in all_links[:20]:
            print(f"  {link}")

        # From XHR
        print(f"\nXHR calls captured: {len(xhr_data)}")
        total_videos_xhr = 0
        for i, xhr in enumerate(xhr_data):
            try:
                body = json.loads(xhr["text"])
                items = body.get("itemList", [])
                total_videos_xhr += len(items)
                print(f"\n  XHR #{i+1}: {len(items)} videos, hasMore={body.get('hasMore')}")
                for item in items[:5]:
                    vid = item.get("id", "?")
                    desc = (item.get("desc") or "")[:50]
                    stats = item.get("stats", {})
                    views = stats.get("playCount", 0)
                    print(f"    Video {vid}: views={views:,} | {desc}")
            except:
                print(f"  XHR #{i+1}: Could not parse")

        print(f"\nTotal videos from XHR: {total_videos_xhr}")
        print(f"Total unique URLs from DOM: {len(all_links)}")

        await browser.close()

    print(f"\n{'='*60}")
    print("Test complete.")
    print(f"{'='*60}\n")

asyncio.run(main())
