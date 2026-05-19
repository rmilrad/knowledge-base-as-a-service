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
from app.services.chunking import iter_chunks
from app.services.embedding import generate_embeddings
from app.services.storage import download_from_s3

# Streaming ingestion: chunk + embed + insert in batches of this size, then
# release memory before the next batch. Tuned for the BAAI/bge-small-en-v1.5
# model (~50MB) running on a 2-4 GB container — keeps per-batch peak memory
# bounded regardless of total document size, so we can ingest documents that
# produce 100K+ chunks without OOM.
EMBED_BATCH_SIZE = 256

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


async def _fetch_with_safe_redirects(url: str, max_redirects: int = 5):
    """Fetch a URL, manually following redirects and SSRF-validating each hop.

    Prevents the bypass where a public hostname redirects (302) to an internal
    IP (e.g. 169.254.169.254 / 127.0.0.1 / 10.x.x.x). Stock `follow_redirects`
    would re-fetch the target without re-validating it."""
    current_url = _validate_url(url)
    async with httpx.AsyncClient(follow_redirects=False, timeout=60.0) as client:
        for _ in range(max_redirects + 1):
            response = await client.get(current_url)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    response.raise_for_status()
                    return response
                # Resolve relative redirects against the current URL
                from urllib.parse import urljoin
                next_url = urljoin(current_url, location)
                current_url = _validate_url(next_url)
                continue
            response.raise_for_status()
            return response
        raise RuntimeError(f"Exceeded max redirects ({max_redirects}) for URL: {url}")


async def extract_text_from_url(url: str) -> tuple[str, str | None]:
    """Extract text from a URL. Returns (text, page_title).

    Handles PDF URLs by downloading and parsing with PyPDF instead of
    treating them as HTML pages.
    """
    logger.info(f"  Fetching URL: {url}")
    try:
        response = await _fetch_with_safe_redirects(url)
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
                raw_text, _ = await extract_text_from_url(doc.source_url)
            elif doc.s3_key and doc.file_type:
                raw_text = await extract_text_from_file(doc.s3_key, doc.file_type)
            else:
                raise RuntimeError("No source available for extraction")
            logger.info(f"[{doc_id}] Text extraction: {len(raw_text)} chars in {time.time()-t0:.1f}s")

            if not raw_text.strip():
                raise RuntimeError("No text content could be extracted")

            # Streaming pipeline: chunk → embed → insert in batches of
            # EMBED_BATCH_SIZE so peak memory stays bounded regardless of
            # total document size. Supports documents producing millions of
            # chunks without OOM.

            title_prefix = doc.title or "Untitled"
            kb_id = doc.kb_id
            doc_pk = doc.id
            text_len = len(raw_text)

            await _update_progress(db, doc, "chunking", 20, "Splitting and embedding...")

            chunker = iter_chunks(raw_text)
            total_chunks = 0
            t_embed_total = 0.0
            t_store_total = 0.0
            batch_chunk_texts: list[str] = []
            # Track approximate position through the text for progress %
            approx_pos = 0

            async def _flush_batch():
                nonlocal total_chunks, t_embed_total, t_store_total
                if not batch_chunk_texts:
                    return
                # Embed this batch
                t0 = time.time()
                prefixed = [f"{title_prefix}: {c}" for c in batch_chunk_texts]
                embeddings = await generate_embeddings(prefixed)
                t_embed_total += time.time() - t0

                # Insert this batch
                t0 = time.time()
                chunk_objects = [
                    Chunk(
                        document_id=doc_pk,
                        kb_id=kb_id,
                        content=c,
                        chunk_index=total_chunks + i,
                        token_count=len(c.split()),
                        embedding=emb,
                        metadata_={"source_title": title_prefix},
                    )
                    for i, (c, emb) in enumerate(zip(batch_chunk_texts, embeddings))
                ]
                db.add_all(chunk_objects)
                await db.flush()
                t_store_total += time.time() - t0
                total_chunks += len(chunk_objects)
                # Release memory before next batch
                batch_chunk_texts.clear()

            extract_elapsed = time.time() - start
            logger.info(
                f"[{doc_id}] Text extracted: {text_len} chars in {extract_elapsed:.1f}s; "
                f"streaming chunks in batches of {EMBED_BATCH_SIZE}"
            )

            t_pipeline_start = time.time()
            last_progress_update = 0.0
            for chunk in chunker:
                batch_chunk_texts.append(chunk)
                approx_pos += len(chunk)
                if len(batch_chunk_texts) >= EMBED_BATCH_SIZE:
                    await _flush_batch()
                    # Throttle progress updates to once every 2 seconds
                    now = time.time()
                    if now - last_progress_update > 2.0:
                        pct = 20 + min(70, int(70 * approx_pos / max(text_len, 1)))
                        await _update_progress(
                            db, doc, "embedding", pct,
                            f"Embedded {total_chunks} chunks...",
                        )
                        last_progress_update = now
            # Flush remaining
            await _flush_batch()

            if total_chunks == 0:
                raise RuntimeError("Text chunking produced no chunks")

            logger.info(
                f"[{doc_id}] Streamed {total_chunks} chunks in "
                f"{time.time()-t_pipeline_start:.1f}s "
                f"(embed: {t_embed_total:.1f}s, store: {t_store_total:.1f}s)"
            )

            # Step 4: Finalize document + KB counters
            await _update_progress(db, doc, "storing", 95, f"Finalizing {total_chunks} chunks...")
            doc.status = "completed"
            doc.chunk_count = total_chunks

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
                select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
            )
            kb = kb_result.scalar_one()
            kb.document_count += 1
            kb.chunk_count += total_chunks

            await db.commit()
            logger.info(f"[{doc_id}] Ingestion complete: {total_chunks} chunks stored in {elapsed:.1f}s")

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
