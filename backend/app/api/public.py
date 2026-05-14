import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.query import QueryRequest, QueryResponse
from app.services.llm import generate_answer, stream_answer
from app.services.retrieval import retrieve_chunks

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def public_query(
    body: QueryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    kb_id = await _get_kb_from_api_key(db, user)
    if not kb_id:
        raise HTTPException(status_code=400, detail="API key is not scoped to a knowledge base")

    chunks = await retrieve_chunks(db, kb_id, body.question, body.top_k)
    answer = await generate_answer(body.question, chunks)
    return QueryResponse(
        answer=answer,
        sources=[
            {"title": c["title"], "content": c["content"], "score": c["score"]}
            for c in chunks
        ],
    )


@router.post("/chat")
async def public_chat(
    body: QueryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    kb_id = await _get_kb_from_api_key(db, user)
    if not kb_id:
        raise HTTPException(status_code=400, detail="API key is not scoped to a knowledge base")

    chunks = await retrieve_chunks(db, kb_id, body.question, body.top_k)
    return StreamingResponse(
        stream_answer(body.question, chunks),
        media_type="text/event-stream",
    )


async def _get_kb_from_api_key(db: AsyncSession, user: User):
    result = await db.execute(
        select(ApiKey.kb_id).where(ApiKey.user_id == user.id).limit(1)
    )
    row = result.first()
    return row.kb_id if row else None
