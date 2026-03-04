"""
SocTrack — TikTok Social Media Performance Tracker
FastAPI application entry point.
"""

from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.business import Business
from app.models.brand import Brand
from app.api import brands, posts, snapshots, discovery

app = FastAPI(
    title="SocTrack API",
    description="TikTok Social Media Performance Tracker with Intelligent Discovery & Competitor Monitoring",
    version="1.0.0",
)

# CORS — allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(brands.router, prefix="/api", tags=["Brands"])
app.include_router(posts.router, prefix="/api", tags=["Posts"])
app.include_router(snapshots.router, prefix="/api", tags=["Snapshots & Metrics"])
app.include_router(discovery.router, prefix="/api", tags=["Discovery"])

# Serve frontend static files
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "soctrack", "version": "1.0.0"}


@app.post("/api/setup", tags=["Setup"])
def initial_setup(db: Session = Depends(get_db)):
    """
    One-time setup: create default business and Roove brand.
    Safe to call multiple times (idempotent).
    """
    # Check if business exists
    business = db.query(Business).filter(Business.name == settings.default_business_name).first()
    if not business:
        business = Business(name=settings.default_business_name)
        db.add(business)
        db.commit()
        db.refresh(business)

    # Check if Roove brand exists
    roove = db.query(Brand).filter(Brand.tiktok_username == "@roove.co.id").first()
    if not roove:
        roove = Brand(
            business_id=business.id,
            name="Roove",
            tiktok_username="@roove.co.id",
            is_competitor=False,
            color="#8B5CF6",
            logo_emoji="🧴",
            auto_discover=True,
        )
        db.add(roove)
        db.commit()
        db.refresh(roove)

    return {
        "business_id": str(business.id),
        "brand_id": str(roove.id),
        "brand_name": roove.name,
        "message": "Setup complete",
    }
