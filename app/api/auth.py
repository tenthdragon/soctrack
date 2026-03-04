"""Authentication endpoints — login, user management."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_owner,
)

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None
    role: str = "user"  # "owner" or "user"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ── Endpoints ────────────────────────────────────────────

@router.post("/auth/login", response_model=LoginResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """Login with email and password."""
    user = db.query(User).filter(
        User.email == data.email,
        User.is_active == True,
    ).first()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email atau password salah")

    token = create_access_token(str(user.id), user.email, user.role)

    return LoginResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/auth/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    """Get current user info."""
    return user


@router.get("/auth/users", response_model=list[UserResponse])
def list_users(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """List all users (Owner only)."""
    return db.query(User).order_by(User.created_at).all()


@router.post("/auth/users", response_model=UserResponse, status_code=201)
def create_user(
    data: UserCreate,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Create a new user (Owner only)."""
    if data.role not in ("owner", "user"):
        raise HTTPException(status_code=400, detail="Role must be 'owner' or 'user'")

    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")

    new_user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.delete("/auth/users/{user_id}", status_code=204)
def delete_user(
    user_id: uuid.UUID,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Deactivate a user (Owner only). Cannot deactivate yourself."""
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Tidak bisa menghapus diri sendiri")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.is_active = False
    db.commit()
