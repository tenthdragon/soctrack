"""Brand model — TikTok account being tracked (own or competitor)."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tiktok_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_competitor: Mapped[bool] = mapped_column(Boolean, default=False)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    logo_emoji: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    auto_discover: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    business = relationship("Business", back_populates="brands")
    posts = relationship("Post", back_populates="brand", cascade="all, delete-orphan")
