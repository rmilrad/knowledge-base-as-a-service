import hashlib
import secrets
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.api_key import ApiKey
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User

router = APIRouter()


class ApiKeyCreate(BaseModel):
    name: Optional[str] = None


class ApiKeyResponse(BaseModel):
    id: UUID
    name: Optional[str]
    key_prefix: str
    last_used_at: Optional[str]
    created_at: str

    model_config = {"from_attributes": True}


class ApiKeyCreated(BaseModel):
    key: str


async def _get_user_kb(db: AsyncSession, kb_id: UUID, user_id: UUID) -> KnowledgeBase:
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user_id,
        )
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


@router.get("/{kb_id}/keys", response_model=List[ApiKeyResponse])
async def list_keys(
    kb_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_kb(db, kb_id, user.id)
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == user.id, ApiKey.kb_id == kb_id)
        .order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()
    return [
        ApiKeyResponse(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            last_used_at=str(k.last_used_at) if k.last_used_at else None,
            created_at=str(k.created_at),
        )
        for k in keys
    ]


@router.post("/{kb_id}/keys", response_model=ApiKeyCreated, status_code=201)
async def create_key(
    kb_id: UUID,
    body: ApiKeyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_kb(db, kb_id, user.id)

    raw_key = f"kb_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    api_key = ApiKey(
        user_id=user.id,
        kb_id=kb_id,
        key_hash=key_hash,
        key_prefix=raw_key[:10],
        name=body.name,
    )
    db.add(api_key)
    await db.commit()
    return ApiKeyCreated(key=raw_key)


@router.delete("/{kb_id}/keys/{key_id}", status_code=204)
async def revoke_key(
    kb_id: UUID,
    key_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_kb(db, kb_id, user.id)
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.user_id == user.id,
            ApiKey.kb_id == kb_id,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    await db.delete(key)
    await db.commit()
