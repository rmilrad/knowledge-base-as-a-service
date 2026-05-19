import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.user import User

security = HTTPBearer()

# A dummy bcrypt hash used to equalize timing for unknown-email login attempts.
# Generated once at import; cost ~250ms verify, matches real password verify.
_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"dummy-password-for-timing-equalization", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def verify_dummy_password(password: str) -> None:
    """Run bcrypt verify against a fixed dummy hash to equalize login timing
    when the supplied email does not exist. Discards the result."""
    bcrypt.checkpw(password.encode(), _DUMMY_PASSWORD_HASH.encode())


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": now + timedelta(minutes=settings.jwt_expiration_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate via JWT or API key.

    Sets `request.state.api_key_kb_id` to the KB the API key is scoped to,
    or None for JWT auth. Routes that take a `kb_id` path param can use
    `enforce_api_key_kb_scope(request, kb_id)` to verify the key is allowed
    to access that specific KB.
    """
    token = credentials.credentials

    if token.startswith("kb_"):
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        result = await db.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash)
        )
        api_key = result.scalar_one_or_none()
        if not api_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

        # Throttle last_used_at writes to once per minute per key to avoid
        # a DB write on every request (lock contention + DoS amplifier).
        now = datetime.now(timezone.utc)
        if api_key.last_used_at is None or (now - api_key.last_used_at.replace(tzinfo=timezone.utc) if api_key.last_used_at.tzinfo is None else now - api_key.last_used_at).total_seconds() > 60:
            api_key.last_used_at = now
            await db.commit()

        result = await db.execute(select(User).where(User.id == api_key.user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        # Expose the API key's KB scope so routes can enforce it
        request.state.api_key_kb_id = api_key.kb_id
        request.state.auth_method = "api_key"
        return user

    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    request.state.api_key_kb_id = None
    request.state.auth_method = "jwt"
    return user


def enforce_api_key_kb_scope(request: Request, kb_id: UUID) -> None:
    """If the request was authenticated by an API key scoped to a specific KB,
    require that this kb_id matches. JWT auth (api_key_kb_id is None) is
    unaffected — JWT users are checked via the usual KB-ownership query.

    Raises 403 if the API key is not authorized for this KB.
    """
    api_key_kb_id = getattr(request.state, "api_key_kb_id", None)
    if api_key_kb_id is not None and api_key_kb_id != kb_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key is not authorized for this knowledge base",
        )


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
