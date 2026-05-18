"""Deep dive service: searches the web for additional info beyond the KB.

Uses Claude's web_search tool for reliable search from any environment,
GitHub API for repo search, and Claude Sonnet for answer synthesis.
"""

import asyncio
import json
import logging
import re
from typing import AsyncGenerator

import anthropic
import httpx

from app.config import settings

logger = logging.getLogger("kbaas.research")

_async_client = None


def _get_anthropic_client():
    global _async_client
    if _async_client is None:
        _async_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _async_client


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------

async def _github_search_repos(query: str, per_page: int = 15) -> list[dict]:
    """Search GitHub repositories."""
    logger.info(f"  GitHub repo search: {query}")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": per_page},
            headers={"Accept": "application/vnd.github+json"},
        )
        if resp.status_code != 200:
            logger.warning(f"  GitHub repo search failed: {resp.status_code}")
            return []
        data = resp.json()
        results = []
        for repo in data.get("items", []):
            results.append({
                "url": repo["html_url"],
                "title": repo["full_name"],
                "description": (repo.get("description") or "")[:300],
                "stars": repo.get("stargazers_count", 0),
                "language": repo.get("language"),
                "source": "github",
                "type": "repository",
            })
        logger.info(f"  GitHub repo search returned {len(results)} results")
        return results


async def _web_search(query: str) -> list[dict]:
    """Use Claude's web_search tool to find relevant pages.

    This uses the Anthropic API's built-in web search capability which is
    reliable from any environment (unlike DuckDuckGo HTML scraping which
    returns 202 from AWS IPs).
    """
    logger.info(f"  Web search (Claude): {query}")
    try:
        client = _get_anthropic_client()
        response = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=256,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 1,
            }],
            messages=[{
                "role": "user",
                "content": f"Search for: {query}",
            }],
        )

        results = []
        for block in response.content:
            if block.type == "web_search_tool_result":
                for item in block.content:
                    if hasattr(item, "url") and item.url:
                        results.append({
                            "url": item.url,
                            "title": getattr(item, "title", "") or "",
                            "description": "",
                            "source": "web",
                            "type": "webpage",
                        })
                        if len(results) >= 10:
                            break

        logger.info(f"  Web search returned {len(results)} results")
        return results
    except Exception as e:
        logger.warning(f"  Web search failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Deep dive
# ---------------------------------------------------------------------------

async def deep_dive(question: str, current_answer: str) -> AsyncGenerator[str, None]:
    """Search the web for deeper information about a chat question.

    Yields SSE events:
    - {"type": "status", "message": "..."} — progress
    - {"type": "token", "content": "..."} — streamed enriched answer
    - {"type": "sources_found", "sources": [...]} — URLs found, user can add to KB
    """
    client = _get_anthropic_client()

    yield _sse({"type": "status", "message": "Searching the web..."})

    # Step 1: Generate search queries
    query_response = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": f"""Generate search queries to find deeper technical information about this question.

Question: {question}

Current answer from the knowledge base (may be incomplete):
{current_answer[:500]}

Generate 3-4 targeted search queries that would find more detailed information, code examples, and documentation. Focus on filling gaps in the current answer.

IMPORTANT: Do NOT use "site:" prefixes in queries. Use plain natural language queries.

Respond with ONLY a JSON object:
{{"queries": ["query1", "query2", ...], "project_org": "the primary GitHub org or company name if identifiable, else null"}}"""
        }],
    )

    try:
        raw = query_response.content[0].text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        parsed = json.loads(raw)
        queries = parsed.get("queries", parsed) if isinstance(parsed, dict) else parsed
        project_org = parsed.get("project_org") if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, IndexError):
        queries = [question]
        project_org = None

    queries = [re.sub(r'site:\S+\s*', '', q).strip() for q in queries]
    queries = [q for q in queries if q]

    logger.info(f"Deep dive queries: {queries}, org: {project_org}")

    # Step 2: Search web + GitHub in parallel
    web_tasks = [_web_search(q) for q in queries[:4]]
    github_queries = queries[:2]
    github_tasks = [_github_search_repos(q, per_page=5) for q in github_queries]

    all_search_results = await asyncio.gather(*web_tasks, *github_tasks, return_exceptions=True)

    all_results = []
    for result in all_search_results:
        if isinstance(result, list):
            all_results.extend(result)

    # Deduplicate
    seen = set()
    unique = []
    for r in all_results:
        url_norm = r["url"].rstrip("/").lower()
        if url_norm not in seen:
            seen.add(url_norm)
            unique.append(r)

    if not unique:
        yield _sse({"type": "token", "content": "I couldn't find additional information online. The knowledge base answer may already be the best available."})
        yield _sse({"type": "sources_found", "sources": []})
        yield "data: [DONE]\n\n"
        return

    yield _sse({"type": "status", "message": f"Found {len(unique)} sources. Fetching content..."})

    # Step 3: Fetch content from top results
    async def _fetch_page_text(url: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as c:
                resp = await c.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; KBaaS/1.0)"})
                if resp.status_code != 200 or len(resp.content) > 5 * 1024 * 1024:
                    return None
                from trafilatura import extract
                text = extract(resp.text)
                return text[:3000] if text else None
        except Exception:
            return None

    fetch_tasks = [_fetch_page_text(r["url"]) for r in unique[:5]]
    fetched = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    web_context_parts = []
    for i, content in enumerate(fetched):
        if isinstance(content, str) and content:
            web_context_parts.append(f"[Source: {unique[i]['title']}]\nURL: {unique[i]['url']}\n{content}")

    web_context = "\n\n---\n\n".join(web_context_parts) if web_context_parts else "No additional content could be extracted."

    yield _sse({"type": "status", "message": "Generating enriched answer..."})

    # Step 4: Stream enriched answer
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            system="""You are providing a deeper, more comprehensive answer using additional sources found on the web.

Rules:
- The user already received an initial answer from their knowledge base. Now provide additional depth from the web sources below.
- Cite your sources inline using markdown links: [source title](url)
- Focus on NEW information not already in the initial answer
- If you find contradictions with the initial answer, note them
- Be thorough — this is a "deep dive" """,
            messages=[{
                "role": "user",
                "content": f"""Original question: {question}

Initial answer from knowledge base:
{current_answer[:1000]}

Additional web sources:
{web_context}

Provide a deeper answer using these additional sources. Focus on what's new or more detailed compared to the initial answer."""
            }],
        ) as stream:
            async for text in stream.text_stream:
                yield _sse({"type": "token", "content": text})
    except Exception as e:
        logger.exception(f"Deep dive streaming error: {e}")
        yield _sse({"type": "token", "content": "An error occurred while generating the deep dive. Please try again."})

    # Step 5: Return sources for KB addition
    sources_for_kb = [
        {
            "url": r["url"],
            "title": r["title"],
            "description": r.get("description", ""),
            "source": r.get("source", "web"),
        }
        for r in unique[:15]
    ]
    yield _sse({"type": "sources_found", "sources": sources_for_kb})
    yield "data: [DONE]\n\n"


def _sse(data: dict) -> str:
    """Format a dict as an SSE event."""
    return f"data: {json.dumps(data)}\n\n"
