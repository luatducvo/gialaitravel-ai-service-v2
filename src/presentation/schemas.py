from pydantic import BaseModel, ConfigDict
from typing import Optional, Generic, TypeVar, Any
from datetime import datetime

T = TypeVar("T")

class BaseResponse(BaseModel, Generic[T]):
    """Standard generic wrapper for all API responses"""
    status_code: int = 200
    message: str = "Success"
    data: Optional[T] = None

class ErrorResponse(BaseModel):
    """Standard generic wrapper for error responses"""
    status_code: int
    message: str
    details: Optional[Any] = None

class ItemCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
