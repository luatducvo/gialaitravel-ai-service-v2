"""Schemas for the custom itinerary REST API endpoint."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class TravelPace(str, Enum):
    slow = "slow"
    balanced = "balanced"
    fast = "fast"


class BudgetLevel(str, Enum):
    budget = "budget"
    mid_range = "mid_range"
    premium = "premium"


class PoiInput(BaseModel):
    """A POI snapshot selected and validated by the backend."""

    model_config = ConfigDict(populate_by_name=True)

    poi_id: str = Field(..., alias="poiId", description="Unique POI/location ID from the backend")
    poi_name: str = Field(..., alias="poiName", min_length=1, max_length=200, description="Display name")
    lat: float = Field(..., description="Latitude")
    lng: float = Field(..., description="Longitude")
    description: Optional[str] = Field(None, max_length=500, description="Short description")
    category: Optional[str] = Field(
        None,
        max_length=50,
        description="Type: restaurant, attraction, hotel, cafe, waterfall, ...",
    )
    tags: List[str] = Field(default_factory=list, max_length=20, description="Backend-provided tags")
    estimated_cost: Optional[float] = Field(
        0.0,
        alias="estimatedCost",
        ge=0,
        description="Estimated cost in VND",
    )
    duration_minutes: Optional[int] = Field(
        60,
        alias="durationMinutes",
        ge=10,
        le=480,
        description="Estimated visit duration in minutes",
    )
    intensity_level: Optional[IntensityLevel] = Field(
        IntensityLevel.medium,
        alias="intensityLevel",
        description="Activity intensity: low / medium / high",
    )
    image_url: Optional[str] = Field(
        None,
        alias="imageUrl",
        description="Representative image URL",
    )
    is_accommodation: bool = Field(
        False,
        alias="isAccommodation",
        description="True when the backend category marks this POI as accommodation",
    )

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, value: float) -> float:
        if not (13.0 <= value <= 15.0):
            raise ValueError(f"Latitude {value} is outside Gia Lai bounds (13.0-15.0)")
        return value

    @field_validator("lng")
    @classmethod
    def validate_lng(cls, value: float) -> float:
        if not (107.0 <= value <= 109.5):
            raise ValueError(f"Longitude {value} is outside Gia Lai bounds (107.0-109.5)")
        return value


class CustomItineraryRequest(BaseModel):
    """Request body for POST /api/v1/itineraries/custom."""

    model_config = ConfigDict(populate_by_name=True)

    duration: str = Field(..., min_length=1, max_length=50, description="Trip duration label")
    group: GroupType = Field(GroupType.friends, description="Traveler group type")
    transport: TransportType = Field(TransportType.motorbike, description="Transport type")
    travel_pace: TravelPace = Field(
        TravelPace.balanced,
        alias="travelPace",
        description="Preferred travel pace",
    )
    budget_level: BudgetLevel = Field(
        BudgetLevel.mid_range,
        alias="budgetLevel",
        description="Budget preference",
    )
    vibe: Optional[str] = Field(None, max_length=500, description="User travel vibe or preference text")
    constraints: List[str] = Field(default_factory=list, max_length=20, description="Known constraints")
    optimize_route: bool = Field(
        True,
        alias="optimizeRoute",
        description="Optimize POI order when true; keep user order when false",
    )
    start_location: Optional[PoiInput] = Field(
        None,
        alias="startLocation",
        description="Optional hotel/current location used as the route start anchor",
    )
    daily_start_time: str = Field(
        "06:00",
        alias="dailyStartTime",
        description="Preferred day start time in HH:MM",
    )
    daily_end_time: str = Field(
        "21:00",
        alias="dailyEndTime",
        description="Preferred day end time in HH:MM",
    )
    selected_pois: List[PoiInput] = Field(
        ...,
        alias="selectedPois",
        min_length=1,
        max_length=60,
        description="POI snapshots selected and validated by the backend",
    )

    @field_validator("daily_start_time", "daily_end_time")
    @classmethod
    def validate_hhmm(cls, value: str) -> str:
        import re

        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Time must use HH:MM 24-hour format")
        return value

    @model_validator(mode="after")
    def check_unique_poi_ids(self) -> "CustomItineraryRequest":
        poi_ids = [poi.poi_id for poi in self.selected_pois]
        if len(poi_ids) != len(set(poi_ids)):
            raise ValueError("selectedPois contains duplicate poiId values")
        return self


class RouteSummaryResponse(BaseModel):
    """Route optimization summary."""

    estimated_km: float = Field(..., description="Estimated total route distance in km")
    optimizer: str = Field(..., description="Optimizer used")
    distance_source: str = Field(
        "none",
        description="Distance source: google_maps | haversine_road_estimate | mixed | none",
    )
    total_pois: int = Field(..., description="Number of POIs in the itinerary")


class OptimizedPoiItem(BaseModel):
    """A POI item in the optimized route order."""

    poi_id: str = Field(..., description="Unique POI/location ID")
    poi_name: str = Field(..., description="Display name")
    lat: Optional[float] = Field(None, description="Latitude")
    lng: Optional[float] = Field(None, description="Longitude")
    route_order: int = Field(..., description="Route order, starting from 1")
    day_number: int = Field(1, alias="dayNumber", description="Trip day assigned by the route planner")
    day_route_order: int = Field(
        1,
        alias="dayRouteOrder",
        description="Route order within the assigned trip day",
    )
    distance_from_prev_km: float = Field(
        0.0,
        description="Road distance from the previous POI in km; 0 for the first item",
    )
    travel_from_previous_minutes: int = Field(
        0,
        description="Estimated travel time from the previous anchor/POI in minutes",
    )


class CustomItineraryResponse(BaseModel):
    """Response data for a generated itinerary."""

    itinerary: Itinerary = Field(..., description="Detailed itinerary")
    route_summary: RouteSummaryResponse = Field(..., description="Route optimization statistics")
    optimized_poi_order: List[OptimizedPoiItem] = Field(
        ...,
        description="Optimized POI order for rendering markers and polylines on the map",
    )
