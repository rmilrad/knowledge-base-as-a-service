import asyncio
import logging
from typing import List

from fastembed import TextEmbedding

logger = logging.getLogger("kbaas.embedding")

_model = None

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = 384


def _get_model() -> TextEmbedding:
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _model = TextEmbedding(model_name=EMBEDDING_MODEL)
        logger.info("Embedding model loaded")
    return _model


def _embed_sync(texts: List[str]) -> List[List[float]]:
    """Synchronous embed. Called from a thread pool — must not be invoked
    from the event loop directly because fastembed performs CPU-bound work
    (numpy/Rust) that would block the loop for multiple seconds and stall
    health checks. With 4000 chunks × ~3 s/batch this previously caused
    ECS to kill the task on ALB health-check timeouts."""
    model = _get_model()
    return [e.tolist() for e in model.embed(texts)]


async def generate_embeddings(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    # Off-load CPU-bound work to a thread so the asyncio event loop stays
    # responsive (health checks, other requests, monitor pings).
    return await asyncio.to_thread(_embed_sync, texts)


async def generate_single_embedding(text: str) -> List[float]:
    result = await generate_embeddings([text])
    return result[0]
