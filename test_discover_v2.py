"""
Test v2: Focus on intercepting /api/post/item_list/ response.
Print raw response to understand the format.
"""

import asyncio
import sys
import json
from playwright.async_api import async_playwright

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "@roove.co.id"
USERNAME = USERNAME.lstrip("@")
PROFILE_URL = f"https://www.tiktok.com/@{USERNAME}"

async def main():
    print(f"\nTarget: {PROFILE_URL}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="id-ID",
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()
        api_results = []

        async def capture_response(response):
            url = response.url
            if "/api/" in url and ("item_list" in url or "item/list" in url or "post" in url):
                status = response.status
                try:
                    text = await response.text()
                    try:
                        body = json.loads(text)
                    except:
                        body = None
                    api_results.append({
                        "url": url[:150],
                        "status": status,
                        "body_preview": text[:500] if text else "EMPTY",
                        "body": body,
                    })
                except Exception as e:
                    api_results.append({
                        "url": url[:150],
                        "status": status,
                        "error": str(e),
                    })

        page.on("response", capture_response)

        print("[1] Loading profile page...")
        await page.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        print("[2] Scrolling to trigger API calls...")
        for i in range(10):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(2000)
            if api_results:
                print(f"  Scroll {i+1}: {len(api_results)} API call(s) captured so far")

        print(f"\n{'='*60}")
        print(f"Total API calls captured: {len(api_results)}")
        print(f"{'='*60}\n")

        for i, res in enumerate(api_results):
            print(f"--- API Call #{i+1} ---")
            print(f"  URL: {res['url']}")
            print(f"  Status: {res.get('status', '?')}")

            if 'error' in res:
                print(f"  Error: {res['error']}")
                continue

            print(f"  Body preview: {res.get('body_preview', 'N/A')[:300]}")

            body = res.get('body')
            if body and isinstance(body, dict):
                print(f"  Top-level keys: {list(body.keys())}")

                # Check for items
                items = body.get("itemList", [])
                if items:
                    print(f"  itemList count: {len(items)}")
                    for item in items[:5]:
                        vid = item.get("id", "?")
                        desc = (item.get("desc") or "")[:60]
                        create = item.get("createTime", 0)
                        stats = item.get("stats", {})
                        views = stats.get("playCount", 0)
                        print(f"    Video {vid}: views={views}, desc={desc}")
                else:
                    print(f"  itemList: empty or not present")

                # Check hasMore
                has_more = body.get("hasMore")
                cursor = body.get("cursor")
                if has_more is not None:
                    print(f"  hasMore: {has_more}, cursor: {cursor}")

                # Check statusCode
                status_code = body.get("statusCode") or body.get("status_code")
                if status_code is not None:
                    print(f"  statusCode: {status_code}")

            print()

        await browser.close()

asyncio.run(main())
