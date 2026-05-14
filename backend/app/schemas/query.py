from typing import List, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=10000)
    top_k: int = Field(default=5, ge=1, le=50)
    model: str = "claude-sonnet-4-5"
    response_style: str = "balanced"  # concise, balanced, comprehensive


class SourceChunk(BaseModel):
    title: Optional[str]
    content: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceChunk]
