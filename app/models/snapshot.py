"""Snapshot model — daily metrics capture for a post."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (
        Index("ix_snapshots_post_recorded", "post_id", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id"), nullable=False)
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    likes: Mapped[int] = mapped_column(BigInteger, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    # Baseline: angka awal saat pertama kali di-scrape hari itu
    baseline_views: Mapped[int] = mapped_column(BigInteger, default=0)
    baseline_likes: Mapped[int] = mapped_column(BigInteger, default=0)
    baseline_comments: Mapped[int] = mapped_column(Integer, default=0)
    baseline_shares: Mapped[int] = mapped_column(Integer, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    post = relationship("Post", back_populates="snapshots")
