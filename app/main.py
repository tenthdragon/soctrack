"""
SocTrack — Social Media Performance Tracker
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
from app.models.user import User
from app.auth import hash_password
from app.api import brands, posts, snapshots, discovery, auth

app = FastAPI(
    title="SocTrack API",
    description="Social Media Performance Tracker",
    version="1.1.0",
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
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(brands.router, prefix="/api", tags=["Brands"])
app.include_router(posts.router, prefix="/api", tags=["Posts"])
app.include_router(snapshots.router, prefix="/api", tags=["Snapshots & Metrics"])
app.include_router(discovery.router, prefix="/api", tags=["Discovery"])

@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "soctrack", "version": "1.1.0"}


@app.post("/api/setup", tags=["Setup"])
def initial_setup(db: Session = Depends(get_db)):
    """
    One-time setup: create default business, brand, and owner user.
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

    # Create default owner if no users exist
    owner_created = False
    default_email = "admin@soctrack.local"
    default_password = "soctrack2024"

    user_count = db.query(User).count()
    if user_count == 0:
        owner = User(
            email=default_email,
            hashed_password=hash_password(default_password),
            full_name="Administrator",
            role="owner",
        )
        db.add(owner)
        db.commit()
        owner_created = True

    result = {
        "business_id": str(business.id),
        "brand_id": str(roove.id),
        "brand_name": roove.name,
        "message": "Setup complete",
    }

    if owner_created:
        result["owner_created"] = True
        result["owner_email"] = default_email
        result["owner_password"] = default_password
        result["warning"] = "Segera ganti password default!"

    return result


# Serve frontend static files — MUST be last (catch-all)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
