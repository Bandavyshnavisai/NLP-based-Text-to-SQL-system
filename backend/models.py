from pydantic import BaseModel
from typing import Any, Optional

class QueryRequest(BaseModel):
    question: str
    database: str

class QueryResponse(BaseModel):
    success: bool
    question: str
    database: str
    sql: Optional[str] = None
    validation: dict[str, Any] = {}
    execution: dict[str, Any] = {}
    error: Optional[str] = None

class DatabaseInfo(BaseModel):
    id: str
    name: str
    filename: str
    uploaded: bool
    size_bytes: int
