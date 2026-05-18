from typing import List
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.document import BulkUrlIngest, DocumentResponse, DocumentUpdate, UrlIngest
from app.services.ingestion import ingest_document
from app.services.storage import upload_to_s3

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


@router.get("/{kb_id}/documents", response_model=List[DocumentResponse])
async def list_documents(
    kb_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_kb(db, kb_id, user.id)
    result = await db.execute(
        select(Document)
        .where(Document.kb_id == kb_id)
        .order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.post("/{kb_id}/documents/upload", response_model=List[DocumentResponse], status_code=201)
async def upload_documents(
    kb_id: UUID,
    files: List[UploadFile],
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    kb = await _get_user_kb(db, kb_id, user.id)

    allowed_types = {"pdf", "md", "txt", "text", "markdown"}
    docs = []

    for file in files:
        ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
        if ext not in allowed_types:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

        content = await file.read()
        if len(content) > 500 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (max 500MB)")

        file_type = "md" if ext in ("md", "markdown") else ("txt" if ext in ("txt", "text") else ext)

        doc = Document(
            kb_id=kb.id,
            title=file.filename,
            source_type="file_upload",
            file_type=file_type,
            file_size_bytes=len(content),
            status="pending",
        )
        db.add(doc)
        await db.flush()

        s3_key = f"{user.id}/{kb.id}/{doc.id}/{file.filename}"
        await upload_to_s3(s3_key, content)
        doc.s3_key = s3_key

        docs.append(doc)

    await db.commit()
    for doc in docs:
        await db.refresh(doc)

    for doc in docs:
        background_tasks.add_task(ingest_document, str(doc.id))

    return docs


@router.post("/{kb_id}/documents/url", response_model=DocumentResponse, status_code=201)
async def ingest_url(
    kb_id: UUID,
    body: UrlIngest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_kb(db, kb_id, user.id)

    # Detect file type from URL extension
    url_path = urlparse(body.url).path.lower()
    if url_path.endswith(".pdf"):
        file_type = "pdf"
    else:
        file_type = "html"

    doc = Document(
        kb_id=kb_id,
        title=body.url,
        source_type="url",
        source_url=body.url,
        file_type=file_type,
        status="pending",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    background_tasks.add_task(ingest_document, str(doc.id))
    return doc


@router.post("/{kb_id}/documents/urls", response_model=List[DocumentResponse], status_code=201)
async def ingest_urls(
    kb_id: UUID,
    body: BulkUrlIngest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_kb(db, kb_id, user.id)

    docs = []
    for url in body.urls:
        url = url.strip()
        if not url:
            continue
        url_path = urlparse(url).path.lower()
        file_type = "pdf" if url_path.endswith(".pdf") else "html"
        doc = Document(
            kb_id=kb_id,
            title=url,
            source_type="url",
            source_url=url,
            file_type=file_type,
            status="pending",
        )
        db.add(doc)
        docs.append(doc)

    await db.commit()
    for doc in docs:
        await db.refresh(doc)

    for doc in docs:
        background_tasks.add_task(ingest_document, str(doc.id))

    return docs


@router.patch("/{kb_id}/documents/{doc_id}", response_model=DocumentResponse)
async def rename_document(
    kb_id: UUID,
    doc_id: UUID,
    body: DocumentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_kb(db, kb_id, user.id)
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.kb_id == kb_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.title = body.title.strip()
    await db.commit()
    await db.refresh(doc)
    return doc


@router.post("/{kb_id}/documents/{doc_id}/retry", response_model=DocumentResponse)
async def retry_document(
    kb_id: UUID,
    doc_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_kb(db, kb_id, user.id)
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.kb_id == kb_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status not in ("error", "completed"):
        raise HTTPException(status_code=400, detail="Document is not in a retryable state")

    if doc.status == "completed" and doc.chunk_count > 0:
        from app.models.chunk import Chunk
        from sqlalchemy import delete as sql_delete
        await db.execute(sql_delete(Chunk).where(Chunk.document_id == doc.id))
        kb_result = await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = kb_result.scalar_one()
        kb.document_count = max(0, kb.document_count - 1)
        kb.chunk_count = max(0, kb.chunk_count - doc.chunk_count)

    doc.status = "pending"
    doc.error_message = None
    doc.chunk_count = 0
    await db.commit()
    await db.refresh(doc)

    background_tasks.add_task(ingest_document, str(doc.id))
    return doc


@router.delete("/{kb_id}/documents/{doc_id}", status_code=204)
async def delete_document(
    kb_id: UUID,
    doc_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_kb(db, kb_id, user.id)
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.kb_id == kb_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.delete(doc)

    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
    )
    kb = kb_result.scalar_one()
    kb.document_count = max(0, kb.document_count - 1)
    kb.chunk_count = max(0, kb.chunk_count - doc.chunk_count)

    await db.commit()


