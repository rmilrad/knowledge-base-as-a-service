import os
import sys
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

BACKEND_URL = os.environ.get("KBAAS_BACKEND_URL", "http://localhost:8000")

mcp = FastMCP("KBaaS", instructions="Query and search knowledge bases managed by KBaaS.")

_api_key: Optional[str] = None


def _get_api_key() -> str:
    global _api_key
    if _api_key:
        return _api_key
    key = os.environ.get("KBAAS_API_KEY", "")
    if not key:
        raise ValueError("KBAAS_API_KEY environment variable is required")
    _api_key = key
    return key


def _headers():
    return {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }


@mcp.tool()
async def list_knowledge_bases() -> str:
    """List all knowledge bases available to your account."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{BACKEND_URL}/api/kb", headers=_headers())
        response.raise_for_status()
        kbs = response.json()
        if not kbs:
            return "No knowledge bases found."
        lines = []
        for kb in kbs:
            lines.append(
                f"- {kb['name']} (ID: {kb['id']}) — "
                f"{kb['document_count']} docs, {kb['chunk_count']} chunks, "
                f"status: {kb['status']}"
            )
        return "\n".join(lines)


@mcp.tool()
async def query_knowledge_base(kb_id: str, question: str) -> str:
    """Query a knowledge base with a natural language question. Returns an AI-generated answer with source citations.

    Args:
        kb_id: The UUID of the knowledge base to query.
        question: The natural language question to ask.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{BACKEND_URL}/api/kb/{kb_id}/query",
            headers=_headers(),
            json={"question": question},
        )
        response.raise_for_status()
        data = response.json()

        result = f"**Answer:**\n{data['answer']}\n\n**Sources:**\n"
        for src in data.get("sources", []):
            result += f"- {src['title']} (relevance: {src['score']:.2f})\n"
        return result


@mcp.tool()
async def search_documents(kb_id: str, query: str, top_k: int = 5) -> str:
    """Search for relevant document chunks without generating an AI answer. Returns raw text passages with source metadata.

    Args:
        kb_id: The UUID of the knowledge base to search.
        query: The search query.
        top_k: Number of results to return (default: 5).
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BACKEND_URL}/api/kb/{kb_id}/query",
            headers=_headers(),
            json={"question": query, "top_k": top_k},
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for i, src in enumerate(data.get("sources", []), 1):
            results.append(
                f"**Result {i}** ({src['title']}, score: {src['score']:.2f}):\n"
                f"{src['content']}\n"
            )
        return "\n---\n".join(results) if results else "No results found."


@mcp.tool()
async def add_urls(kb_id: str, urls: list[str]) -> str:
    """Add one or more URLs to a knowledge base for ingestion. The URLs will be fetched, their text extracted, chunked, embedded, and stored in the knowledge base for RAG retrieval.

    Use this after researching a topic to populate a knowledge base with relevant sources. Present the list of URLs to the user for approval before calling this tool.

    Args:
        kb_id: The UUID of the knowledge base to add URLs to.
        urls: A list of URLs to ingest.
    """
    if not urls:
        return "No URLs provided."

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{BACKEND_URL}/api/kb/{kb_id}/documents/urls",
            headers=_headers(),
            json={"urls": urls},
        )
        response.raise_for_status()
        docs = response.json()

    return f"Added {len(docs)} URL(s) for ingestion. They will be processed in the background.\n" + "\n".join(
        f"- {doc['title']} (status: {doc['status']})" for doc in docs
    )


if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport == "http":
        mcp.run(transport="streamable-http", host="0.0.0.0", port=3001)
    else:
        mcp.run(transport="stdio")
