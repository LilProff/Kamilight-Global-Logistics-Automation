"""Staff accounts. Administrators only."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.models import User
from app.security import hash_password, password_problem

router = APIRouter(prefix="/api/users", tags=["team"], dependencies=[Depends(require_admin)])

Role = Literal["admin", "staff"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: str
    active: bool
    created_at: datetime
    last_login_at: datetime | None


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = Field(default="", max_length=200)
    role: Role = "staff"
    password: str = Field(max_length=300)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=300)  # reset


def _active_admins(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.active.is_(True)))


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.name, User.email)).all()


@router.post("", response_model=UserOut, status_code=201)
def create(body: UserCreate, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, f"{email} already has an account.")
    if problem := password_problem(body.password, email):
        raise HTTPException(422, problem)
    user = User(email=email, name=body.name.strip(), role=body.role, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update(user_id: int, body: UserUpdate, me: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    data = body.model_dump(exclude_unset=True)
    losing_admin = user.role == "admin" and user.active and (data.get("role") == "staff" or data.get("active") is False)
    if losing_admin and _active_admins(db) <= 1:
        raise HTTPException(409, "There must always be at least one active administrator.")
    if user.id == me.id and data.get("active") is False:
        raise HTTPException(409, "You can't deactivate your own account.")
    if "name" in data:
        user.name = (data["name"] or "").strip()
    if "role" in data and data["role"]:
        user.role = data["role"]
    if data.get("active") is not None and data["active"] != user.active:
        user.active = data["active"]
        user.token_version += 1
    if data.get("password"):
        if problem := password_problem(data["password"], user.email):
            raise HTTPException(422, problem)
        user.password_hash = hash_password(data["password"])
        user.token_version += 1
    db.commit()
    return user
