from typing import List, Optional

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    model: str = "claude-sonnet-4-5"
    response_style: str = "balanced"  # concise, balanced, comprehensive


class SourceChunk(BaseModel):
    title: Optional[str]
    content: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceChunk]
