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
    summary="Tạo lịch trình tối ưu từ danh sách POI tự chọn",
    description=(
        "Nhận danh sách địa điểm (POI) user tự chọn từ frontend, "
        "tối ưu thứ tự tham quan bằng nearest-neighbor + Google Maps, "
        "sau đó gọi LLM để sinh lịch trình chi tiết."
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
            message="Lịch trình đã được tạo thành công",
        )
    except Exception as exc:
        logger.error(f"Error creating custom itinerary: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                status_code=500,
                message="Không thể tạo lịch trình",
                details=str(exc),
            ).model_dump(),
        )
