"""Post model — individual social media post being tracked."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("tiktok_video_id", name="uq_posts_tiktok_video_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    platform: Mapped[str] = mapped_column(
        String(20), nullable=False, default="tiktok"
    )  # "tiktok", "instagram"
    tiktok_url: Mapped[str] = mapped_column(Text, nullable=False)  # works for any platform URL
    tiktok_video_id: Mapped[str] = mapped_column(String(255), nullable=False)  # shortcode for IG
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # post thumbnail
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    tracking_since: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="link"
    )  # "account", "link", "discovery"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    brand = relationship("Brand", back_populates="posts")
    snapshots = relationship("Snapshot", back_populates="post", cascade="all, delete-orphan")
