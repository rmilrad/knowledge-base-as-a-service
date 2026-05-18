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


def _validate_url(url: str) -> str:
    """Validate URL to prevent SSRF attacks."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError("URL must have a hostname")

    # Resolve hostname and check for private/reserved IPs
    try:
        resolved = socket.getaddrinfo(parsed.hostname, None)
        for _, _, _, _, sockaddr in resolved:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError(f"URL resolves to private/reserved IP: {ip}")
    except socket.gaierror:
        raise ValueError(f"Could not resolve hostname: {parsed.hostname}")

    return url


def _is_pdf_url(url: str, content_type: str | None = None) -> bool:
    """Check if a URL points to a PDF based on extension or content-type."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    path_lower = parsed.path.lower().rstrip("/")
    if path_lower.endswith(".pdf"):
        return True
    if content_type and "application/pdf" in content_type.lower():
        return True
    return False


async def extract_text_from_url(url: str) -> tuple[str, str | None]:
    """Extract text from a URL. Returns (text, page_title).

    Handles PDF URLs by downloading and parsing with PyPDF instead of
    treating them as HTML pages.
    """
    logger.info(f"  Fetching URL: {url}")
    try:
        url = _validate_url(url)

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=60.0,
            max_redirects=5,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            # Limit response size to 500MB
            if len(response.content) > 500 * 1024 * 1024:
                raise RuntimeError("URL content exceeds 500MB limit")

            content_type = response.headers.get("content-type", "")
            raw_bytes = response.content
            logger.info(f"  Fetched {len(raw_bytes)} bytes (content-type: {content_type}, status {response.status_code})")

        # Handle PDF URLs: download bytes and parse with PyPDF
        if _is_pdf_url(url, content_type):
            logger.info("  Detected PDF URL, extracting with PyPDF")
            from pypdf import PdfReader
            import io

            reader = PdfReader(io.BytesIO(raw_bytes))
            pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            logger.info(f"  Extracted text from {len(pages)} PDF pages")
            if not pages:
                raise RuntimeError("PDF contains no extractable text")
            # Use filename from URL path as a fallback title
            from urllib.parse import urlparse, unquote
            path = urlparse(url).path
            filename = unquote(path.split("/")[-1]) if path else None
            page_title = filename.rsplit(".", 1)[0] if filename else None
            return "\n\n".join(pages), page_title

        # HTML path: use trafilatura + BeautifulSoup
        from trafilatura import extract
        html = raw_bytes.decode("utf-8", errors="replace")
        logger.info(f"  Processing as HTML ({len(html)} chars)")

        # Extract page title from HTML
        page_title = None
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            page_title = title_tag.string.strip()[:200]
            logger.info(f"  Extracted page title: {page_title}")

        text = extract(html)
        if text:
            logger.info(f"  Trafilatura extracted {len(text)} chars")
            return text, page_title

        logger.info("  Trafilatura returned empty, falling back to BeautifulSoup")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        logger.info(f"  BeautifulSoup extracted {len(text)} chars")
        return text, page_title
    except Exception as e:
        raise RuntimeError(f"Failed to extract text from URL: {e}") from e


async def _update_progress(db: AsyncSession, doc: Document, step: str, pct: int, detail: str = ""):
    """Update document metadata with processing progress."""
    from sqlalchemy.orm.attributes import flag_modified
    meta = dict(doc.metadata_ or {})
    meta["progress_step"] = step
    meta["progress_pct"] = pct
    meta["progress_detail"] = detail
    meta["progress_updated_at"] = time.time()
    doc.metadata_ = meta
    flag_modified(doc, "metadata_")
    await db.commit()


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
            await _update_progress(db, doc, "extracting", 10, "Downloading and extracting text...")
            t0 = time.time()
            if doc.source_type == "url" and doc.source_url:
                raw_text, page_title = await extract_text_from_url(doc.source_url)
                # Auto-set title from page <title> if the document title is still the raw URL
                if page_title and doc.title == doc.source_url:
                    doc.title = page_title
                    logger.info(f"[{doc_id}] Auto-set title from page: {page_title}")
            elif doc.s3_key and doc.file_type:
                raw_text = await extract_text_from_file(doc.s3_key, doc.file_type)
            else:
                raise RuntimeError("No source available for extraction")
            logger.info(f"[{doc_id}] Text extraction: {len(raw_text)} chars in {time.time()-t0:.1f}s")

            if not raw_text.strip():
                raise RuntimeError("No text content could be extracted")

            # Safety cap: truncate excessively large text to prevent OOM during chunking/embedding
            MAX_TEXT_CHARS = 2_000_000  # ~2M chars ≈ ~500K tokens, plenty for any document
            if len(raw_text) > MAX_TEXT_CHARS:
                logger.warning(f"[{doc_id}] Text too large ({len(raw_text)} chars), truncating to {MAX_TEXT_CHARS}")
                raw_text = raw_text[:MAX_TEXT_CHARS]

            # Step 1b: Suggest title using Claude if still a raw URL or filename
            await _update_progress(db, doc, "analyzing", 25, "Generating title...")
            is_raw_url = doc.source_type == "url" and doc.title and doc.title.startswith("http")
            is_filename = doc.source_type == "file_upload" and doc.title and "." in doc.title
            if is_raw_url or is_filename:
                try:
                    from app.services.llm import suggest_title
                    suggested = await suggest_title(raw_text)
                    if suggested:
                        doc.title = suggested
                        logger.info(f"[{doc_id}] Claude suggested title: {suggested}")
                except Exception as e:
                    logger.warning(f"[{doc_id}] Title suggestion failed (non-fatal): {e}")

            # Step 2: Chunk
            await _update_progress(db, doc, "chunking", 35, "Splitting into chunks...")
            t0 = time.time()
            chunks = chunk_text(raw_text)
            if not chunks:
                raise RuntimeError("Text chunking produced no chunks")
            logger.info(f"[{doc_id}] Chunking: {len(chunks)} chunks in {time.time()-t0:.1f}s")

            # Step 3: Embed (prefix chunks with doc title for better retrieval)
            await _update_progress(db, doc, "embedding", 45, f"Embedding {len(chunks)} chunks...")
            t0 = time.time()
            title_prefix = doc.title or "Untitled"
            chunks_for_embedding = [f"{title_prefix}: {c}" for c in chunks]
            embeddings = await generate_embeddings(chunks_for_embedding)
            logger.info(f"[{doc_id}] Embedding: {len(embeddings)} vectors in {time.time()-t0:.1f}s")

            # Step 4: Store
            await _update_progress(db, doc, "storing", 85, f"Saving {len(chunks)} chunks...")
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

            # Clear progress metadata and record elapsed time
            from sqlalchemy.orm.attributes import flag_modified
            elapsed = time.time() - start
            meta = dict(doc.metadata_ or {})
            meta.pop("progress_step", None)
            meta.pop("progress_pct", None)
            meta.pop("progress_detail", None)
            meta.pop("progress_updated_at", None)
            meta["processing_time_secs"] = round(elapsed, 1)
            doc.metadata_ = meta
            flag_modified(doc, "metadata_")

            kb_result = await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == doc.kb_id)
            )
            kb = kb_result.scalar_one()
            kb.document_count += 1
            kb.chunk_count += len(chunk_objects)

            await db.commit()
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
