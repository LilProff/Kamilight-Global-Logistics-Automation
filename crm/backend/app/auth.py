import hmac
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

bearer = HTTPBearer(auto_error=False)


def check_login(email: str, password: str) -> bool:
    s = get_settings()
    return hmac.compare_digest(email.strip().lower(), s.admin_email.lower()) and hmac.compare_digest(
        password, s.admin_password
    )


def issue_token(email: str) -> str:
    s = get_settings()
    exp = datetime.now(UTC) + timedelta(hours=s.jwt_hours)
    return jwt.encode({"sub": email, "exp": exp}, s.jwt_secret, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue")
    try:
        claims = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Sign in again.") from None
    return claims["sub"]
