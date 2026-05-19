"""
Embedded MCP server — exposed via FastAPI routes at /api/mcp/{kb_id}.

Each knowledge base gets its own MCP endpoint URL. The KB ID is extracted
from the URL path so tools don't need it as a parameter.

Auth is optional:
  - If an API key (Bearer kb_...) or JWT is provided, it's forwarded to the
    backend API for authentication.
  - If no auth is provided, tools return a clear error asking for credentials.
  - The MCP connection itself always succeeds (no auth to connect).
"""

import contextvars
import os

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# The backend URL for internal API calls — loopback in production
BACKEND_URL = os.environ.get("KBAAS_BACKEND_URL", "http://localhost:8000")

mcp = FastMCP(
    "KBaaS",
    instructions=(
        "Query and search a knowledge base managed by KBaaS. "
        "This MCP server is connected to a specific knowledge base. "
        "Use the available tools to search documents and ask questions."
    ),
    streamable_http_path="/",
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)

# Context vars for the current request's KB ID and auth header.
_current_kb_id: contextvars.ContextVar[str] = contextvars.ContextVar("_current_kb_id", default="")
_current_auth: contextvars.ContextVar[str] = contextvars.ContextVar("_current_auth", default="")


def _headers() -> dict[str, str]:
    """Build headers for internal backend API calls."""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    auth = _current_auth.get()
    if auth:
        headers["Authorization"] = auth
    return headers


def _kb_id() -> str:
    """Get the current KB ID from the URL context."""
    kb = _current_kb_id.get()
    if not kb:
        raise ValueError("No knowledge base ID in request context")
    return kb


@mcp.tool()
async def query(question: str) -> str:
    """Ask a question about the knowledge base. Returns an AI-generated answer with source citations.

    Args:
        question: The natural language question to ask.
    """
    kb = _kb_id()
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                f"{BACKEND_URL}/api/kb/{kb}/query",
                headers=_headers(),
                json={"question": question},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return "Authentication required. Provide an API key in the Authorization header."
            if e.response.status_code == 404:
                return "Knowledge base not found. Check the KB ID in your MCP connection URL."
            return f"Error: {e.response.status_code} — {e.response.text}"

        data = response.json()
        result = f"**Answer:**\n{data['answer']}\n\n**Sources:**\n"
        for src in data.get("sources", []):
            result += f"- {src['title']} (relevance: {src['score']:.2f})\n"
        return result


@mcp.tool()
async def search(query: str, top_k: int = 5) -> str:
    """Search for relevant document chunks without generating an AI answer.

    Args:
        query: The search query.
        top_k: Number of results to return (default: 5).
    """
    kb = _kb_id()
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{BACKEND_URL}/api/kb/{kb}/query",
                headers=_headers(),
                json={"question": query, "top_k": top_k},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return "Authentication required. Provide an API key in the Authorization header."
            if e.response.status_code == 404:
                return "Knowledge base not found. Check the KB ID in your MCP connection URL."
            return f"Error: {e.response.status_code} — {e.response.text}"

        data = response.json()
        results = []
        for i, src in enumerate(data.get("sources", []), 1):
            results.append(
                f"**Result {i}** ({src['title']}, score: {src['score']:.2f}):\n"
                f"{src['content']}\n"
            )
        return "\n---\n".join(results) if results else "No results found."


@mcp.tool()
async def add_urls(urls: list[str]) -> str:
    """Add URLs to this knowledge base for ingestion.

    Args:
        urls: A list of URLs to ingest.
    """
    if not urls:
        return "No URLs provided."

    kb = _kb_id()
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                f"{BACKEND_URL}/api/kb/{kb}/documents/urls",
                headers=_headers(),
                json={"urls": urls},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return "Authentication required. Provide an API key in the Authorization header."
            if e.response.status_code == 404:
                return "Knowledge base not found. Check the KB ID in your MCP connection URL."
            return f"Error: {e.response.status_code} — {e.response.text}"

        docs = response.json()
        return (
            f"Added {len(docs)} URL(s) for ingestion.\n"
            + "\n".join(f"- {doc['title']} (status: {doc['status']})" for doc in docs)
        )


@mcp.tool()
async def info() -> str:
    """Get information about this knowledge base — name, document count, chunk count."""
    kb = _kb_id()
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(
                f"{BACKEND_URL}/api/kb/{kb}",
                headers=_headers(),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return "Authentication required. Provide an API key in the Authorization header."
            if e.response.status_code == 404:
                return "Knowledge base not found. Check the KB ID in your MCP connection URL."
            return f"Error: {e.response.status_code} — {e.response.text}"

        data = response.json()
        return (
            f"**{data['name']}**\n"
            f"- Documents: {data['document_count']}\n"
            f"- Chunks: {data['chunk_count']}\n"
            f"- Status: {data['status']}\n"
            f"- Description: {data.get('description') or 'None'}"
        )
