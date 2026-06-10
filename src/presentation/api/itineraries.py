"""REST API router for custom itinerary generation."""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from loguru import logger

from src.application.services.itinerary_service import CustomItineraryService
from src.presentation.dependencies import get_custom_itinerary_service
from src.presentation.schemas import BaseResponse, ErrorResponse
from src.presentation.schemas_itinerary import (
    CustomItineraryRequest,
    CustomItineraryResponse,
)

router = APIRouter(prefix="/api/v1/itineraries", tags=["itineraries"])


@router.post(
    "/custom",
    response_model=BaseResponse[CustomItineraryResponse],
    responses={
        422: {"model": ErrorResponse, "description": "Validation Error"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"},
    },
    summary="Create itinerary from backend-selected POI snapshots",
    description=(
        "Internal Agent API for NestJS Backend. Receives POI snapshots that the "
        "backend already validated from PostgreSQL, optionally optimizes route "
        "order, then calls the LLM planner. This endpoint does not query Qdrant, "
        "does not access the database, and does not replace selected POIs."
    ),
)
async def create_custom_itinerary(
    request: CustomItineraryRequest,
    service: CustomItineraryService = Depends(get_custom_itinerary_service),
):
    try:
        result = await service.create_custom_itinerary(request)
        return BaseResponse(
            data=result,
            message="Lich trinh da duoc tao thanh cong",
        )
    except Exception as exc:
        logger.error(f"Error creating custom itinerary: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                status_code=500,
                message="Khong the tao lich trinh",
                details=str(exc),
            ).model_dump(),
        )
