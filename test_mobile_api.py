"""
Test: Use TikTok mobile API (m.tiktok.com) to get video list from profile.
Approach inspired by drawrowfly/tiktok-scraper.
"""

import asyncio
import json
import time
import sys
from playwright.async_api import async_playwright

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "@roove.co.id"
USERNAME = USERNAME.lstrip("@")
PROFILE_URL = f"https://www.tiktok.com/@{USERNAME}"


async def main():
    print(f"\n{'='*60}")
    print(f"Mobile API test for: @{USERNAME}")
    print(f"{'='*60}\n")

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

        # Step 1: Get secUid from profile page
        print("[1] Getting secUid from profile page...")
        page = await context.new_page()
        await page.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        data_str = await page.evaluate("""
            () => {
                const el = document.querySelector('script#__UNIVERSAL_DATA_FOR_REHYDRATION__');
                return el ? el.textContent : null;
            }
        """)

        if not data_str:
            print("  FAILED: No embedded JSON found")
            await browser.close()
            return

        data = json.loads(data_str)
        user_detail = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {})
        user_info = user_detail.get("userInfo", {}).get("user", {})
        sec_uid = user_info.get("secUid", "")
        user_id = user_info.get("id", "")

        print(f"  Username: {user_info.get('uniqueId')}")
        print(f"  User ID: {user_id}")
        print(f"  secUid: {sec_uid[:40]}...")
        print(f"  Videos: {user_detail.get('userInfo', {}).get('stats', {}).get('videoCount', '?')}")

        if not sec_uid:
            print("  FAILED: No secUid found")
            await browser.close()
            return

        # Get cookies from the page for authentication
        cookies = await context.cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        print(f"  Cookies count: {len(cookies)}")

        await page.close()

        # Step 2: Try mobile API endpoint
        print(f"\n[2] Trying m.tiktok.com API endpoint...")
        api_page = await context.new_page()

        mobile_url = (
            f"https://m.tiktok.com/api/post/item_list/"
            f"?aid=1988"
            f"&app_name=tiktok_web"
            f"&device_platform=web_pc"
            f"&count=30"
            f"&secUid={sec_uid}"
            f"&cursor=0"
            f"&WebIdLastTime={int(time.time())}"
        )

        try:
            resp = await api_page.goto(mobile_url, timeout=15000)
            status = resp.status if resp else "No response"
            text = await api_page.evaluate("() => document.body.innerText") if resp else ""
            print(f"  Status: {status}")
            print(f"  Response length: {len(text)}")
            print(f"  Preview: {text[:300]}")

            if text:
                try:
                    body = json.loads(text)
                    items = body.get("itemList", [])
                    print(f"  Keys: {list(body.keys())}")
                    print(f"  itemList: {len(items)} items")
                    print(f"  hasMore: {body.get('hasMore')}")
                    print(f"  cursor: {body.get('cursor')}")
                    print(f"  statusCode: {body.get('statusCode')}")
                    for item in items[:10]:
                        vid = item.get("id", "?")
                        desc = (item.get("desc") or "")[:60]
                        create_time = item.get("createTime", 0)
                        stats = item.get("stats", {})
                        views = stats.get("playCount", 0)
                        print(f"    Video {vid}: views={views:,} | {desc}")
                except json.JSONDecodeError:
                    print("  Not valid JSON")
        except Exception as e:
            print(f"  Error: {e}")
        await api_page.close()

        # Step 3: Try www.tiktok.com API with mobile user-agent
        print(f"\n[3] Trying www.tiktok.com API with mobile UA...")
        mobile_context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            locale="id-ID",
        )
        await mobile_context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        # First visit profile to get cookies
        mpage = await mobile_context.new_page()
        await mpage.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=30000)
        await mpage.wait_for_timeout(3000)

        www_url = (
            f"https://www.tiktok.com/api/post/item_list/"
            f"?aid=1988"
            f"&app_name=tiktok_web"
            f"&device_platform=web_mobile"
            f"&count=30"
            f"&secUid={sec_uid}"
            f"&cursor=0"
        )

        try:
            resp = await mpage.goto(www_url, timeout=15000)
            status = resp.status if resp else "No response"
            text = await mpage.evaluate("() => document.body.innerText") if resp else ""
            print(f"  Status: {status}")
            print(f"  Response length: {len(text)}")
            print(f"  Preview: {text[:300]}")

            if text:
                try:
                    body = json.loads(text)
                    items = body.get("itemList", [])
                    print(f"  Keys: {list(body.keys())}")
                    print(f"  itemList: {len(items)} items")
                    print(f"  hasMore: {body.get('hasMore')}")
                    print(f"  statusCode: {body.get('statusCode')}")
                    for item in items[:10]:
                        vid = item.get("id", "?")
                        desc = (item.get("desc") or "")[:60]
                        stats = item.get("stats", {})
                        views = stats.get("playCount", 0)
                        print(f"    Video {vid}: views={views:,} | {desc}")
                except json.JSONDecodeError:
                    print("  Not valid JSON")
        except Exception as e:
            print(f"  Error: {e}")
        await mpage.close()

        # Step 4: Try direct fetch (no browser navigation) via page.evaluate
        print(f"\n[4] Trying fetch() from within a TikTok page context...")
        fetch_page = await context.new_page()
        await fetch_page.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=30000)
        await fetch_page.wait_for_timeout(3000)

        try:
            result = await fetch_page.evaluate(f"""
                async () => {{
                    try {{
                        const resp = await fetch('/api/post/item_list/?aid=1988&count=30&secUid={sec_uid}&cursor=0');
                        const text = await resp.text();
                        return {{ status: resp.status, body: text.substring(0, 2000) }};
                    }} catch(e) {{
                        return {{ error: e.message }};
                    }}
                }}
            """)
            print(f"  Result: {json.dumps(result)[:500]}")
            if result.get("body"):
                try:
                    body = json.loads(result["body"])
                    items = body.get("itemList", [])
                    print(f"  Keys: {list(body.keys())}")
                    print(f"  itemList: {len(items)} items")
                    print(f"  hasMore: {body.get('hasMore')}")
                    print(f"  statusCode: {body.get('statusCode')}")
                    for item in items[:10]:
                        vid = item.get("id", "?")
                        desc = (item.get("desc") or "")[:60]
                        stats = item.get("stats", {})
                        views = stats.get("playCount", 0)
                        print(f"    Video {vid}: views={views:,} | {desc}")
                except:
                    pass
        except Exception as e:
            print(f"  Error: {e}")

        await browser.close()

    print(f"\n{'='*60}")
    print("Test complete.")
    print(f"{'='*60}\n")

asyncio.run(main())
