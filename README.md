# SocTrack

**TikTok Social Media Performance Tracker** with Intelligent Discovery & Competitor Monitoring.

Track views, likes, comments, dan shares dari post TikTok milik sendiri maupun kompetitor, dengan daily delta tracking yang menunjukkan pertumbuhan setiap hari.

## Features

- **Track by Account** — Auto-discover semua post dari username TikTok
- **Track by Link** — Monitor post spesifik via URL
- **FYP Scanner (Discovery)** — Cari konten trending berdasarkan keyword/niche
- **Daily Delta Tracking** — Snapshot metrics harian + perbandingan delta
- **Compare View** — Side-by-side comparison 2+ posts
- **Competitor Intelligence** — Monitor kompetitor tanpa mereka tahu

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI (Python) |
| Database | PostgreSQL + SQLAlchemy + Alembic |
| Scraper | Playwright (headless Chromium) |
| Frontend | HTML/CSS/JS + Chart.js |
| Scheduler | System cron |

## Setup

```bash
# 1. Clone repo
git clone <repo-url> && cd soctrack

# 2. Create virtual environment
python -m venv .venv && source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 4. Setup environment
cp .env.example .env
# Edit .env with your database credentials

# 5. Create database
createdb soctrack

# 6. Run migrations
alembic upgrade head

# 7. Start server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Cron Jobs

```crontab
# Account discovery — setiap hari jam 00:00 WIB
0 0 * * * /path/to/.venv/bin/python /path/to/soctrack/jobs/account_discover.py

# Post metrics scrape — setiap hari jam 00:30 WIB
30 0 * * * /path/to/.venv/bin/python /path/to/soctrack/jobs/scrape_posts.py

# Delta calculation — setiap hari jam 03:00 WIB
0 3 * * * /path/to/.venv/bin/python /path/to/soctrack/jobs/calculate_deltas.py
```

## Project Structure

```
soctrack/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py             # Settings & env vars
│   ├── database.py           # SQLAlchemy engine & session
│   ├── models/               # Database models
│   │   ├── business.py
│   │   ├── brand.py
│   │   ├── post.py
│   │   ├── snapshot.py
│   │   ├── discovery.py
│   │   └── scrape_log.py
│   └── api/                  # REST API endpoints
│       ├── brands.py
│       ├── posts.py
│       ├── snapshots.py
│       └── discovery.py
├── scraper/
│   ├── tiktok.py             # Core scraping logic
│   ├── selectors.py          # CSS selectors (easy to update)
│   ├── anti_detect.py        # User agents & viewport rotation
│   └── parser.py             # Parse "1.2M" → integer
├── jobs/
│   ├── account_discover.py   # Cron: discover new posts
│   ├── scrape_posts.py       # Cron: nightly metrics scrape
│   └── calculate_deltas.py   # Cron: compute daily deltas
├── frontend/
│   ├── index.html            # Dashboard
│   ├── css/style.css
│   └── js/
│       ├── app.js            # Main UI logic
│       ├── api.js            # API client
│       └── charts.js         # Chart.js configs
├── alembic/                  # Database migrations
├── requirements.txt
├── .env.example
└── README.md
```
