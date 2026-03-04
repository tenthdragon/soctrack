"""
SocTrack Scraper Test v3
Approach: Use TikTok's internal web API endpoints via Playwright.
TikTok renders video feeds via JS, but their API returns raw JSON.
"""

import asyncio
import json
from playwright.async_api import async_playwright


async def test_scrape():
    print("=" * 60)
    print("SocTrack Scraper Test v3 (API Approach)")
    print("=" * 60)

    print("\n[1] Launching Chromium...")
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

    # ── Approach: Visit profile, intercept API calls ─────
    print("\n[2] Intercepting TikTok API calls from profile page...")

    api_responses = []

    page = await context.new_page()

    # Intercept network requests to capture API data
    async def handle_response(response):
        url = response.url
        if "/api/post/item_list" in url or "/api/user/detail" in url:
            try:
                body = await response.json()
                api_responses.append({"url": url, "data": body})
                print(f"    ✓ Captured API: {url[:80]}...")
            except:
                pass

    page.on("response", handle_response)

    try:
        profile_url = "https://www.tiktok.com/@roove.co.id"
        print(f"    Opening {profile_url}")
        await page.goto(profile_url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # Scroll to trigger lazy loading of video list API
        print("    Scrolling to trigger video list API...")
        for i in range(3):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)
            print(f"    Scroll {i+1} done, captured {len(api_responses)} API calls")

    except Exception as e:
        print(f"    ✗ Navigation failed: {e}")

    # ── Parse captured API responses ─────────────────────
    print(f"\n[3] Analyzing {len(api_responses)} captured API responses...")

    user_info = None
    video_list = []

    for resp in api_responses:
        data = resp["data"]
        if "userInfo" in data:
            user_info = data["userInfo"]
        if "itemList" in data:
            video_list.extend(data["itemList"])

    if user_info:
        user = user_info.get("user", {})
        stats = user_info.get("stats", {})
        print(f"\n    ✓ User Info:")
        print(f"      Username: @{user.get('uniqueId', 'N/A')}")
        print(f"      Nickname: {user.get('nickname', 'N/A')}")
        print(f"      Followers: {stats.get('followerCount', 0):,}")
        print(f"      Videos: {stats.get('videoCount', 0)}")
        print(f"      Total Likes: {stats.get('heartCount', 0):,}")

    if video_list:
        print(f"\n    ✓ Videos found: {len(video_list)}")
        print(f"\n    First 5 videos:")
        for i, video in enumerate(video_list[:5]):
            vid_stats = video.get("stats", {})
            desc = video.get("desc", "No title")[:60]
            vid_id = video.get("id", "N/A")
            print(f"\n      [{i+1}] {desc}")
            print(f"          ID: {vid_id}")
            print(f"          Views: {vid_stats.get('playCount', 0):,}")
            print(f"          Likes: {vid_stats.get('diggCount', 0):,}")
            print(f"          Comments: {vid_stats.get('commentCount', 0):,}")
            print(f"          Shares: {vid_stats.get('shareCount', 0):,}")
            print(f"          URL: https://www.tiktok.com/@roove.co.id/video/{vid_id}")
    else:
        print("\n    ✗ No videos captured from API")

    # ── Fallback: Parse __UNIVERSAL_DATA_FOR_REHYDRATION__ ──
    if not video_list:
        print("\n[4] Trying fallback: extract data from page source...")
        try:
            data_str = await page.evaluate("""
                () => {
                    // TikTok embeds data in a script tag for SSR
                    const scripts = document.querySelectorAll('script#__UNIVERSAL_DATA_FOR_REHYDRATION__');
                    if (scripts.length > 0) return scripts[0].textContent;

                    // Alternative: SIGI_STATE
                    const sigi = document.querySelectorAll('script#SIGI_STATE');
                    if (sigi.length > 0) return sigi[0].textContent;

                    // Try all script tags
                    for (const s of document.querySelectorAll('script')) {
                        if (s.textContent.includes('"ItemModule"') || s.textContent.includes('"itemList"')) {
                            return s.textContent;
                        }
                    }
                    return null;
                }
            """)

            if data_str:
                print(f"    Found embedded data ({len(data_str)} chars)")
                data = json.loads(data_str)

                # Try to extract from __DEFAULT_SCOPE__
                default_scope = data.get("__DEFAULT_SCOPE__", {})

                # User detail
                user_detail = default_scope.get("webapp.user-detail", {})
                if user_detail:
                    ui = user_detail.get("userInfo", {})
                    user = ui.get("user", {})
                    stats = ui.get("stats", {})
                    print(f"\n    ✓ User Info (from page data):")
                    print(f"      Username: @{user.get('uniqueId', 'N/A')}")
                    print(f"      Followers: {stats.get('followerCount', 0):,}")
                    print(f"      Videos: {stats.get('videoCount', 0)}")

                # Video list
                video_post = default_scope.get("webapp.video-detail", {})
                user_post = default_scope.get("webapp.user-detail", {})

                # Try ItemModule pattern
                item_module = data.get("ItemModule", {})
                if item_module:
                    print(f"\n    ✓ Videos from ItemModule: {len(item_module)}")
                    for vid_id, video in list(item_module.items())[:5]:
                        print(f"      [{vid_id}] Views: {video.get('stats', {}).get('playCount', 'N/A')}")

                # Save for analysis
                with open("debug_data.json", "w") as f:
                    json.dump(data, f, indent=2, default=str)
                print("\n    Data saved: debug_data.json")
            else:
                print("    No embedded data found")

        except Exception as e:
            print(f"    ✗ Fallback failed: {e}")

    await page.screenshot(path="debug_profile.png", full_page=False)
    print("\n[5] Screenshot saved: debug_profile.png")

    await browser.close()
    await pw.stop()
    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_scrape())
