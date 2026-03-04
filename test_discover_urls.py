"""
Test: Discover video URLs from a TikTok profile page.
Tries multiple strategies to extract video links.

Usage: python test_discover_urls.py @roove.co.id
"""

import asyncio
import sys
import re
import json
import time
from playwright.async_api import async_playwright

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "@roove.co.id"
USERNAME = USERNAME.lstrip("@")
PROFILE_URL = f"https://www.tiktok.com/@{USERNAME}"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


async def main():
    print(f"\n{'='*60}")
    print(f"Testing URL discovery for: {PROFILE_URL}")
    print(f"{'='*60}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=USER_AGENTS[0],
            viewport={"width": 1920, "height": 1080},
            locale="id-ID",
        )

        # Anti-detection
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        # ── Strategy 1: Embedded JSON ──
        print("[Strategy 1] Embedded JSON dari SSR data...")
        try:
            await page.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            data_str = await page.evaluate("""
                () => {
                    const el = document.querySelector('script#__UNIVERSAL_DATA_FOR_REHYDRATION__');
                    return el ? el.textContent : null;
                }
            """)

            if data_str:
                data = json.loads(data_str)
                default_scope = data.get("__DEFAULT_SCOPE__", {})

                # Try user-detail path
                user_detail = default_scope.get("webapp.user-detail", {})
                user_info = user_detail.get("userInfo", {})
                stats = user_info.get("stats", {})
                print(f"  User found: {user_info.get('user', {}).get('uniqueId', 'N/A')}")
                print(f"  Videos: {stats.get('videoCount', 'N/A')}, Followers: {stats.get('followerCount', 'N/A')}")

                # Check itemList
                item_list = user_detail.get("itemList", [])
                print(f"  itemList count: {len(item_list)}")
                if item_list:
                    for item in item_list[:5]:
                        vid = item.get("id", "?")
                        desc = item.get("desc", "")[:50]
                        print(f"    - Video {vid}: {desc}")
                else:
                    print("  itemList is empty (as expected)")

                # Check all keys for any video data
                print(f"\n  All keys in __DEFAULT_SCOPE__: {list(default_scope.keys())}")
                for key in default_scope:
                    val = default_scope[key]
                    if isinstance(val, dict):
                        for subkey in val:
                            if 'item' in subkey.lower() or 'video' in subkey.lower() or 'post' in subkey.lower():
                                print(f"    Found potential video key: {key}.{subkey}")
            else:
                print("  No embedded JSON found")
        except Exception as e:
            print(f"  Error: {e}")

        # ── Strategy 2: Regex video IDs from HTML ──
        print(f"\n[Strategy 2] Regex video IDs from page source...")
        try:
            html = await page.content()
            # Pattern 1: "id":"<19-digit-number>"
            ids_json = set(re.findall(r'"id"\s*:\s*"(\d{18,20})"', html))
            # Pattern 2: /video/<19-digit-number>
            ids_url = set(re.findall(r'/video/(\d{18,20})', html))
            # Pattern 3: videoId
            ids_vid = set(re.findall(r'"videoId"\s*:\s*"(\d{18,20})"', html))

            all_ids = ids_json | ids_url | ids_vid
            print(f"  From JSON 'id': {len(ids_json)} — {list(ids_json)[:5]}")
            print(f"  From URL /video/: {len(ids_url)} — {list(ids_url)[:5]}")
            print(f"  From videoId: {len(ids_vid)} — {list(ids_vid)[:5]}")
            print(f"  Total unique IDs: {len(all_ids)}")
        except Exception as e:
            print(f"  Error: {e}")

        # ── Strategy 3: Wait for page render + scroll ──
        print(f"\n[Strategy 3] Wait for JS render + scroll to load videos...")
        try:
            # Wait longer for the page to fully render
            await page.wait_for_timeout(5000)

            # Try to find video links in DOM
            video_links_before = await page.evaluate("""
                () => {
                    const links = document.querySelectorAll('a[href*="/video/"]');
                    return Array.from(links).map(a => a.href);
                }
            """)
            print(f"  Video links before scroll: {len(video_links_before)}")

            # Scroll down several times
            for i in range(5):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(2000)

            video_links_after = await page.evaluate("""
                () => {
                    const links = document.querySelectorAll('a[href*="/video/"]');
                    return Array.from(links).map(a => a.href);
                }
            """)
            print(f"  Video links after 5 scrolls: {len(video_links_after)}")
            for link in video_links_after[:10]:
                print(f"    - {link}")

        except Exception as e:
            print(f"  Error: {e}")

        # ── Strategy 4: Intercept API calls ──
        print(f"\n[Strategy 4] Intercept TikTok API calls during scroll...")
        api_responses = []

        async def handle_response(response):
            url = response.url
            if "item_list" in url or "item/list" in url or "post/item" in url:
                try:
                    body = await response.json()
                    api_responses.append({"url": url, "body": body})
                except:
                    api_responses.append({"url": url, "body": None})

        page2 = await context.new_page()
        page2.on("response", handle_response)

        try:
            await page2.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=30000)
            await page2.wait_for_timeout(5000)

            # Scroll to trigger lazy loading
            for i in range(8):
                await page2.evaluate("window.scrollBy(0, window.innerHeight)")
                await page2.wait_for_timeout(2000)

            print(f"  API calls intercepted: {len(api_responses)}")
            for resp in api_responses:
                url_short = resp["url"][:100]
                print(f"    - {url_short}")
                if resp["body"] and isinstance(resp["body"], dict):
                    items = resp["body"].get("itemList", [])
                    print(f"      Items: {len(items)}")
                    for item in items[:3]:
                        print(f"        Video {item.get('id')}: {item.get('desc', '')[:40]}")

        except Exception as e:
            print(f"  Error: {e}")

        # ── Strategy 5: Sitemap/SEO approach ──
        print(f"\n[Strategy 5] Try direct API endpoint...")
        try:
            api_url = f"https://www.tiktok.com/api/post/item_list/?WebIdLastTime=0&aid=1988&count=30&secUid=&cursor=0"
            # We need secUid - try to get it from the profile data
            if data_str:
                data = json.loads(data_str)
                user_detail = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {})
                sec_uid = user_detail.get("userInfo", {}).get("user", {}).get("secUid", "")
                if sec_uid:
                    print(f"  Found secUid: {sec_uid[:30]}...")
                    api_page = await context.new_page()
                    api_url = f"https://www.tiktok.com/api/post/item_list/?WebIdLastTime={int(time.time())}&aid=1988&app_language=en&app_name=tiktok_web&count=30&secUid={sec_uid}&cursor=0"
                    response = await api_page.goto(api_url, timeout=15000)
                    if response:
                        body = await response.json()
                        items = body.get("itemList", [])
                        print(f"  API returned {len(items)} items")
                        for item in items[:5]:
                            vid = item.get("id", "?")
                            desc = item.get("desc", "")[:50]
                            create_time = item.get("createTime", 0)
                            print(f"    - Video {vid}: {desc} (created: {create_time})")
                    await api_page.close()
                else:
                    print("  No secUid found")
        except Exception as e:
            print(f"  Error: {e}")

        await browser.close()

    print(f"\n{'='*60}")
    print("Test complete.")
    print(f"{'='*60}\n")


asyncio.run(main())
