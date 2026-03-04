"""
SocTrack — TikTok Social Media Performance Tracker
FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
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
