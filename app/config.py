"""
SocTrack Configuration
Loads settings from environment variables.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://soctrack:soctrack@localhost:5432/soctrack"

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "production"
    secret_key: str = "change-this-to-a-random-secret-key"

    # Default business
    default_business_name: str = "Army Group"

    # Scraper settings
    scrape_delay_min: int = 30
    scrape_delay_max: int = 90
    scrape_batch_size: int = 50
    scrape_start_hour: int = 0
    scrape_max_posts_per_cycle: int = 350

    # Proxy (opsional)
    proxy_url: Optional[str] = None
    proxy_enabled: bool = False

    # Timezone
    tz: str = "Asia/Jakarta"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
