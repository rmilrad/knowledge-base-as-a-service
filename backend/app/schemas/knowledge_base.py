from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class KBCreate(BaseModel):
    name: str
    description: Optional[str] = None


class KBUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class KBResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    status: str
    document_count: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
