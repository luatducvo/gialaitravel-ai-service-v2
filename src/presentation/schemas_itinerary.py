"""Schemas for the custom itinerary REST API endpoint."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from src.domain.itinerary import Itinerary


class GroupType(str, Enum):
    solo = "solo"
    couple = "couple"
    family = "family"
    friends = "friends"
    elderly = "elderly"


class TransportType(str, Enum):
    motorbike = "motorbike"
    car = "car"
    bus = "bus"


class IntensityLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class PoiInput(BaseModel):
    """Một địa điểm user chọn từ frontend."""

    poi_id: str = Field(..., description="ID duy nhất của POI (từ Qdrant hoặc frontend)")
    poi_name: str = Field(..., min_length=1, max_length=200, description="Tên hiển thị")
    lat: float = Field(..., description="Vĩ độ (latitude)")
    lng: float = Field(..., description="Kinh độ (longitude)")
    description: Optional[str] = Field(None, max_length=500, description="Mô tả ngắn")
    category: Optional[str] = Field(
        None,
        max_length=50,
        description="Loại: restaurant, attraction, hotel, cafe, waterfall, ...",
    )
    estimated_cost: Optional[float] = Field(0.0, ge=0, description="Chi phí ước tính (VND)")
    duration_minutes: Optional[int] = Field(60, ge=10, le=480, description="Thời gian tham quan (phút)")
    intensity_level: Optional[IntensityLevel] = Field(
        IntensityLevel.medium, description="Mức độ vận động: low / medium / high"
    )
    image_url: Optional[str] = Field(None, description="URL ảnh đại diện")

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v: float) -> float:
        if not (13.0 <= v <= 15.0):
            raise ValueError(f"Latitude {v} nằm ngoài vùng Gia Lai (13.0 – 15.0)")
        return v

    @field_validator("lng")
    @classmethod
    def validate_lng(cls, v: float) -> float:
        if not (107.0 <= v <= 109.5):
            raise ValueError(f"Longitude {v} nằm ngoài vùng Gia Lai (107.0 – 109.5)")
        return v


class CustomItineraryRequest(BaseModel):
    """Request body cho POST /api/v1/itineraries/custom."""

    poi_names: List[str] = Field(
        ..., min_length=1, max_length=20, description="Danh sách tên POI đã chọn (1-20)"
    )

    @model_validator(mode="after")
    def check_unique_poi_names(self) -> "CustomItineraryRequest":
        if len(self.poi_names) != len(set(self.poi_names)):
            raise ValueError("Danh sách tên POI chứa tên trùng lặp")
        return self


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class RouteSummaryResponse(BaseModel):
    """Tóm tắt route đã tối ưu."""

    estimated_km: float = Field(..., description="Tổng km ước tính")
    optimizer: str = Field(..., description="Thuật toán đã dùng")
    distance_source: str = Field(
        "none",
        description=(
            "Nguồn dữ liệu khoảng cách: 'google_maps' | 'haversine_road_estimate' "
            "| 'mixed' | 'none'"
        ),
    )
    total_pois: int = Field(..., description="Số POI trong itinerary")


class OptimizedPoiItem(BaseModel):
    """Một POI trong danh sách thứ tự tuyến đường đã tối ưu."""

    poi_id: str = Field(..., description="ID duy nhất của POI")
    poi_name: str = Field(..., description="Tên hiển thị")
    lat: Optional[float] = Field(None, description="Vĩ độ")
    lng: Optional[float] = Field(None, description="Kinh độ")
    route_order: int = Field(..., description="Thứ tự trong tuyến đường (bắt đầu từ 1)")
    distance_from_prev_km: float = Field(
        0.0, description="Khoảng cách đường bộ từ POI trước (km); 0 với điểm đầu tiên"
    )


class CustomItineraryResponse(BaseModel):
    """Response data cho itinerary đã tạo."""

    itinerary: Itinerary = Field(..., description="Lịch trình chi tiết (days → activities)")
    route_summary: RouteSummaryResponse = Field(..., description="Thống kê tối ưu route")
    optimized_poi_order: List[OptimizedPoiItem] = Field(
        ...,
        description=(
            "Thứ tự POI sau tối ưu kèm tọa độ — dùng để render marker + polyline trên bản đồ. "
            "Kiểm tra route_summary.optimizer để biết có tối ưu hay không."
        ),
    )
