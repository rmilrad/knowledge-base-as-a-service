import logging
import time
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.services.chunking import chunk_text
from app.services.embedding import generate_embeddings
from app.services.storage import download_from_s3

logger = logging.getLogger("kbaas.ingestion")


async def extract_text_from_file(s3_key: str, file_type: str) -> str:
    logger.info(f"  Extracting text from file: type={file_type}, s3_key={s3_key}")
    data = await download_from_s3(s3_key)
    logger.info(f"  Downloaded {len(data)} bytes from S3")

    if file_type == "pdf":
        from pypdf import PdfReader
        import io

        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        logger.info(f"  Extracted text from {len(pages)} PDF pages")
        return "\n\n".join(pages)

    if file_type in ("md", "txt"):
        text = data.decode("utf-8", errors="replace")
        logger.info(f"  Read {len(text)} characters of text")
        return text

    text = data.decode("utf-8", errors="replace")
    logger.info(f"  Read {len(text)} characters (fallback decode)")
    return text


async def extract_text_from_url(url: str) -> str:
    logger.info(f"  Fetching URL: {url}")
    try:
        from trafilatura import extract

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
            logger.info(f"  Fetched {len(html)} chars of HTML (status {response.status_code})")

        text = extract(html)
        if text:
            logger.info(f"  Trafilatura extracted {len(text)} chars")
            return text

        logger.info("  Trafilatura returned empty, falling back to BeautifulSoup")
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        logger.info(f"  BeautifulSoup extracted {len(text)} chars")
        return text
    except Exception as e:
        raise RuntimeError(f"Failed to extract text from URL: {e}") from e


async def ingest_document(doc_id: str):
    start = time.time()
    logger.info(f"[{doc_id}] Starting ingestion")

    async with async_session() as db:
        try:
            result = await db.execute(
                select(Document).where(Document.id == UUID(doc_id))
            )
            doc = result.scalar_one_or_none()
            if not doc:
                logger.error(f"[{doc_id}] Document not found in database")
                return

            logger.info(f"[{doc_id}] Document: title={doc.title}, type={doc.source_type}, file_type={doc.file_type}")
            doc.status = "processing"
            await db.commit()

            # Step 1: Extract text
            t0 = time.time()
            if doc.source_type == "url" and doc.source_url:
                raw_text = await extract_text_from_url(doc.source_url)
            elif doc.s3_key and doc.file_type:
                raw_text = await extract_text_from_file(doc.s3_key, doc.file_type)
            else:
                raise RuntimeError("No source available for extraction")
            logger.info(f"[{doc_id}] Text extraction: {len(raw_text)} chars in {time.time()-t0:.1f}s")

            if not raw_text.strip():
                raise RuntimeError("No text content could be extracted")

            # Step 2: Chunk
            t0 = time.time()
            chunks = chunk_text(raw_text)
            if not chunks:
                raise RuntimeError("Text chunking produced no chunks")
            logger.info(f"[{doc_id}] Chunking: {len(chunks)} chunks in {time.time()-t0:.1f}s")

            # Step 3: Embed (prefix chunks with doc title for better retrieval)
            t0 = time.time()
            title_prefix = doc.title or "Untitled"
            chunks_for_embedding = [f"{title_prefix}: {c}" for c in chunks]
            embeddings = await generate_embeddings(chunks_for_embedding)
            logger.info(f"[{doc_id}] Embedding: {len(embeddings)} vectors in {time.time()-t0:.1f}s")

            # Step 4: Store
            t0 = time.time()
            chunk_objects = []
            for i, (text, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_obj = Chunk(
                    document_id=doc.id,
                    kb_id=doc.kb_id,
                    content=text,
                    chunk_index=i,
                    token_count=len(text.split()),
                    embedding=embedding,
                    metadata_={"source_title": doc.title or "Untitled"},
                )
                chunk_objects.append(chunk_obj)

            db.add_all(chunk_objects)

            doc.status = "completed"
            doc.chunk_count = len(chunk_objects)

            kb_result = await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == doc.kb_id)
            )
            kb = kb_result.scalar_one()
            kb.document_count += 1
            kb.chunk_count += len(chunk_objects)

            await db.commit()
            elapsed = time.time() - start
            logger.info(f"[{doc_id}] Ingestion complete: {len(chunk_objects)} chunks stored in {elapsed:.1f}s")

        except Exception as e:
            elapsed = time.time() - start
            logger.exception(f"[{doc_id}] Ingestion FAILED after {elapsed:.1f}s: {e}")
            await db.rollback()
            result = await db.execute(
                select(Document).where(Document.id == UUID(doc_id))
            )
            doc = result.scalar_one_or_none()
            if doc:
                doc.status = "error"
                doc.error_message = str(e)[:500]
                await db.commit()
