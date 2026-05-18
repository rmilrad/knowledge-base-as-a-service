from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


class DocumentResponse(BaseModel):
    id: UUID
    title: Optional[str]
    source_type: str
    source_url: Optional[str] = None
    file_type: Optional[str]
    file_size_bytes: Optional[int]
    status: str
    error_message: Optional[str]
    chunk_count: int
    created_at: datetime
    metadata_: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class DocumentUpdate(BaseModel):
    title: str


class UrlIngest(BaseModel):
    url: str


class BulkUrlIngest(BaseModel):
    urls: list[str]


class ResearchRequest(BaseModel):
    prompt: str
