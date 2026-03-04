"""
Test v2: Deep dive into Instagram's web_profile_info API.
Strategy 6 (fetch from page context) returned 200 — now extract full post data.

Usage: python test_instagram_v2.py roove.co.id
"""

import asyncio
import sys
import json
from playwright.async_api import async_playwright

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "roove.co.id"
USERNAME = USERNAME.lstrip("@")
PROFILE_URL = f"https://www.instagram.com/{USERNAME}/"


async def main():
    print(f"\n{'='*60}")
    print(f"Instagram Deep Scrape Test — @{USERNAME}")
    print(f"{'='*60}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {} };
        """)

        page = await context.new_page()
        print("[1] Loading Instagram profile page...")
        await page.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        print(f"    Page title: {await page.title()}")

        # ── Fetch full profile data ──
        print("\n[2] Fetching web_profile_info API from page context...")
        raw = await page.evaluate(f"""
            async () => {{
                try {{
                    const resp = await fetch('/api/v1/users/web_profile_info/?username={USERNAME}', {{
                        headers: {{
                            'X-IG-App-ID': '936619743392459',
                            'X-Requested-With': 'XMLHttpRequest',
                        }}
                    }});
                    const text = await resp.text();
                    return {{ status: resp.status, body: text }};
                }} catch(e) {{
                    return {{ error: e.message }};
                }}
            }}
        """)

        if raw.get('error'):
            print(f"    ERROR: {raw['error']}")
            await browser.close()
            return

        print(f"    Status: {raw['status']}")
        print(f"    Response size: {len(raw.get('body', '')):,} chars")

        body = json.loads(raw['body'])

        # Save full response for inspection
        with open("/tmp/ig_profile_data.json", "w") as f:
            json.dump(body, f, indent=2)
        print("    Full response saved to /tmp/ig_profile_data.json")

        user = body.get('data', {}).get('user', {})
        if not user:
            print("    No user data found!")
            await browser.close()
            return

        # ── Profile Info ──
        print(f"\n[3] Profile Info:")
        print(f"    Username:  {user.get('username')}")
        print(f"    Full name: {user.get('full_name')}")
        print(f"    Bio:       {user.get('biography', '')[:100]}")
        print(f"    Followers: {user.get('edge_followed_by', {}).get('count', '?'):,}")
        print(f"    Following: {user.get('edge_follow', {}).get('count', '?'):,}")
        print(f"    Is private: {user.get('is_private')}")
        print(f"    Is verified: {user.get('is_verified')}")
        print(f"    Profile pic: {user.get('profile_pic_url_hd', '')[:80]}...")

        # ── Posts (edge_owner_to_timeline_media) ──
        media = user.get('edge_owner_to_timeline_media', {})
        print(f"\n[4] Posts (edge_owner_to_timeline_media):")
        print(f"    Total post count: {media.get('count', '?')}")

        edges = media.get('edges', [])
        print(f"    Posts in this response: {len(edges)}")

        page_info = media.get('page_info', {})
        print(f"    has_next_page: {page_info.get('has_next_page')}")
        print(f"    end_cursor: {page_info.get('end_cursor', 'N/A')[:30]}...")

        for i, edge in enumerate(edges):
            node = edge.get('node', {})
            shortcode = node.get('shortcode', '?')
            typename = node.get('__typename', '?')
            timestamp = node.get('taken_at_timestamp', 0)
            caption_edges = node.get('edge_media_to_caption', {}).get('edges', [])
            caption = caption_edges[0]['node']['text'][:80] if caption_edges else '(no caption)'

            likes = node.get('edge_liked_by', node.get('edge_media_preview_like', {})).get('count', 0)
            comments = node.get('edge_media_to_comment', {}).get('count', 0)
            views = node.get('video_view_count', None)
            is_video = node.get('is_video', False)

            print(f"\n    --- Post #{i+1} ---")
            print(f"    URL:       https://www.instagram.com/p/{shortcode}/")
            print(f"    Type:      {typename} {'(video)' if is_video else '(image)'}")
            print(f"    Likes:     {likes:,}")
            print(f"    Comments:  {comments:,}")
            if views is not None:
                print(f"    Views:     {views:,}")
            print(f"    Timestamp: {timestamp}")
            print(f"    Caption:   {caption}")

            # Check what other keys are available
            if i == 0:
                print(f"    All node keys: {list(node.keys())}")

        # ── Reels (edge_felix_video_timeline) ──
        reels = user.get('edge_felix_video_timeline', {})
        print(f"\n[5] Reels (edge_felix_video_timeline):")
        print(f"    Total reel count: {reels.get('count', '?')}")
        reel_edges = reels.get('edges', [])
        print(f"    Reels in this response: {len(reel_edges)}")
        for i, edge in enumerate(reel_edges[:5]):
            node = edge.get('node', {})
            shortcode = node.get('shortcode', '?')
            views = node.get('video_view_count', 0)
            likes = node.get('edge_liked_by', node.get('edge_media_preview_like', {})).get('count', 0)
            print(f"    Reel #{i+1}: /reel/{shortcode}/ — views={views:,}, likes={likes:,}")

        # ── Try pagination (get more posts) ──
        end_cursor = page_info.get('end_cursor')
        if end_cursor and page_info.get('has_next_page'):
            user_id = user.get('id')
            print(f"\n[6] Pagination test (user_id={user_id}, cursor={end_cursor[:20]}...)...")

            pagination_result = await page.evaluate(f"""
                async () => {{
                    try {{
                        const variables = JSON.stringify({{
                            id: "{user_id}",
                            first: 12,
                            after: "{end_cursor}"
                        }});
                        const url = `/graphql/query/?query_hash=e769aa130647d2571c27c44c3142ea8c&variables=${{encodeURIComponent(variables)}}`;
                        const resp = await fetch(url, {{
                            headers: {{
                                'X-IG-App-ID': '936619743392459',
                                'X-Requested-With': 'XMLHttpRequest',
                            }}
                        }});
                        const text = await resp.text();
                        return {{ status: resp.status, body: text.substring(0, 5000) }};
                    }} catch(e) {{
                        return {{ error: e.message }};
                    }}
                }}
            """)

            print(f"    Status: {pagination_result.get('status', 'N/A')}")
            if pagination_result.get('body'):
                try:
                    pbody = json.loads(pagination_result['body'])
                    next_media = pbody.get('data', {}).get('user', {}).get('edge_owner_to_timeline_media', {})
                    next_edges = next_media.get('edges', [])
                    print(f"    Next page posts: {len(next_edges)}")
                    for i, edge in enumerate(next_edges[:3]):
                        node = edge.get('node', {})
                        sc = node.get('shortcode', '?')
                        likes = node.get('edge_liked_by', node.get('edge_media_preview_like', {})).get('count', 0)
                        print(f"      Post: /p/{sc}/ — likes={likes:,}")
                except:
                    print(f"    Raw: {pagination_result['body'][:300]}")
            elif pagination_result.get('error'):
                print(f"    Error: {pagination_result['error']}")

        # ── Test individual post scrape ──
        if edges:
            first_shortcode = edges[0]['node']['shortcode']
            print(f"\n[7] Individual post scrape test: /p/{first_shortcode}/")

            post_result = await page.evaluate(f"""
                async () => {{
                    try {{
                        const resp = await fetch('/api/v1/media/{first_shortcode}/web_info/', {{
                            headers: {{
                                'X-IG-App-ID': '936619743392459',
                                'X-Requested-With': 'XMLHttpRequest',
                            }}
                        }});
                        const text = await resp.text();
                        return {{ status: resp.status, body: text.substring(0, 5000) }};
                    }} catch(e) {{
                        // Try alternative endpoint
                        try {{
                            const resp2 = await fetch('/p/{first_shortcode}/?__a=1&__d=dis', {{
                                headers: {{
                                    'X-IG-App-ID': '936619743392459',
                                    'X-Requested-With': 'XMLHttpRequest',
                                }}
                            }});
                            const text2 = await resp2.text();
                            return {{ status: resp2.status, body: text2.substring(0, 5000), endpoint: '?__a=1' }};
                        }} catch(e2) {{
                            return {{ error: e.message, error2: e2.message }};
                        }}
                    }}
                }}
            """)

            print(f"    Status: {post_result.get('status', 'N/A')}")
            if post_result.get('body'):
                try:
                    post_body = json.loads(post_result['body'])
                    print(f"    Keys: {list(post_body.keys())[:10]}")
                    # Try to find detailed metrics
                    items = post_body.get('items', [])
                    if items:
                        item = items[0]
                        print(f"    Item keys: {list(item.keys())[:15]}")
                        print(f"    Like count: {item.get('like_count', '?')}")
                        print(f"    Comment count: {item.get('comment_count', '?')}")
                        print(f"    Play count: {item.get('play_count', '?')}")
                        print(f"    View count: {item.get('view_count', '?')}")
                except:
                    print(f"    Raw: {post_result['body'][:500]}")

        await browser.close()

    print(f"\n{'='*60}")
    print("Test complete!")
    print(f"{'='*60}\n")


asyncio.run(main())
