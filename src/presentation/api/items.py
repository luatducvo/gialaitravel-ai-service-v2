from fastapi import APIRouter, Depends, HTTPException, status, Response, Query
from fastapi.responses import JSONResponse
from typing import List, Optional
from src.presentation.schemas import ItemCreate, ItemResponse, BaseResponse, ErrorResponse
from src.application.use_cases import ItemService
from src.presentation.dependencies import get_item_service

# API Design Pattern: Path Versioning, Resource is plural
router = APIRouter(prefix="/api/v1/items", tags=["items"])

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=BaseResponse[ItemResponse])
def create_item(item: ItemCreate, response: Response, service: ItemService = Depends(get_item_service)):
    # Create action
    result = service.create_item(name=item.name, description=item.description)
    
    # API Design Pattern: 201 Created with Location header
    response.status_code = status.HTTP_201_CREATED
    response.headers["Location"] = f"/api/v1/items/{result.id}"
    
    return BaseResponse(data=result, message="Item created successfully")

@router.get("/{item_id}", response_model=BaseResponse[ItemResponse], responses={404: {"model": ErrorResponse}})
def get_item(item_id: int, service: ItemService = Depends(get_item_service)):
    try:
        result = service.get_item(item_id)
        return BaseResponse(data=result)
    except ValueError as e:
        # API Design Pattern: Structured Error Response for 404
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                status_code=404,
                message="Resource not found",
                details=[{"field": "item_id", "message": str(e), "code": "not_found"}]
            ).model_dump()
        )

@router.get("/", response_model=BaseResponse[List[ItemResponse]])
def list_items(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    service: ItemService = Depends(get_item_service)
):
    # API Design Pattern: Offset-based pagination for lists
    # Note: Service implementation should support pagination parameters
    results = service.list_items() # (page=page, per_page=per_page)
    return BaseResponse(data=results)
