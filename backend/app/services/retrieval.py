from typing import Dict, List
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedding import generate_single_embedding


async def retrieve_chunks(
    db: AsyncSession,
    kb_id: UUID,
    question: str,
    top_k: int = 5,
) -> List[Dict]:
    query_embedding = await generate_single_embedding(question)

    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    sql = text("""
        SELECT
            c.content,
            c.metadata,
            d.title as doc_title,
            1 - (c.embedding <=> cast(:embedding as vector)) as similarity
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.kb_id = :kb_id
        ORDER BY c.embedding <=> cast(:embedding as vector)
        LIMIT :top_k
    """)

    result = await db.execute(
        sql,
        {
            "kb_id": str(kb_id),
            "embedding": embedding_str,
            "top_k": top_k,
        },
    )
    rows = result.fetchall()

    return [
        {
            "content": row.content,
            "title": row.doc_title or "Untitled",
            "score": float(row.similarity),
        }
        for row in rows
    ]
