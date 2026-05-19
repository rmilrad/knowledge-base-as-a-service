import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import create_access_token, get_current_user, hash_password, verify_dummy_password, verify_password
from app.middleware.rate_limit import limiter
from app.models.user import User
from app.schemas.user import MeResponse, TokenResponse, UserLogin, UserRegister

router = APIRouter()


@router.post("/register", response_model=TokenResponse)
@limiter.limit("5/hour")
async def register(request: Request, body: UserRegister, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None:
        # Run a bcrypt verify against a dummy hash to equalize timing with
        # the existing-email path. Prevents email enumeration via timing.
        verify_dummy_password(body.password)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/guest", response_model=TokenResponse)
@limiter.limit("5/hour")
async def guest_login(request: Request, db: AsyncSession = Depends(get_db)):
    """Create a temporary guest account. Data will be deleted after the session."""
    guest_id = uuid.uuid4().hex[:8]
    guest_email = f"guest-{guest_id}@guest.kbaas.dev"
    user = User(
        email=guest_email,
        password_hash=hash_password(uuid.uuid4().hex),
        name=f"Guest {guest_id}",
        is_guest=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)):
    return MeResponse(id=str(user.id), email=user.email, name=user.name, is_admin=user.is_admin, is_guest=user.is_guest)
