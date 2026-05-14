from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: UUID
    title: Optional[str]
    source_type: str
    file_type: Optional[str]
    file_size_bytes: Optional[int]
    status: str
    error_message: Optional[str]
    chunk_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UrlIngest(BaseModel):
    url: str


class BulkUrlIngest(BaseModel):
    urls: list[str]
