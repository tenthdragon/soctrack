"""ScrapeLog model — logging each scrape attempt for monitoring."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScrapeLog(Base):
    __tablename__ = "scrape_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    post_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("posts.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "success", "failed", "timeout", "blocked"
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
