# SocTrack Deployment Guide

Server: DigitalOcean Droplet (Ubuntu 24.04 LTS, 1 vCPU, 2GB RAM)

---

## Step 1: Login ke Server

Buka Terminal di komputer kamu, lalu SSH ke server:

```bash
ssh root@152.42.235.4
```

Kalau pakai password, masukkan password yang kamu set saat buat droplet.
Kalau pertama kali connect, ketik `yes` saat ditanya fingerprint.

---

## Step 2: Update System & Install Dependencies

```bash
# Update package list
apt update && apt upgrade -y

# Install essentials
apt install -y python3.12 python3.12-venv python3-pip git curl wget unzip \
  nginx certbot python3-certbot-nginx \
  libpq-dev build-essential

# Install PostgreSQL 16
apt install -y postgresql postgresql-contrib

# Install Playwright system dependencies (Chromium)
apt install -y libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
  libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64
```

---

## Step 3: Setup PostgreSQL

```bash
# Switch ke postgres user dan buat database + user
sudo -u postgres psql <<EOF
CREATE USER soctrack WITH PASSWORD 'GANTI_PASSWORD_INI';
CREATE DATABASE soctrack OWNER soctrack;
GRANT ALL PRIVILEGES ON DATABASE soctrack TO soctrack;
EOF
```

> **PENTING:** Ganti `GANTI_PASSWORD_INI` dengan password yang kuat.
> Catat password-nya, nanti dipakai di file `.env`.

Verifikasi:
```bash
sudo -u postgres psql -c "\l" | grep soctrack
```

---

## Step 4: Clone Repo & Setup Python Environment

```bash
# Buat directory
mkdir -p /opt/soctrack
cd /opt/soctrack

# Clone dari GitHub
git clone https://github.com/tenthdragon/soctrack.git .

# Buat virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright + Chromium
playwright install chromium
```

---

## Step 5: Setup Environment Variables

```bash
cp .env.example .env
nano .env
```

Edit isi `.env` seperti ini:

```
DATABASE_URL=postgresql://soctrack:GANTI_PASSWORD_INI@localhost:5432/soctrack
APP_HOST=0.0.0.0
APP_PORT=8000
APP_ENV=production
SECRET_KEY=GANTI_DENGAN_RANDOM_STRING_PANJANG
DEFAULT_BUSINESS_NAME=Army Group
SCRAPE_DELAY_MIN=30
SCRAPE_DELAY_MAX=90
SCRAPE_BATCH_SIZE=50
SCRAPE_START_HOUR=0
SCRAPE_MAX_POSTS_PER_CYCLE=350
TZ=Asia/Jakarta
```

> Untuk generate SECRET_KEY:
> ```bash
> python3 -c "import secrets; print(secrets.token_urlsafe(48))"
> ```

Simpan: `Ctrl+O`, Enter, `Ctrl+X`

---

## Step 6: Run Database Migrations

```bash
cd /opt/soctrack
source .venv/bin/activate
alembic upgrade head
```

---

## Step 7: Test — Jalankan Server Manual

```bash
cd /opt/soctrack
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Buka browser: `http://152.42.235.4:8000`
Kalau dashboard muncul, berarti berhasil. `Ctrl+C` untuk stop.

---

## Step 8: Setup systemd Service (Auto-start)

```bash
nano /etc/systemd/system/soctrack.service
```

Paste:

```ini
[Unit]
Description=SocTrack API Server
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/soctrack
Environment=PATH=/opt/soctrack/.venv/bin:/usr/bin
ExecStart=/opt/soctrack/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Simpan, lalu aktifkan:

```bash
systemctl daemon-reload
systemctl enable soctrack
systemctl start soctrack
systemctl status soctrack
```

Harus muncul **active (running)**.

---

## Step 9: Setup Nginx Reverse Proxy

```bash
nano /etc/nginx/sites-available/soctrack
```

Paste:

```nginx
server {
    listen 80;
    server_name 152.42.235.4;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Aktifkan:

```bash
ln -s /etc/nginx/sites-available/soctrack /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
```

Sekarang buka browser: `http://152.42.235.4` (tanpa port).

---

## Step 10: Setup Cron Jobs

```bash
crontab -e
```

Tambahkan di bawah:

```cron
# SocTrack: Account discovery — setiap hari jam 00:00 WIB
0 17 * * * cd /opt/soctrack && /opt/soctrack/.venv/bin/python jobs/account_discover.py >> /var/log/soctrack-discover.log 2>&1

# SocTrack: Post metrics scrape — setiap hari jam 00:30 WIB
30 17 * * * cd /opt/soctrack && /opt/soctrack/.venv/bin/python jobs/scrape_posts.py >> /var/log/soctrack-scrape.log 2>&1

# SocTrack: Delta calculation — setiap hari jam 03:00 WIB
0 20 * * * cd /opt/soctrack && /opt/soctrack/.venv/bin/python jobs/calculate_deltas.py >> /var/log/soctrack-deltas.log 2>&1
```

> **Catatan waktu:** Server di Singapore pakai UTC+8.
> WIB = UTC+7, jadi 00:00 WIB = 17:00 UTC (hari sebelumnya di UTC).
> Tapi Singapore (UTC+8) berarti cron jam 17 UTC = 01:00 SGT.
> Sesuaikan jika server timezone berbeda. Cek dengan: `timedatectl`

Simpan: `Ctrl+O`, Enter, `Ctrl+X`

---

## Step 11: Setup Firewall

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
ufw status
```

---

## Step 12: (Opsional) Setup Domain + HTTPS

Kalau nanti punya domain (misal soctrack.armygroup.com):

```bash
# Update nginx server_name
nano /etc/nginx/sites-available/soctrack
# Ganti: server_name 152.42.235.4;
# Jadi:  server_name soctrack.armygroup.com;

systemctl restart nginx

# Install SSL certificate
certbot --nginx -d soctrack.armygroup.com
```

---

## Useful Commands

```bash
# Cek status server
systemctl status soctrack

# Restart server setelah update code
cd /opt/soctrack && git pull && systemctl restart soctrack

# Lihat logs
journalctl -u soctrack -f              # API server logs
tail -f /var/log/soctrack-scrape.log   # Scraper logs
tail -f /var/log/soctrack-discover.log # Discovery logs

# Manual test scraper
cd /opt/soctrack && source .venv/bin/activate
python jobs/scrape_posts.py

# Cek database
sudo -u postgres psql soctrack -c "SELECT count(*) FROM posts;"
```
