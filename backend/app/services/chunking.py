from typing import List


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> List[str]:
    separators = ["\n\n", "\n", ". ", " "]

    chunks: List[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunk = text[start:].strip()
            if chunk:
                chunks.append(chunk)
            break

        split_pos = end
        for sep in separators:
            pos = text.rfind(sep, start, end)
            if pos > start:
                split_pos = pos + len(sep)
                break

        chunk = text[start:split_pos].strip()
        if chunk:
            chunks.append(chunk)

        start = max(start + 1, split_pos - chunk_overlap)

    return chunks
