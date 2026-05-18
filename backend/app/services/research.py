"""AI-powered research service for discovering relevant URLs and repositories.

Uses Claude to generate search queries, GitHub API for repo/code search,
and Claude again to curate and rank results into a structured list.
"""

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
# GitHub search helpers
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


async def _github_search_code(query: str, per_page: int = 10) -> list[dict]:
    """Search GitHub code for relevant files (READMEs, docs, etc.)."""
    logger.info(f"  GitHub code search: {query}")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://api.github.com/search/code",
            params={"q": query, "per_page": per_page},
            headers={"Accept": "application/vnd.github+json"},
        )
        if resp.status_code != 200:
            logger.warning(f"  GitHub code search failed: {resp.status_code}")
            return []
        data = resp.json()
        results = []
        seen_repos = set()
        for item in data.get("items", []):
            repo_name = item.get("repository", {}).get("full_name", "")
            if repo_name in seen_repos:
                continue
            seen_repos.add(repo_name)
            results.append({
                "url": item.get("html_url", ""),
                "title": f"{repo_name}/{item.get('name', '')}",
                "description": f"Code match in {item.get('path', '')}",
                "source": "github",
                "type": "code",
            })
        logger.info(f"  GitHub code search returned {len(results)} results")
        return results


# ---------------------------------------------------------------------------
# Web search via Claude's web_search tool
# ---------------------------------------------------------------------------

async def _web_search(query: str) -> list[dict]:
    """Use a simple web search to find relevant pages."""
    logger.info(f"  Web search: {query}")
    # Use DuckDuckGo HTML search as a free fallback
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; KBaaS/1.0)"},
            )
            if resp.status_code != 200:
                logger.warning(f"  Web search failed: {resp.status_code}")
                return []

            # Parse results from DDG HTML
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for result_div in soup.select(".result"):
                title_el = result_div.select_one(".result__title a")
                snippet_el = result_div.select_one(".result__snippet")
                if not title_el:
                    continue
                href = title_el.get("href", "")
                # DDG wraps URLs in a redirect — extract the real URL
                if "uddg=" in href:
                    from urllib.parse import unquote, urlparse, parse_qs
                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    real_url = unquote(qs.get("uddg", [href])[0])
                else:
                    real_url = href

                if not real_url.startswith("http"):
                    continue

                results.append({
                    "url": real_url,
                    "title": title_el.get_text(strip=True),
                    "description": snippet_el.get_text(strip=True) if snippet_el else "",
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
# Main research orchestration
# ---------------------------------------------------------------------------

async def research_topic(prompt: str) -> AsyncGenerator[str, None]:
    """Research a topic and stream results as SSE events.

    Yields SSE-formatted events:
    - {"type": "status", "message": "..."} — progress updates
    - {"type": "results", "results": [...]} — final curated results
    """
    client = _get_anthropic_client()

    # Step 1: Use Claude to generate search queries
    yield _sse({"type": "status", "message": "Analyzing your research request..."})

    query_response = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""Based on this research request, generate search queries to find relevant codebases, documentation, and resources.

Research request: {prompt}

Respond with a JSON object containing:
- "github_queries": list of 3-5 GitHub search queries (optimized for GitHub's search syntax, e.g. "avalanche staking" or "ava-labs subnet")
- "web_queries": list of 2-3 general web search queries for documentation and guides
- "focus": one of "codebase", "documentation", "mixed" — what the user seems most interested in

Respond with ONLY the JSON, no other text."""
        }],
    )

    try:
        raw = query_response.content[0].text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        search_plan = json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        logger.error(f"Failed to parse search plan: {query_response.content[0].text}")
        yield _sse({"type": "error", "message": "Failed to generate search queries. Please try again."})
        yield "data: [DONE]\n\n"
        return

    github_queries = search_plan.get("github_queries", [])
    web_queries = search_plan.get("web_queries", [])
    focus = search_plan.get("focus", "mixed")

    logger.info(f"Research plan: {len(github_queries)} GitHub queries, {len(web_queries)} web queries, focus={focus}")
    yield _sse({"type": "status", "message": f"Searching GitHub and web ({len(github_queries) + len(web_queries)} queries)..."})

    # Step 2: Run all searches in parallel
    import asyncio
    all_results = []

    # GitHub repo searches
    repo_tasks = [_github_search_repos(q) for q in github_queries[:5]]
    # GitHub code searches (for finding specific integration files)
    code_queries = [f"{q} filename:README" for q in github_queries[:3]]
    code_tasks = [_github_search_code(q) for q in code_queries]
    # Web searches
    web_tasks = [_web_search(q) for q in web_queries[:3]]

    search_results = await asyncio.gather(
        *repo_tasks, *code_tasks, *web_tasks,
        return_exceptions=True,
    )

    for result in search_results:
        if isinstance(result, list):
            all_results.extend(result)
        elif isinstance(result, Exception):
            logger.warning(f"Search task failed: {result}")

    # Deduplicate by URL
    seen_urls = set()
    unique_results = []
    for r in all_results:
        url_normalized = r["url"].rstrip("/").lower()
        if url_normalized not in seen_urls:
            seen_urls.add(url_normalized)
            unique_results.append(r)

    logger.info(f"Total unique results: {len(unique_results)}")

    if not unique_results:
        yield _sse({"type": "results", "results": []})
        yield "data: [DONE]\n\n"
        return

    yield _sse({"type": "status", "message": f"Found {len(unique_results)} results. Analyzing relevance..."})

    # Step 3: Use Claude to curate and rank results
    results_text = json.dumps(unique_results[:50], indent=2)  # Cap at 50 for Claude context

    curation_response = await client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""You are curating search results for a knowledge base. The user wants to build a knowledge base about:

"{prompt}"

Here are the raw search results:
{results_text}

Your task:
1. Filter out irrelevant results
2. Rank by relevance and quality (most relevant first)
3. For GitHub repos, include the README URL (add /blob/main/README.md or /blob/master/README.md to the repo URL)
4. Also suggest the documentation URL if the repo has docs/ or a docs site
5. Add a concise 1-sentence reason why each result is relevant
6. Select the best 15-25 results

Respond with ONLY a JSON array of objects, each with:
- "url": the URL to ingest (prefer README or docs pages over repo root)
- "title": short descriptive title
- "description": 1-sentence explanation of relevance
- "source": "github" or "web"
- "type": "repository" | "documentation" | "code" | "guide" | "article"
- "relevance": "high" | "medium" — how relevant this is

Respond with ONLY the JSON array, no other text."""
        }],
    )

    try:
        raw = curation_response.content[0].text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        curated = json.loads(raw)
    except (json.JSONDecodeError, IndexError):
        logger.error(f"Failed to parse curation response")
        # Fall back to raw results
        curated = [
            {
                "url": r["url"],
                "title": r["title"],
                "description": r["description"],
                "source": r["source"],
                "type": r.get("type", "webpage"),
                "relevance": "medium",
            }
            for r in unique_results[:20]
        ]

    # Add selected=True to all results (user can deselect)
    for item in curated:
        item["selected"] = item.get("relevance") == "high"

    logger.info(f"Curated {len(curated)} results")
    yield _sse({"type": "results", "results": curated})
    yield "data: [DONE]\n\n"


def _sse(data: dict) -> str:
    """Format a dict as an SSE event."""
    return f"data: {json.dumps(data)}\n\n"
