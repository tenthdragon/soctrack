"""
Test: Discover post data from an Instagram profile page.
Tries multiple strategies similar to TikTok approach:
1. Embedded JSON (SSR data)
2. Regex extraction from HTML
3. API interception during scroll
4. Meta tags / Open Graph data

Usage: python test_instagram.py roove.co.id
"""

import asyncio
import sys
import re
import json
from playwright.async_api import async_playwright

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "roove.co.id"
USERNAME = USERNAME.lstrip("@")
PROFILE_URL = f"https://www.instagram.com/{USERNAME}/"


async def main():
    print(f"\n{'='*60}")
    print(f"Instagram Scraping Test for: @{USERNAME}")
    print(f"URL: {PROFILE_URL}")
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
        """)

        page = await context.new_page()

        # ── Strategy 1: Embedded JSON / SSR Data ──
        print("[Strategy 1] Looking for embedded JSON data...")
        try:
            await page.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)

            # Check page title to verify we loaded correctly
            title = await page.title()
            print(f"  Page title: {title}")

            # Check for login wall
            login_wall = await page.query_selector('input[name="username"]')
            if login_wall:
                print("  WARNING: Instagram login wall detected!")

            # Look for various embedded data scripts
            scripts_data = await page.evaluate("""
                () => {
                    const results = {};

                    // Strategy 1a: window._sharedData (old Instagram approach)
                    if (window._sharedData) {
                        results['_sharedData'] = JSON.stringify(window._sharedData).substring(0, 2000);
                    }

                    // Strategy 1b: window.__additionalDataLoaded
                    if (window.__additionalDataLoaded) {
                        results['__additionalDataLoaded'] = 'exists';
                    }

                    // Strategy 1c: Look for script tags with JSON
                    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                    scripts.forEach((s, i) => {
                        results[`ld_json_${i}`] = s.textContent.substring(0, 1000);
                    });

                    // Strategy 1d: Look for __NEXT_DATA__ (Next.js SSR)
                    const nextData = document.querySelector('script#__NEXT_DATA__');
                    if (nextData) {
                        results['__NEXT_DATA__'] = nextData.textContent.substring(0, 2000);
                    }

                    // Strategy 1e: Look for any script with "profilePage" or "user" data
                    const allScripts = document.querySelectorAll('script:not([src])');
                    allScripts.forEach((s, i) => {
                        const text = s.textContent || '';
                        if (text.includes('profilePage') || text.includes('edge_owner_to_timeline_media') || text.includes('graphql')) {
                            results[`profile_script_${i}`] = text.substring(0, 2000);
                        }
                        // Also check for require/define patterns (Instagram's module system)
                        if (text.includes('XIGSharedData') || text.includes('xdt_api__v1__users__web_profile_info')) {
                            results[`ig_module_${i}`] = text.substring(0, 2000);
                        }
                    });

                    // Strategy 1f: Check meta tags
                    const metaDesc = document.querySelector('meta[property="og:description"]');
                    if (metaDesc) results['og_description'] = metaDesc.content;

                    const metaTitle = document.querySelector('meta[property="og:title"]');
                    if (metaTitle) results['og_title'] = metaTitle.content;

                    const metaUrl = document.querySelector('meta[property="og:url"]');
                    if (metaUrl) results['og_url'] = metaUrl.content;

                    const metaImage = document.querySelector('meta[property="og:image"]');
                    if (metaImage) results['og_image'] = metaImage.content;

                    return results;
                }
            """)

            for key, value in scripts_data.items():
                print(f"\n  [{key}]:")
                if isinstance(value, str) and len(value) > 200:
                    print(f"    {value[:200]}...")
                    # Try to parse as JSON
                    try:
                        parsed = json.loads(value)
                        print(f"    (Valid JSON with keys: {list(parsed.keys())[:10]})")
                    except:
                        pass
                else:
                    print(f"    {value}")

            if not scripts_data:
                print("  No embedded data found")

        except Exception as e:
            print(f"  Error: {e}")

        # ── Strategy 2: Regex from HTML source ──
        print(f"\n[Strategy 2] Regex extraction from page source...")
        try:
            html = await page.content()
            html_len = len(html)
            print(f"  HTML length: {html_len:,} chars")

            # Instagram post shortcodes (e.g., /p/ABC123/)
            shortcodes = set(re.findall(r'/p/([A-Za-z0-9_-]+)/', html))
            print(f"  Post shortcodes (/p/XXX/): {len(shortcodes)}")
            for sc in list(shortcodes)[:10]:
                print(f"    https://www.instagram.com/p/{sc}/")

            # Reel shortcodes
            reel_codes = set(re.findall(r'/reel/([A-Za-z0-9_-]+)/', html))
            print(f"  Reel shortcodes (/reel/XXX/): {len(reel_codes)}")
            for rc in list(reel_codes)[:10]:
                print(f"    https://www.instagram.com/reel/{rc}/")

            # Media IDs (large numbers)
            media_ids = set(re.findall(r'"media_id":\s*"(\d{15,20})"', html))
            print(f"  Media IDs: {len(media_ids)}")

            # pk / user IDs
            pks = set(re.findall(r'"pk":\s*"?(\d{8,20})"?', html))
            print(f"  PKs found: {len(pks)}")
            for pk in list(pks)[:5]:
                print(f"    {pk}")

            # Look for edge_owner_to_timeline_media (old GraphQL format)
            if 'edge_owner_to_timeline_media' in html:
                print("  Found 'edge_owner_to_timeline_media' in HTML!")
                match = re.search(r'"edge_owner_to_timeline_media"\s*:\s*\{[^}]*"count"\s*:\s*(\d+)', html)
                if match:
                    print(f"    Post count: {match.group(1)}")
            else:
                print("  No 'edge_owner_to_timeline_media' found")

            # Look for any GraphQL data
            gql_matches = re.findall(r'graphql["\s:]+', html[:50000])
            print(f"  GraphQL references in first 50K chars: {len(gql_matches)}")

        except Exception as e:
            print(f"  Error: {e}")

        # ── Strategy 3: API Interception ──
        print(f"\n[Strategy 3] API interception during page load + scroll...")
        api_results = []

        async def capture_response(response):
            url = response.url
            # Instagram API patterns
            if any(pattern in url for pattern in [
                '/api/v1/users/',
                '/api/v1/feed/',
                '/graphql',
                'query_hash',
                'web_profile_info',
                '/api/v1/media/',
            ]):
                status = response.status
                try:
                    text = await response.text()
                    try:
                        body = json.loads(text)
                    except:
                        body = None
                    api_results.append({
                        "url": url[:200],
                        "status": status,
                        "size": len(text),
                        "body_preview": text[:500] if text else "EMPTY",
                        "body": body,
                    })
                except Exception as e:
                    api_results.append({
                        "url": url[:200],
                        "status": status,
                        "error": str(e),
                    })

        page2 = await context.new_page()
        page2.on("response", capture_response)

        try:
            await page2.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=30000)
            await page2.wait_for_timeout(5000)

            # Scroll to trigger lazy loading
            for i in range(8):
                await page2.evaluate("window.scrollBy(0, window.innerHeight)")
                await page2.wait_for_timeout(3000)
                if api_results:
                    print(f"  Scroll {i+1}: {len(api_results)} API call(s) captured")

            print(f"\n  Total API calls captured: {len(api_results)}")
            for i, res in enumerate(api_results):
                print(f"\n  --- API Call #{i+1} ---")
                print(f"  URL: {res['url']}")
                print(f"  Status: {res.get('status', '?')}")
                if 'error' in res:
                    print(f"  Error: {res['error']}")
                    continue
                print(f"  Size: {res.get('size', 0)}")
                print(f"  Preview: {res.get('body_preview', '')[:300]}")

                body = res.get('body')
                if body and isinstance(body, dict):
                    print(f"  Keys: {list(body.keys())[:15]}")
                    # Look for user data
                    if 'data' in body:
                        data = body['data']
                        if isinstance(data, dict):
                            print(f"    data keys: {list(data.keys())[:10]}")
                    if 'user' in body:
                        user = body['user']
                        if isinstance(user, dict):
                            print(f"    user keys: {list(user.keys())[:10]}")

        except Exception as e:
            print(f"  Error: {e}")

        # ── Strategy 4: DOM-based extraction ──
        print(f"\n[Strategy 4] DOM-based post link extraction...")
        try:
            dom_links = await page.evaluate("""
                () => {
                    const results = {
                        post_links: [],
                        reel_links: [],
                        img_count: 0,
                        article_count: 0,
                    };

                    // Post links
                    document.querySelectorAll('a[href*="/p/"]').forEach(a => {
                        if (!results.post_links.includes(a.href))
                            results.post_links.push(a.href);
                    });

                    // Reel links
                    document.querySelectorAll('a[href*="/reel/"]').forEach(a => {
                        if (!results.reel_links.includes(a.href))
                            results.reel_links.push(a.href);
                    });

                    // Count images (potential post thumbnails)
                    results.img_count = document.querySelectorAll('img').length;

                    // Count article elements
                    results.article_count = document.querySelectorAll('article').length;

                    return results;
                }
            """)

            print(f"  Post links (/p/): {len(dom_links['post_links'])}")
            for link in dom_links['post_links'][:10]:
                print(f"    {link}")
            print(f"  Reel links (/reel/): {len(dom_links['reel_links'])}")
            for link in dom_links['reel_links'][:10]:
                print(f"    {link}")
            print(f"  Images in DOM: {dom_links['img_count']}")
            print(f"  Article elements: {dom_links['article_count']}")

        except Exception as e:
            print(f"  Error: {e}")

        # ── Strategy 5: Try Instagram GraphQL API ──
        print(f"\n[Strategy 5] Try Instagram GraphQL API directly...")
        try:
            # First get user ID from the page
            user_id = await page.evaluate("""
                () => {
                    // Try various ways to find user ID
                    const html = document.documentElement.innerHTML;

                    // Pattern 1: "profilePage_<id>"
                    const match1 = html.match(/"profilePage_(\d+)"/);
                    if (match1) return match1[1];

                    // Pattern 2: "user_id":"<id>"
                    const match2 = html.match(/"user_id"\s*:\s*"(\d+)"/);
                    if (match2) return match2[1];

                    // Pattern 3: logging_page_id
                    const match3 = html.match(/"logging_page_id"\s*:\s*"profilePage_(\d+)"/);
                    if (match3) return match3[1];

                    return null;
                }
            """)
            print(f"  User ID from page: {user_id}")

            if user_id:
                # Try the GraphQL endpoint
                gql_url = f"https://www.instagram.com/graphql/query/?query_hash=e769aa130647d2571c27c44c3142ea8c&variables=%7B%22id%22%3A%22{user_id}%22%2C%22first%22%3A12%7D"

                api_page = await context.new_page()
                try:
                    resp = await api_page.goto(gql_url, timeout=15000)
                    status = resp.status if resp else "No response"
                    text = await api_page.evaluate("() => document.body.innerText") if resp else ""
                    print(f"  GraphQL Status: {status}")
                    print(f"  Response length: {len(text)}")
                    print(f"  Preview: {text[:300]}")
                except Exception as e:
                    print(f"  GraphQL Error: {e}")
                await api_page.close()

                # Try v1 API
                v1_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={USERNAME}"
                api_page2 = await context.new_page()
                try:
                    # Set required headers
                    await api_page2.set_extra_http_headers({
                        "X-IG-App-ID": "936619743392459",
                        "X-Requested-With": "XMLHttpRequest",
                    })
                    resp = await api_page2.goto(v1_url, timeout=15000)
                    status = resp.status if resp else "No response"
                    text = await api_page2.evaluate("() => document.body.innerText") if resp else ""
                    print(f"\n  V1 API Status: {status}")
                    print(f"  Response length: {len(text)}")
                    if text:
                        try:
                            body = json.loads(text)
                            print(f"  Keys: {list(body.keys())[:10]}")
                            if 'data' in body and 'user' in body['data']:
                                user = body['data']['user']
                                print(f"  Username: {user.get('username')}")
                                print(f"  Full name: {user.get('full_name')}")
                                media = user.get('edge_owner_to_timeline_media', {})
                                print(f"  Post count: {media.get('count', '?')}")
                                edges = media.get('edges', [])
                                print(f"  Posts in response: {len(edges)}")
                                for edge in edges[:5]:
                                    node = edge.get('node', {})
                                    print(f"    Post {node.get('shortcode')}: likes={node.get('edge_liked_by', {}).get('count', 0)}")
                        except:
                            print(f"  Preview: {text[:300]}")
                except Exception as e:
                    print(f"  V1 API Error: {e}")
                await api_page2.close()

        except Exception as e:
            print(f"  Error: {e}")

        # ── Strategy 6: fetch() from within Instagram context ──
        print(f"\n[Strategy 6] fetch() from within Instagram page context...")
        try:
            result = await page.evaluate(f"""
                async () => {{
                    try {{
                        const resp = await fetch('/api/v1/users/web_profile_info/?username={USERNAME}', {{
                            headers: {{
                                'X-IG-App-ID': '936619743392459',
                                'X-Requested-With': 'XMLHttpRequest',
                            }}
                        }});
                        const text = await resp.text();
                        return {{ status: resp.status, body: text.substring(0, 3000) }};
                    }} catch(e) {{
                        return {{ error: e.message }};
                    }}
                }}
            """)
            print(f"  Result status: {result.get('status', 'N/A')}")
            if result.get('body'):
                try:
                    body = json.loads(result['body'])
                    print(f"  Keys: {list(body.keys())[:10]}")
                    if 'data' in body and 'user' in body['data']:
                        user = body['data']['user']
                        print(f"  Username: {user.get('username')}")
                        media = user.get('edge_owner_to_timeline_media', {})
                        print(f"  Post count: {media.get('count', '?')}")
                        edges = media.get('edges', [])
                        print(f"  Posts returned: {len(edges)}")
                        for edge in edges[:5]:
                            node = edge.get('node', {})
                            sc = node.get('shortcode', '?')
                            likes = node.get('edge_liked_by', {}).get('count', 0)
                            comments = node.get('edge_media_to_comment', {}).get('count', 0)
                            print(f"    /p/{sc}/ — likes={likes:,}, comments={comments:,}")
                except:
                    print(f"  Body preview: {result['body'][:300]}")
            elif result.get('error'):
                print(f"  Error: {result['error']}")
        except Exception as e:
            print(f"  Error: {e}")

        # Take screenshot for debugging
        await page.screenshot(path="/tmp/ig_profile.png")
        print(f"\n  Screenshot saved to /tmp/ig_profile.png")

        await browser.close()

    print(f"\n{'='*60}")
    print("Test complete.")
    print(f"{'='*60}\n")


asyncio.run(main())
