"""DiscoveryResult model — posts found via FYP Scanner keyword search."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, BigInteger, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DiscoveryResult(Base):
    __tablename__ = "discovery_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    tiktok_url: Mapped[str] = mapped_column(Text, nullable=False)
    tiktok_video_id: Mapped[str] = mapped_column(String(255), nullable=False)
    creator_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    views_at_discovery: Mapped[int] = mapped_column(BigInteger, default=0)
    likes_at_discovery: Mapped[int] = mapped_column(BigInteger, default=0)
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
