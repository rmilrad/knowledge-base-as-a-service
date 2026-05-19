import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
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


def _kb_id_from_request(request: Request) -> UUID:
    """Resolve the KB the *current API key* is scoped to.

    Set by middleware in `get_current_user` when auth uses an API key.
    Refuses JWT-authenticated requests on the public API (this endpoint is
    intended for programmatic API-key access only)."""
    if getattr(request.state, "auth_method", None) != "api_key":
        raise HTTPException(
            status_code=403,
            detail="Public API requires API key authentication",
        )
    kb_id = getattr(request.state, "api_key_kb_id", None)
    if kb_id is None:
        raise HTTPException(
            status_code=400,
            detail="API key is not scoped to a knowledge base",
        )
    return kb_id


@router.post("/query", response_model=QueryResponse)
async def public_query(
    body: QueryRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    kb_id = _kb_id_from_request(request)
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
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    kb_id = _kb_id_from_request(request)
    chunks = await retrieve_chunks(db, kb_id, body.question, body.top_k)
    return StreamingResponse(
        stream_answer(body.question, chunks),
        media_type="text/event-stream",
    )
