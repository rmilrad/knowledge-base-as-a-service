import json
import logging
from typing import AsyncGenerator, Dict, List

import anthropic

logger = logging.getLogger("kbaas.llm")

from app.config import settings

_async_client = None

ALLOWED_MODELS = {
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
    "claude-opus-4-7",
}

RESPONSE_STYLES = {
    "concise": {
        "max_tokens": 300,
        "instruction": "Be very brief and concise. Answer in a few sentences at most.",
    },
    "balanced": {
        "max_tokens": 1024,
        "instruction": "Be clear and direct. Use moderate detail.",
    },
    "comprehensive": {
        "max_tokens": 4096,
        "instruction": "Be thorough and detailed. Cover all relevant aspects, provide examples where helpful, and explain nuances.",
    },
}


def _get_async_client():
    global _async_client
    if _async_client is None:
        _async_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _async_client


def _build_context(chunks: List[Dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[Source {i}: {chunk['title']}]\n{chunk['content']}")
    return "\n\n---\n\n".join(parts)


def _build_system_prompt(response_style: str = "balanced", engineer_mode: bool = False) -> str:
    style = RESPONSE_STYLES.get(response_style, RESPONSE_STYLES["balanced"])

    if engineer_mode:
        return f"""You are a senior software engineer assistant that answers technical questions based on the provided knowledge base context.

Rules:
- Answer ONLY based on the provided context. If the context doesn't contain enough information, say so clearly.
- EVERY claim or explanation MUST be backed by actual code from the context. Include relevant code snippets using markdown code blocks with the appropriate language tag.
- When explaining how something works, show the actual implementation code — API calls, function signatures, data structures, configuration, etc.
- Structure your response as: explanation → supporting code → explanation → supporting code. Never explain without code evidence.
- If the context contains API endpoints, show the exact endpoint, method, and request/response format.
- If the context contains smart contract or on-chain interactions, show the exact function calls and parameters.
- Use inline citations by linking to the source title like this: [source title](url). Place citations naturally within or at the end of each claim.
- Do NOT include a separate sources list at the end.
- If the context doesn't contain actual code to support an answer, explicitly state: "No code found in the knowledge base for this."
- {style['instruction']}"""

    return f"""You are a helpful assistant that answers questions based on the provided knowledge base context.

Rules:
- Answer ONLY based on the provided context. If the context doesn't contain enough information, say so clearly.
- Use inline citations by linking to the source title like this: [source title](url). Place citations naturally within or at the end of each claim.
- Do NOT include a separate sources list at the end.
- If multiple sources contain relevant information, synthesize them.
- {style['instruction']}"""


async def generate_answer(
    question: str,
    chunks: List[Dict],
    model: str = "claude-sonnet-4-5",
    response_style: str = "balanced",
    engineer_mode: bool = False,
) -> str:
    if not chunks:
        return "No relevant information found in the knowledge base."

    if model not in ALLOWED_MODELS:
        model = "claude-sonnet-4-5"

    style = RESPONSE_STYLES.get(response_style, RESPONSE_STYLES["balanced"])
    client = _get_async_client()
    context = _build_context(chunks)

    message = await client.messages.create(
        model=model,
        max_tokens=style["max_tokens"],
        system=_build_system_prompt(response_style, engineer_mode),
        messages=[
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {question}",
            }
        ],
    )
    return message.content[0].text


async def stream_answer(
    question: str,
    chunks: List[Dict],
    model: str = "claude-sonnet-4-5",
    response_style: str = "balanced",
    engineer_mode: bool = False,
) -> AsyncGenerator[str, None]:
    if not chunks:
        yield f"data: {json.dumps({'type': 'token', 'content': 'No relevant information found in the knowledge base.'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    if model not in ALLOWED_MODELS:
        model = "claude-sonnet-4-5"

    style = RESPONSE_STYLES.get(response_style, RESPONSE_STYLES["balanced"])
    client = _get_async_client()
    context = _build_context(chunks)

    # In engineer mode, retrieve more chunks for richer code context
    sources_data = [
        {"title": c["title"], "content": c["content"][:200]} for c in chunks
    ]
    yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data})}\n\n"

    try:
        async with client.messages.stream(
            model=model,
            max_tokens=style["max_tokens"],
            system=_build_system_prompt(response_style, engineer_mode),
            messages=[
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {question}",
                }
            ],
        ) as stream:
            async for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"
    except Exception as e:
        logger.exception(f"LLM streaming error: {e}")
        yield f"data: {json.dumps({'type': 'token', 'content': 'An error occurred while generating the response. Please try again.'})}\n\n"

    yield "data: [DONE]\n\n"


async def suggest_title(text: str) -> str | None:
    """Use Claude Haiku to suggest a concise title from document content."""
    try:
        client = _get_async_client()
        # Use first ~2000 chars to keep it cheap and fast
        snippet = text[:2000]
        message = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=60,
            messages=[{
                "role": "user",
                "content": f"Based on this document content, suggest a short, descriptive title (under 80 characters). Reply with ONLY the title, nothing else.\n\n{snippet}",
            }],
        )
        title = message.content[0].text.strip().strip('"\'')
        logger.info(f"  Claude suggested title: {title}")
        return title[:200] if title else None
    except Exception as e:
        logger.warning(f"  Title suggestion failed: {e}")
        return None
