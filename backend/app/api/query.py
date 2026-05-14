from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.query import QueryRequest, QueryResponse
from app.services.llm import generate_answer, stream_answer
from app.services.retrieval import retrieve_chunks

router = APIRouter()


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


@router.post("/{kb_id}/query", response_model=QueryResponse)
async def query_kb(
    kb_id: UUID,
    body: QueryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_kb(db, kb_id, user.id)
    chunks = await retrieve_chunks(db, kb_id, body.question, body.top_k)
    answer = await generate_answer(
        body.question, chunks, model=body.model, response_style=body.response_style
    )
    return QueryResponse(
        answer=answer,
        sources=[
            {"title": c["title"], "content": c["content"], "score": c["score"]}
            for c in chunks
        ],
    )


@router.post("/{kb_id}/chat")
async def chat_kb(
    kb_id: UUID,
    body: QueryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_kb(db, kb_id, user.id)
    chunks = await retrieve_chunks(db, kb_id, body.question, body.top_k)
    return StreamingResponse(
        stream_answer(
            body.question, chunks, model=body.model, response_style=body.response_style
        ),
        media_type="text/event-stream",
    )
