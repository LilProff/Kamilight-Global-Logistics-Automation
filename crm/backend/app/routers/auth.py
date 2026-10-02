from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import authenticate, client_ip, current_user_obj, issue_token
from app.db import get_db
from app.models import User
from app.security import hash_password, password_problem, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=300)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=300)
    new_password: str = Field(max_length=300)


def _me(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = authenticate(db, body.email, body.password, client_ip(request))
    return {"token": issue_token(user), **_me(user)}


@router.get("/me")
def me(user: User = Depends(current_user_obj)):
    return _me(user)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, user: User = Depends(current_user_obj), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(422, "Your current password isn't right.")
    if problem := password_problem(body.new_password, user.email):
        raise HTTPException(422, problem)
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # every other signed-in device is signed out
    db.commit()
    return {"token": issue_token(user)}
