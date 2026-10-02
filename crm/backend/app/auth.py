from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import DEV_ADMIN_PASSWORD, get_settings
from app.db import get_db
from app.models import LoginAttempt, User, utcnow
from app.security import burn_time, hash_password, verify_password

bearer = HTTPBearer(auto_error=False)


def ensure_admin(db: Session) -> None:
    """First start: create the admin account from ADMIN_EMAIL / ADMIN_PASSWORD. Never touches an existing user table."""
    s = get_settings()
    if db.scalar(select(func.count()).select_from(User)):
        return
    if s.is_production and s.admin_password == DEV_ADMIN_PASSWORD:
        raise RuntimeError("Set ADMIN_PASSWORD to a real password before the first start in production.")
    db.add(User(email=s.admin_email.strip().lower(), name=s.admin_name, password_hash=hash_password(s.admin_password), role="admin"))
    db.commit()


def issue_token(user: User) -> str:
    s = get_settings()
    exp = datetime.now(UTC) + timedelta(hours=s.jwt_hours)
    return jwt.encode({"sub": user.email, "uid": user.id, "tv": user.token_version, "exp": exp}, s.jwt_secret, algorithm="HS256")


def client_ip(request: Request) -> str:
    return (request.client.host if request.client else "") or ""


def check_lockout(db: Session, email: str, ip: str) -> None:
    s = get_settings()
    since = utcnow() - timedelta(minutes=s.login_window_minutes)
    by_email = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.email == email, LoginAttempt.at >= since))
    by_ip = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.ip == ip, LoginAttempt.at >= since)) if ip else 0
    if by_email >= s.login_max_failures or by_ip >= s.login_ip_max_failures:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed attempts. Try again in {s.login_window_minutes} minutes.",
            headers={"Retry-After": str(s.login_window_minutes * 60)},
        )


def authenticate(db: Session, email: str, password: str, ip: str) -> User:
    """Check a sign-in. Wrong email and wrong password look identical to the caller, and both count toward lockout."""
    email = email.strip().lower()
    check_lockout(db, email, ip)
    user = db.scalar(select(User).where(User.email == email))
    ok = False
    if user is not None:
        ok = verify_password(password, user.password_hash) and user.active
    else:
        burn_time()
    if not ok:
        db.add(LoginAttempt(email=email[:200], ip=ip[:64]))
        db.execute(delete(LoginAttempt).where(LoginAttempt.at < utcnow() - timedelta(days=1)))
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is wrong.")
    db.execute(delete(LoginAttempt).where(LoginAttempt.email == email))
    user.last_login_at = utcnow()
    db.commit()
    return user


def current_user_obj(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue")
    try:
        claims = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Sign in again.") from None
    uid = claims.get("uid")
    user = db.get(User, uid) if isinstance(uid, int) else None  # tokens from before accounts existed have no uid
    # Deactivating a user or changing their password signs them out everywhere (token_version)
    if user is None or not user.active or user.token_version != claims.get("tv"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Sign in again.")
    return user


def current_user(user: User = Depends(current_user_obj)) -> str:
    return user.email


def require_admin(user: User = Depends(current_user_obj)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can do that.")
    return user
