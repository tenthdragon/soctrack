"""
Quick test: scrape satu akun TikTok untuk verifikasi Playwright bisa jalan dari server.
Jalankan: python test_scraper.py
"""

import asyncio
from playwright.async_api import async_playwright


async def test_scrape():
    print("=" * 60)
    print("SocTrack Scraper Test v2 (Anti-Detection)")
    print("=" * 60)

    print("\n[1] Launching Chromium...")
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ],
    )

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="id-ID",
        timezone_id="Asia/Jakarta",
        color_scheme="light",
    )

    # Remove webdriver flag
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['id-ID', 'id', 'en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        window.chrome = { runtime: {} };
    """)

    page = await context.new_page()

    # ── Test 1: Coba buka satu video langsung ────────────
    # Profile page sering diblock, coba langsung ke video page dulu
    print("\n[2] Trying direct video page approach...")
    print("    Opening TikTok search for @roove.co.id...")

    try:
        # Approach 1: via embed/oembed API (no browser detection)
        print("\n[3] Testing oembed API (no detection risk)...")
        api_page = await context.new_page()
        oembed_url = "https://www.tiktok.com/oembed?url=https://www.tiktok.com/@roove.co.id"
        await api_page.goto(oembed_url, timeout=15000)
        content = await api_page.content()
        print(f"    oembed response length: {len(content)} chars")
        if "roove" in content.lower():
            print("    ✓ oembed API accessible!")
        else:
            print(f"    Response preview: {content[:200]}")
        await api_page.close()
    except Exception as e:
        print(f"    ✗ oembed failed: {e}")

    # ── Test 2: Buka profile dengan stealth ──────────────
    print("\n[4] Opening profile page with stealth mode...")
    profile_url = "https://www.tiktok.com/@roove.co.id"

    try:
        # Intercept and block unnecessary resources to speed up
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,ico}", lambda route: route.abort())
        await page.route("**/analytics/**", lambda route: route.abort())
        await page.route("**/slardar/**", lambda route: route.abort())

        response = await page.goto(profile_url, timeout=30000, wait_until="domcontentloaded")
        print(f"    Status: {response.status if response else 'no response'}")
        print(f"    Title: {await page.title()}")

        # Wait longer for JS to render
        print("    Waiting for content to render...")
        await page.wait_for_timeout(8000)

        # Try multiple selectors for video links
        selectors_to_try = [
            ('a[href*="/video/"]', "video link"),
            ('[data-e2e="user-post-item"]', "user-post-item"),
            ('[data-e2e="user-post-item-list"]', "post-item-list"),
            ('[class*="DivItemContainer"]', "DivItemContainer"),
            ('[class*="video-feed"]', "video-feed"),
            ('a[href*="/@"]', "any tiktok link"),
        ]

        for sel, name in selectors_to_try:
            els = await page.query_selector_all(sel)
            print(f"    {name} ({sel}): {len(els)} found")

        # Check page content for clues
        body_text = await page.evaluate("document.body.innerText")
        text_preview = body_text[:500].replace("\n", " ")
        print(f"\n    Page text preview: {text_preview[:300]}...")

        # Check if there's a CAPTCHA or verify page
        if "verify" in body_text.lower() or "captcha" in body_text.lower():
            print("\n    ⚠️  CAPTCHA/Verification detected!")
        elif "login" in body_text.lower() and "sign up" in body_text.lower():
            print("\n    ⚠️  Login wall detected!")

        # Save full page HTML for analysis
        html = await page.content()
        with open("debug_page.html", "w") as f:
            f.write(html)
        print("\n    Full HTML saved: debug_page.html")

    except Exception as e:
        print(f"    ✗ Failed: {e}")

    # ── Test 3: Try fetching data via TikTok's internal API ──
    print("\n[5] Testing TikTok web API approach...")
    try:
        api_page2 = await context.new_page()
        # TikTok's public API for user info
        api_url = "https://www.tiktok.com/api/user/detail/?uniqueId=roove.co.id"
        await api_page2.goto(api_url, timeout=15000)
        api_content = await api_page2.evaluate("document.body.innerText")

        if len(api_content) > 50:
            print(f"    ✓ API response received ({len(api_content)} chars)")
            # Try to parse
            import json
            try:
                data = json.loads(api_content)
                if "userInfo" in data:
                    user = data["userInfo"].get("user", {})
                    stats = data["userInfo"].get("stats", {})
                    print(f"    Username: {user.get('uniqueId', 'N/A')}")
                    print(f"    Nickname: {user.get('nickname', 'N/A')}")
                    print(f"    Followers: {stats.get('followerCount', 'N/A')}")
                    print(f"    Videos: {stats.get('videoCount', 'N/A')}")
                    print(f"    Likes: {stats.get('heartCount', 'N/A')}")
                else:
                    print(f"    Response keys: {list(data.keys())}")
            except json.JSONDecodeError:
                print(f"    Raw response: {api_content[:300]}")
        else:
            print(f"    Response: {api_content[:200]}")
        await api_page2.close()
    except Exception as e:
        print(f"    ✗ API test failed: {e}")

    # Save screenshot
    await page.screenshot(path="debug_profile.png", full_page=False)
    print("\n[6] Screenshot saved: debug_profile.png")

    await browser.close()
    await pw.stop()
    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_scrape())
