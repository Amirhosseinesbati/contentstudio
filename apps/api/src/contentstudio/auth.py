import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import LoginSession, User, now

COOKIE_NAME = "contentstudio_session"
password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(48)
    db.add(
        LoginSession(
            token_hash=token_hash(token),
            user_id=user.id,
            expires_at=now() + timedelta(hours=get_settings().session_hours),
        )
    )
    db.commit()
    return token


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    session = db.get(LoginSession, token_hash(token))
    if not session or session.expires_at.replace(tzinfo=None) <= now().replace(tzinfo=None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account unavailable")
    return user


def operator(user: User = Depends(current_user)) -> User:
    if user.role not in ("admin", "operator"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operator role required")
    return user


def admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return user


def require_service_token(request: Request) -> None:
    expected = get_settings().service_token
    received = request.headers.get("X-Service-Token", "")
    if not expected or not secrets.compare_digest(received, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid service token")


def user_data(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "workspace_id": user.workspace_id,
    }
