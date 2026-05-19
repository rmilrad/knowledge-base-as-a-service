from typing import Iterator, List


def iter_chunks(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> Iterator[str]:
    """Lazily yield overlapping chunks of `text`.

    Memory-friendly: only one chunk is materialized at a time, so very large
    inputs (millions of chunks) can be streamed through the ingestion
    pipeline without holding the whole list in memory.

    Guarantees forward progress: each iteration advances `start` by at least
    `chunk_size - chunk_overlap` characters, preventing pathological inputs
    from producing O(n) chunks per O(n) characters (a real bug we hit when
    a separator landed near the beginning of the search window).
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be in [0, chunk_size)")

    separators = ("\n\n", "\n", ". ", " ")
    min_advance = chunk_size - chunk_overlap  # guaranteed forward progress

    start = 0
    n = len(text)

    while start < n:
        end = start + chunk_size

        if end >= n:
            chunk = text[start:].strip()
            if chunk:
                yield chunk
            return

        # Find a clean break point in the LATTER half of the window so we
        # always make significant forward progress. If we searched the whole
        # window, a separator near `start` would produce a tiny chunk and
        # cause `start` to barely advance — exploding chunk count.
        search_from = start + (chunk_size // 2)
        split_pos = end
        for sep in separators:
            pos = text.rfind(sep, search_from, end)
            if pos >= search_from:
                split_pos = pos + len(sep)
                break

        chunk = text[start:split_pos].strip()
        if chunk:
            yield chunk

        # Always advance by at least min_advance to guarantee O(n/min_advance) chunks
        start = max(start + min_advance, split_pos - chunk_overlap)


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> List[str]:
    """Eager wrapper around `iter_chunks` for callers that want a list.

    Prefer `iter_chunks` for ingestion of large documents — it avoids
    materializing all chunks in memory at once.
    """
    return list(iter_chunks(text, chunk_size, chunk_overlap))
