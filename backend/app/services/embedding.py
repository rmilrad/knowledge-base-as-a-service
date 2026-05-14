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


async def generate_embeddings(texts: List[str]) -> List[List[float]]:
    model = _get_model()
    embeddings = list(model.embed(texts))
    return [e.tolist() for e in embeddings]


async def generate_single_embedding(text: str) -> List[float]:
    result = await generate_embeddings([text])
    return result[0]
