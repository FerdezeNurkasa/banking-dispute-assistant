"""Authentication & authorization: password hashing, JWT tokens, login lockout and role checks."""
import base64
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.config import settings
from app.db import SessionLocal, User

log = logging.getLogger("security")

PBKDF2_ITERATIONS = 600_000  # OWASP recommendation for PBKDF2-HMAC-SHA256


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    """Salted PBKDF2 hash. Format: pbkdf2_sha256$iterations$salt$hash"""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return "$".join(["pbkdf2_sha256", str(PBKDF2_ITERATIONS),
                     base64.b64encode(salt).decode(), base64.b64encode(digest).decode()])


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_b64, digest_b64 = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iterations))
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))  # constant-time comparison
    except (ValueError, TypeError):
        return False


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- login
class CurrentUser(BaseModel):
    username: str
    full_name: str
    role: str


def authenticate(username: str, password: str) -> User:
    """Checks the password and applies lockout after too many failed attempts."""
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    with SessionLocal() as db:
        user = db.get(User, username)
        if not user or not user.is_active:
            log.warning("Failed login for unknown/inactive user %r", username)
            raise invalid  # same message as a wrong password, so usernames can't be guessed

        now = datetime.now(timezone.utc)
        locked_until = _aware(user.locked_until)
        if locked_until and locked_until > now:
            minutes = int((locked_until - now).total_seconds() // 60) + 1
            raise HTTPException(status.HTTP_423_LOCKED, f"Account locked. Try again in {minutes} minutes.")

        if not verify_password(password, user.password_hash):
            user.failed_logins += 1
            if user.failed_logins >= settings.MAX_FAILED_LOGINS:
                user.locked_until = now + timedelta(minutes=settings.LOCKOUT_MINUTES)
                user.failed_logins = 0
                log.warning("User %s locked after too many failed logins", username)
            db.commit()
            raise invalid

        user.failed_logins = 0
        user.locked_until = None
        db.commit()
        log.info("User %s logged in", username)
        return user


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user.username, "role": user.role, "name": user.full_name,
               "iat": now, "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


# ---------------------------------------------------------------- request dependencies
_bearer = HTTPBearer(auto_error=False)


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> CurrentUser:
    unauthorized = lambda msg: HTTPException(status.HTTP_401_UNAUTHORIZED, msg, headers={"WWW-Authenticate": "Bearer"})
    if not creds:
        raise unauthorized("Not logged in")
    try:
        payload = jwt.decode(creds.credentials, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise unauthorized("Session expired, please log in again")
    except jwt.InvalidTokenError:
        raise unauthorized("Invalid token")

    # Check the database on every request, so a deactivated user loses access immediately
    with SessionLocal() as db:
        user = db.get(User, payload.get("sub"))
        if not user or not user.is_active:
            raise unauthorized("User no longer has access")
        return CurrentUser(username=user.username, full_name=user.full_name, role=user.role)


def require_role(*roles: str):
    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"This action requires role: {', '.join(roles)}")
        return user
    return checker