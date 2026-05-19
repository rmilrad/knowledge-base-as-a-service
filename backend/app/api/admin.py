from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import delete as sql_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_admin_user
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User

router = APIRouter()


@router.get("/stats")
async def admin_stats(
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Return platform-wide stats for the admin dashboard."""

    # Totals
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    total_kbs = (await db.execute(select(func.count(KnowledgeBase.id)))).scalar() or 0
    total_docs = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    total_chunks = (await db.execute(select(func.count(Chunk.id)))).scalar() or 0

    # Document status breakdown
    status_rows = (
        await db.execute(
            select(Document.status, func.count(Document.id))
            .group_by(Document.status)
        )
    ).all()
    doc_statuses = {row[0]: row[1] for row in status_rows}

    # Storage — file uploads (S3) + chunk text content
    file_bytes = (
        await db.execute(select(func.coalesce(func.sum(Document.file_size_bytes), 0)))
    ).scalar() or 0
    chunk_text_bytes = (
        await db.execute(select(func.coalesce(func.sum(func.length(Chunk.content)), 0)))
    ).scalar() or 0
    total_bytes = file_bytes + chunk_text_bytes

    # Recent users (last 20)
    recent_users_rows = (
        await db.execute(
            select(User.id, User.email, User.name, User.created_at)
            .order_by(User.created_at.desc())
            .limit(20)
        )
    ).all()
    recent_users = [
        {
            "id": str(r[0]),
            "email": r[1],
            "name": r[2],
            "created_at": r[3].isoformat() if r[3] else None,
        }
        for r in recent_users_rows
    ]

    # Top KBs by actual chunk count (live query, not cached counters)
    top_kbs_rows = (
        await db.execute(
            select(
                KnowledgeBase.id,
                KnowledgeBase.name,
                func.count(func.distinct(Document.id)).label("doc_count"),
                func.count(Chunk.id).label("chunk_count"),
                User.email,
            )
            .join(User, KnowledgeBase.user_id == User.id)
            .outerjoin(Document, Document.kb_id == KnowledgeBase.id)
            .outerjoin(Chunk, Chunk.kb_id == KnowledgeBase.id)
            .group_by(KnowledgeBase.id, KnowledgeBase.name, User.email)
            .order_by(func.count(Chunk.id).desc())
            .limit(20)
        )
    ).all()
    top_kbs = [
        {
            "id": str(r[0]),
            "name": r[1],
            "document_count": r[2],
            "chunk_count": r[3],
            "owner_email": r[4],
        }
        for r in top_kbs_rows
    ]

    # Recent documents (last 20)
    recent_docs_rows = (
        await db.execute(
            select(
                Document.id,
                Document.title,
                Document.status,
                Document.file_type,
                Document.chunk_count,
                Document.created_at,
                KnowledgeBase.name,
            )
            .join(KnowledgeBase, Document.kb_id == KnowledgeBase.id)
            .order_by(Document.created_at.desc())
            .limit(20)
        )
    ).all()
    recent_docs = [
        {
            "id": str(r[0]),
            "title": r[1],
            "status": r[2],
            "file_type": r[3],
            "chunk_count": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
            "kb_name": r[6],
        }
        for r in recent_docs_rows
    ]

    return {
        "totals": {
            "users": total_users,
            "knowledge_bases": total_kbs,
            "documents": total_docs,
            "chunks": total_chunks,
            "storage_bytes": total_bytes,
        },
        "doc_statuses": doc_statuses,
        "recent_users": recent_users,
        "top_kbs": top_kbs,
        "recent_docs": recent_docs,
    }


@router.post("/cleanup-guests")
async def cleanup_guests(
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete guest users older than 24 hours and all their data (cascading)."""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(User).where(User.is_guest == True, User.created_at < cutoff)  # noqa: E712
    )
    guests = result.scalars().all()
    count = len(guests)
    for guest in guests:
        await db.delete(guest)  # cascade deletes KBs, docs, chunks, api_keys
    await db.commit()
    return {"deleted": count}
