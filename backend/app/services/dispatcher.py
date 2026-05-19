"""Concurrent dispatcher for document ingestion.

Replaces FastAPI's `BackgroundTasks`, which executes its queued callables
SEQUENTIALLY in the request's event loop after the response is sent. That
means bulk ingestion of N URLs would take N × per-doc-time instead of
running them concurrently — a 10-URL "deep dive" went from ~15-20 min
expected to ~2 hours.

This module fires each ingestion as its own `asyncio.create_task`, so:
  - All in-flight ingestions interleave on the event loop and parallelize
    across I/O waits (HTTP fetches, DB inserts) and across CPU-bound calls
    that release the GIL (fastembed inference via ONNX Runtime).
  - A concurrency semaphore caps how many run at once. CPU is the limiting
    resource on a small container; >N parallel runs only thrash. The cap
    also bounds memory (each ingestion holds the source text + per-batch
    buffers in RAM).
  - We hold strong references to created tasks so asyncio doesn't GC them
    mid-flight — a documented foot-gun with create_task fire-and-forget.
"""

import asyncio
import logging
import os
from typing import Awaitable, Callable, Set

logger = logging.getLogger("kbaas.dispatcher")

# Cap simultaneous ingestions. Tune based on container CPU/memory.
# fastembed inference is the bottleneck (CPU-bound, single-core). >~4 in
# flight starts thrashing and starves health checks even with off-thread.
# With 2 vCPU and fastembed releasing the GIL via ONNX Runtime, 2 concurrent
# CPU-bound ingestions roughly saturate the cores. >2 just adds context-
# switching overhead and starves health checks. Concurrency above the vCPU
# count is counter-productive: observed 4-way concurrent ingestion on 1
# vCPU ran at ~2.7 chunks/sec aggregate versus 5.3/sec single-doc.
INGEST_CONCURRENCY = int(os.environ.get("KBAAS_INGEST_CONCURRENCY", "2"))

_semaphore: asyncio.Semaphore | None = None
_pending: Set[asyncio.Task] = set()


def _get_semaphore() -> asyncio.Semaphore:
    """Lazily create the semaphore so it's bound to the running event loop."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(INGEST_CONCURRENCY)
    return _semaphore


async def _run_with_limit(coro_fn: Callable[[], Awaitable[None]], label: str) -> None:
    """Run a coroutine with the global ingestion semaphore, logging errors."""
    sem = _get_semaphore()
    async with sem:
        try:
            await coro_fn()
        except Exception:
            # Swallow — ingest_document already records status=error on the
            # document. Logging here protects against bugs that crash the
            # coroutine before that DB update runs.
            logger.exception(f"[{label}] dispatcher coroutine crashed")


def schedule(coro_fn: Callable[[], Awaitable[None]], label: str = "task") -> None:
    """Schedule `coro_fn()` to run concurrently in the background.

    Holds a strong reference to the task in a module-level set so asyncio
    cannot GC it before completion. The task removes itself on done.
    """
    task = asyncio.create_task(_run_with_limit(coro_fn, label), name=label)
    _pending.add(task)
    task.add_done_callback(_pending.discard)


def schedule_ingestion(doc_id: str) -> None:
    """Convenience: schedule app.services.ingestion.ingest_document(doc_id)."""
    # Imported lazily to avoid circular import (dispatcher loaded at startup).
    from app.services.ingestion import ingest_document
    schedule(lambda: ingest_document(doc_id), label=f"ingest:{doc_id}")
