"""Service for creating custom itineraries from backend-provided POI snapshots."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List

from langsmith import traceable
from loguru import logger

from src.application.graph.nodes.llm_planner import generate_itinerary_from_pois
from src.application.graph.nodes.route_optimizer import optimize_route
from src.application.services.distance import haversine_km
from src.presentation.schemas_itinerary import (
    CustomItineraryRequest,
    CustomItineraryResponse,
    OptimizedPoiItem,
    PoiInput,
    RouteSummaryResponse,
)


HOTEL_CATEGORIES = {"hotel", "accommodation", "lodging", "resort", "homestay"}


def _poi_snapshot_to_planner_dict(poi: PoiInput) -> Dict[str, Any]:
    """Map a selected POI snapshot into the internal planner/optimizer format."""
    description = poi.description or poi.poi_name
    cost = float(poi.estimated_cost or 0.0)
    duration_minutes = int(poi.duration_minutes or 60)
    intensity_level = (poi.intensity_level.value if poi.intensity_level else "medium")

    return {
        "page_content": description,
        "metadata": {
            "poi_id": poi.poi_id,
            "poi_name": poi.poi_name,
            "lat": float(poi.lat),
            "lng": float(poi.lng),
            "category": poi.category or "attraction",
            "tags": list(poi.tags),
            "cost": cost,
            "estimated_cost": cost,
            "duration_minutes": duration_minutes,
            "intensity_level": intensity_level,
            "image_url": poi.image_url,
        },
    }


def _metadata_by_poi_id(ordered_pois: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Index optimized POI metadata by backend POI id."""
    return {
        str(metadata.get("poi_id")): metadata
        for poi in ordered_pois
        if (metadata := poi.get("metadata", {})).get("poi_id")
    }


def _route_order_to_poi_id(ordered_pois: List[Dict[str, Any]]) -> Dict[str, str]:
    """Map route order labels that LLMs sometimes use back to real POI ids."""
    mapping: Dict[str, str] = {}
    for index, poi in enumerate(ordered_pois):
        metadata = poi.get("metadata", {})
        poi_id = metadata.get("poi_id")
        if not poi_id:
            continue

        route_order = metadata.get("route_order", index + 1)
        mapping[str(route_order)] = str(poi_id)
        mapping[str(index + 1)] = str(poi_id)

    return mapping


def _trip_day_count(duration: str) -> int:
    """Extract trip day count from labels like 2d1n, 2 days, or 2 ngay 1 dem."""
    normalized = duration.strip().lower()
    patterns = [
        r"(\d+)\s*d(?:\s*\d+\s*n)?",
        r"(\d+)\s*(?:day|days)\b",
        r"(\d+)\s*(?:ngay|ngày)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return max(1, int(match.group(1)))

    match = re.search(r"\d+", normalized)
    if match:
        return max(1, int(match.group(0)))
    return 1


def _is_hotel_poi(poi: Dict[str, Any]) -> bool:
    metadata = poi.get("metadata", {})
    category = str(metadata.get("category") or "").strip().lower()
    tags = {str(tag).strip().lower() for tag in metadata.get("tags", [])}
    return category in HOTEL_CATEGORIES or bool(tags & HOTEL_CATEGORIES)


def _coordinate_from_planner_poi(poi: Dict[str, Any]) -> tuple[float, float] | None:
    metadata = poi.get("metadata", {})
    lat = metadata.get("lat")
    lng = metadata.get("lng")
    try:
        if lat is None or lng is None:
            return None
        return float(lat), float(lng)
    except (TypeError, ValueError):
        return None


def _sort_for_daily_groups(
    pois: List[Dict[str, Any]],
    start_location: Dict[str, Any] | None,
) -> List[Dict[str, Any]]:
    """Sort POIs into a deterministic geographic sweep before day chunking."""
    coordinates = [_coordinate_from_planner_poi(poi) for poi in pois]
    valid_coordinates = [coord for coord in coordinates if coord]
    if not valid_coordinates:
        return list(pois)

    start_coord = (
        _coordinate_from_planner_poi(start_location)
        if start_location
        else None
    )
    if start_coord:
        anchor_lat, anchor_lng = start_coord
    else:
        anchor_lat = sum(coord[0] for coord in valid_coordinates) / len(valid_coordinates)
        anchor_lng = sum(coord[1] for coord in valid_coordinates) / len(valid_coordinates)

    def sort_key(poi: Dict[str, Any]) -> tuple[float, float]:
        coord = _coordinate_from_planner_poi(poi)
        if not coord:
            return (float("inf"), float("inf"))
        angle = math.atan2(coord[0] - anchor_lat, coord[1] - anchor_lng)
        distance = haversine_km(anchor_lat, anchor_lng, coord[0], coord[1])
        return (angle, distance)

    return sorted(pois, key=sort_key)


def _split_pois_by_trip_days(
    pois: List[Dict[str, Any]],
    *,
    duration: str,
    start_location: Dict[str, Any] | None,
) -> List[List[Dict[str, Any]]]:
    """Group selected POIs by trip duration before optimizing each day."""
    if not pois:
        return []

    day_count = min(_trip_day_count(duration), len(pois))
    if day_count <= 1:
        return [list(pois)]

    sorted_pois = _sort_for_daily_groups(pois, start_location)
    remaining_visit_minutes = sum(
        int(poi.get("metadata", {}).get("duration_minutes") or 60)
        for poi in sorted_pois
    )
    groups: List[List[Dict[str, Any]]] = []
    cursor = 0

    for day_index in range(day_count):
        remaining_days = day_count - day_index
        remaining_pois = len(sorted_pois) - cursor
        if remaining_days == 1:
            groups.append(sorted_pois[cursor:])
            break

        target_minutes = remaining_visit_minutes / remaining_days
        group: List[Dict[str, Any]] = []
        group_minutes = 0
        min_pois_for_day = max(1, remaining_pois // remaining_days)

        while cursor < len(sorted_pois):
            pois_left_after_take = len(sorted_pois) - cursor - 1
            if pois_left_after_take < remaining_days - 1:
                break

            poi = sorted_pois[cursor]
            duration_minutes = int(poi.get("metadata", {}).get("duration_minutes") or 60)
            should_stop = (
                len(group) >= min_pois_for_day
                and group_minutes > 0
                and group_minutes + duration_minutes > target_minutes
            )
            if should_stop:
                break

            group.append(poi)
            group_minutes += duration_minutes
            remaining_visit_minutes -= duration_minutes
            cursor += 1

        groups.append(group or [sorted_pois[cursor]])
        if not group:
            remaining_visit_minutes -= int(
                sorted_pois[cursor].get("metadata", {}).get("duration_minutes") or 60
            )
            cursor += 1

    return [group for group in groups if group]


def _normalize_itinerary_poi_ids(
    itinerary,
    ordered_pois: List[Dict[str, Any]],
    allowed_poi_ids: set[str],
) -> set[str]:
    """
    Convert accidental route_order values like "1" into backend POI ids.

    The prompt asks the LLM to copy real poi_id values, but some models still
    use the visible route order number. That is recoverable; invented IDs are
    still rejected by the caller.
    """
    metadata_by_id = _metadata_by_poi_id(ordered_pois)
    route_order_mapping = _route_order_to_poi_id(ordered_pois)
    unknown_poi_ids: set[str] = set()

    for day in itinerary.days:
        for activity in day.activities:
            activity_poi_id = str(activity.poi_id)
            normalized_poi_id = activity_poi_id

            if activity_poi_id not in allowed_poi_ids:
                normalized_poi_id = route_order_mapping.get(activity_poi_id, activity_poi_id)

            if normalized_poi_id not in allowed_poi_ids:
                unknown_poi_ids.add(activity_poi_id)
                continue

            if normalized_poi_id != activity_poi_id:
                logger.warning(
                    "Normalized LLM activity poi_id route_order {} -> {}",
                    activity_poi_id,
                    normalized_poi_id,
                )
                activity.poi_id = normalized_poi_id

            metadata = metadata_by_id.get(normalized_poi_id)
            if metadata:
                activity.poi_name = metadata.get("poi_name") or activity.poi_name
                activity.lat = float(metadata.get("lat", activity.lat))
                activity.lng = float(metadata.get("lng", activity.lng))
                activity.distance_from_prev_km = float(
                    metadata.get("distance_from_prev_km", activity.distance_from_prev_km)
                )

    return unknown_poi_ids


class CustomItineraryService:
    """Orchestrates route optimization and LLM itinerary generation."""

    @traceable(name="custom_itinerary_service")
    async def create_custom_itinerary(
        self, request: CustomItineraryRequest
    ) -> CustomItineraryResponse:
        logger.info(
            "Creating custom itinerary from {} backend-selected POIs | optimize_route={}",
            len(request.selected_pois),
            request.optimize_route,
        )

        selected_pois: List[Dict[str, Any]] = [
            _poi_snapshot_to_planner_dict(poi) for poi in request.selected_pois
        ]

        explicit_start_location = (
            _poi_snapshot_to_planner_dict(request.start_location)
            if request.start_location
            else None
        )
        hotel_start_location = next(
            (poi for poi in selected_pois if _is_hotel_poi(poi)),
            None,
        )
        start_location = explicit_start_location or hotel_start_location
        activity_pois = [
            poi for poi in selected_pois
            if not (start_location and poi.get("metadata", {}).get("poi_id") == start_location.get("metadata", {}).get("poi_id"))
        ]
        daily_groups = _split_pois_by_trip_days(
            activity_pois,
            duration=request.duration,
            start_location=start_location,
        )

        ordered_pois: List[Dict[str, Any]] = []
        total_km = 0.0
        distance_sources: List[str] = []
        optimizer_names: List[str] = []

        for day_number, daily_pois in enumerate(daily_groups, start=1):
            daily_ordered_pois, daily_summary = await optimize_route(
                daily_pois,
                should_optimize=request.optimize_route,
                start_location=start_location,
            )
            total_km += float(daily_summary["estimated_km"])
            optimizer_names.append(daily_summary["optimizer"])
            distance_source = daily_summary.get("distance_source", "none")
            if distance_source != "none":
                distance_sources.append(distance_source)

            for poi in daily_ordered_pois:
                metadata = poi.setdefault("metadata", {})
                metadata["day_number"] = day_number
                metadata["day_route_order"] = metadata.get("route_order", 1)
                metadata["route_order"] = len(ordered_pois) + 1
                ordered_pois.append(poi)

        if not distance_sources:
            overall_source = "none"
        elif all(source == "google_maps" for source in distance_sources):
            overall_source = "google_maps"
        elif all(source == "haversine_road_estimate" for source in distance_sources):
            overall_source = "haversine_road_estimate"
        else:
            overall_source = "mixed"

        if not optimizer_names:
            optimizer = "none"
        elif len(set(optimizer_names)) == 1:
            optimizer = optimizer_names[0]
        else:
            optimizer = "mixed"

        raw_summary = {
            "estimated_km": round(total_km, 2),
            "optimizer": optimizer,
            "distance_source": overall_source,
            "day_count": len(daily_groups),
            "start_location": (
                start_location.get("metadata", {}).get("poi_name")
                if start_location
                else None
            ),
        }

        route_summary = RouteSummaryResponse(
            estimated_km=raw_summary["estimated_km"],
            optimizer=raw_summary["optimizer"],
            distance_source=raw_summary.get("distance_source", "none"),
            total_pois=len(ordered_pois),
        )

        constraints = list(request.constraints)
        constraints.append(
            "Only use POIs from selectedPois. Do not add, replace, or invent locations."
        )
        constraints.append(
            "Respect each POI day_number. Build day 1 from day_number=1 POIs, day 2 from day_number=2 POIs, and so on."
        )
        if start_location:
            start_name = start_location.get("metadata", {}).get("poi_name", "the provided start location")
            constraints.append(
                f"Use {start_name} as the daily start location/hotel anchor, not as a sightseeing activity."
            )
        constraints.append(f"Travel pace: {request.travel_pace.value}")
        constraints.append(f"Budget level: {request.budget_level.value}")

        itinerary = await generate_itinerary_from_pois(
            ordered_pois=ordered_pois,
            route_summary=raw_summary,
            duration=request.duration,
            group=request.group.value,
            transport=request.transport.value,
            vibe=request.vibe,
            constraints=constraints,
        )
        allowed_poi_ids = {
            str(poi.get("metadata", {}).get("poi_id"))
            for poi in activity_pois
            if poi.get("metadata", {}).get("poi_id")
        }
        unknown_poi_ids = _normalize_itinerary_poi_ids(
            itinerary=itinerary,
            ordered_pois=ordered_pois,
            allowed_poi_ids=allowed_poi_ids,
        )
        if unknown_poi_ids:
            raise ValueError(
                "LLM returned POIs outside selectedPois: "
                + ", ".join(sorted(unknown_poi_ids))
            )

        optimized_order = [
            OptimizedPoiItem(
                poi_id=poi.get("metadata", {}).get("poi_id", ""),
                poi_name=poi.get("metadata", {}).get("poi_name", ""),
                lat=poi.get("metadata", {}).get("lat"),
                lng=poi.get("metadata", {}).get("lng"),
                route_order=poi.get("metadata", {}).get("route_order", index + 1),
                day_number=poi.get("metadata", {}).get("day_number", 1),
                day_route_order=poi.get("metadata", {}).get("day_route_order", index + 1),
                distance_from_prev_km=poi.get("metadata", {}).get("distance_from_prev_km", 0.0),
            )
            for index, poi in enumerate(ordered_pois)
        ]

        logger.success("Custom itinerary generated successfully")
        return CustomItineraryResponse(
            itinerary=itinerary,
            route_summary=route_summary,
            optimized_poi_order=optimized_order,
        )
