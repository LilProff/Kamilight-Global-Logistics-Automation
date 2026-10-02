"""Password hashing and strength rules. Standard library only (scrypt), so there is nothing extra to keep patched."""

import base64
import hashlib
import hmac
import os

_N, _R, _P = 2**14, 8, 1
MIN_PASSWORD_LENGTH = 10
_COMMON = {"password", "12345678", "123456789", "qwerty", "letmein", "admin", "welcome", "kamilight", "kgl2026", "iloveyou"}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_N}${_R}${_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Verified against when the email doesn't exist, so a wrong email and a wrong password take the same time
_DUMMY_HASH = hash_password("not-a-real-account")


def burn_time() -> None:
    verify_password("x", _DUMMY_HASH)


def password_problem(password: str, email: str = "") -> str | None:
    """Plain-language reason a new password is refused, or None if it's fine."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > 200:
        return "That password is too long."
    low = password.lower()
    if low in _COMMON or (email and low == email.lower()) or (email and email.split("@")[0].lower() in low and len(email.split("@")[0]) >= 4):
        return "That password is too easy to guess. Use something less obvious."
    if len(set(password)) < 5:
        return "That password is too repetitive."
    return None
