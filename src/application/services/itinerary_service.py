"""Service for creating custom itineraries from backend-provided POI snapshots."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from langsmith import traceable
from loguru import logger

from src.application.graph.nodes.llm_planner import generate_itinerary_from_pois
from src.application.graph.nodes.route_optimizer import optimize_route
from src.application.services.distance import haversine_km
from src.domain.itinerary import Activity, DayPlan
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
            "is_accommodation": poi.is_accommodation,
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
    return (
        bool(metadata.get("is_accommodation"))
        or category in HOTEL_CATEGORIES
        or bool(tags & HOTEL_CATEGORIES)
    )


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


def _distance_between_pois(
    origin: Dict[str, Any] | None,
    destination: Dict[str, Any],
) -> float:
    origin_coord = _coordinate_from_planner_poi(origin) if origin else None
    destination_coord = _coordinate_from_planner_poi(destination)
    if not origin_coord or not destination_coord:
        return float("inf")
    return haversine_km(origin_coord[0], origin_coord[1], destination_coord[0], destination_coord[1])


def _nearest_unassigned_poi(
    pois: List[Dict[str, Any]],
    anchor: Dict[str, Any] | None,
) -> Dict[str, Any]:
    if not anchor:
        return max(
            pois,
            key=lambda poi: float(poi.get("metadata", {}).get("score") or 0.0),
        )
    return min(pois, key=lambda poi: _distance_between_pois(anchor, poi))


def _nearest_to_group(
    pois: List[Dict[str, Any]],
    group: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return min(
        pois,
        key=lambda candidate: min(_distance_between_pois(anchor, candidate) for anchor in group),
    )


def _split_pois_by_trip_days(
    pois: List[Dict[str, Any]],
    *,
    duration: str,
    start_location: Dict[str, Any] | None,
) -> List[List[Dict[str, Any]]]:
    """Cluster selected POIs by nearby geography and visit duration before routing."""
    if not pois:
        return []

    day_count = min(_trip_day_count(duration), len(pois))
    if day_count <= 1:
        return [list(pois)]

    unassigned = list(pois)
    remaining_visit_minutes = sum(_visit_minutes(poi) for poi in unassigned)
    groups: List[List[Dict[str, Any]]] = []
    rolling_anchor = start_location

    for day_index in range(day_count):
        remaining_days = day_count - day_index
        if remaining_days == 1:
            groups.append(unassigned)
            break

        target_minutes = remaining_visit_minutes / remaining_days
        first_poi = _nearest_unassigned_poi(unassigned, rolling_anchor)
        group: List[Dict[str, Any]] = [first_poi]
        unassigned.remove(first_poi)
        group_minutes = _visit_minutes(first_poi)
        remaining_visit_minutes -= group_minutes
        min_pois_for_day = max(1, (len(unassigned) + 1) // remaining_days)

        while unassigned:
            pois_left_after_take = len(unassigned) - 1
            if pois_left_after_take < remaining_days - 1:
                break

            next_poi = _nearest_to_group(unassigned, group)
            next_minutes = _visit_minutes(next_poi)
            if len(group) >= min_pois_for_day and group_minutes + next_minutes > target_minutes:
                break

            group.append(next_poi)
            unassigned.remove(next_poi)
            group_minutes += next_minutes
            remaining_visit_minutes -= next_minutes

        groups.append(group)
        rolling_anchor = group[-1]

    return [group for group in groups if group]


def _split_ordered_pois_by_trip_days(
    pois: List[Dict[str, Any]],
    *,
    duration: str,
) -> List[List[Dict[str, Any]]]:
    """Split a globally ordered TSP path into day buckets without reordering."""
    if not pois:
        return []

    day_count = min(_trip_day_count(duration), len(pois))
    if day_count <= 1:
        return [list(pois)]

    remaining = list(pois)
    remaining_visit_minutes = sum(_visit_minutes(poi) for poi in remaining)
    groups: List[List[Dict[str, Any]]] = []

    for day_index in range(day_count):
        remaining_days = day_count - day_index
        if remaining_days == 1:
            groups.append(remaining)
            break

        target_minutes = remaining_visit_minutes / remaining_days
        group: List[Dict[str, Any]] = []
        group_minutes = 0

        while remaining:
            pois_left_after_take = len(remaining) - 1
            if group and pois_left_after_take < remaining_days - 1:
                break

            next_poi = remaining[0]
            next_minutes = _visit_minutes(next_poi)
            if group and group_minutes + next_minutes > target_minutes:
                break

            group.append(remaining.pop(0))
            group_minutes += next_minutes
            remaining_visit_minutes -= next_minutes

        if not group and remaining:
            next_poi = remaining.pop(0)
            group.append(next_poi)
            remaining_visit_minutes -= _visit_minutes(next_poi)

        groups.append(group)

    return [group for group in groups if group]


def _visit_minutes(poi: Dict[str, Any]) -> int:
    return int(poi.get("metadata", {}).get("duration_minutes") or 60)


def _time_to_minutes(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def _minutes_to_time(value: int) -> str:
    value = max(0, min(value, 23 * 60 + 59))
    return f"{value // 60:02d}:{value % 60:02d}"


def _travel_minutes(distance_km: float, transport: str) -> int:
    if distance_km <= 0:
        return 0
    speeds = {"motorbike": 28.0, "car": 35.0, "bus": 24.0}
    speed = speeds.get(transport, 28.0)
    return max(1, round(distance_km / speed * 60))


def _ordered_activity_template(itinerary) -> Dict[str, Activity]:
    return {
        str(activity.poi_id): activity
        for day in itinerary.days
        for activity in day.activities
    }


def _apply_deterministic_schedule(
    itinerary,
    ordered_pois: List[Dict[str, Any]],
    request: CustomItineraryRequest,
) -> None:
    """Make day grouping and time slots deterministic after LLM text generation."""
    activity_by_poi_id = _ordered_activity_template(itinerary)
    start_minutes = _time_to_minutes(request.daily_start_time)
    end_minutes = _time_to_minutes(request.daily_end_time)
    grouped: Dict[int, List[Dict[str, Any]]] = {}

    for poi in ordered_pois:
        metadata = poi.get("metadata", {})
        day_number = int(metadata.get("day_number") or 1)
        grouped.setdefault(day_number, []).append(poi)

    days: List[DayPlan] = []
    for day_number in sorted(grouped):
        cursor = start_minutes
        activities: List[Activity] = []
        total_km = 0.0

        for poi in grouped[day_number]:
            metadata = poi.get("metadata", {})
            poi_id = str(metadata.get("poi_id") or "")
            llm_activity = activity_by_poi_id.get(poi_id)
            distance_km = float(metadata.get("distance_from_prev_km") or 0.0)
            travel_minutes = _travel_minutes(distance_km, request.transport.value)
            visit_minutes = _visit_minutes(poi)

            cursor += travel_minutes
            start = cursor
            end = min(start + visit_minutes, end_minutes)
            cursor = min(end + 15, end_minutes)
            total_km += distance_km

            activities.append(
                Activity(
                    time_slot=f"{_minutes_to_time(start)}-{_minutes_to_time(end)}",
                    poi_id=poi_id,
                    poi_name=metadata.get("poi_name") or (llm_activity.poi_name if llm_activity else poi_id),
                    lat=float(metadata.get("lat") or 0.0),
                    lng=float(metadata.get("lng") or 0.0),
                    duration_minutes=visit_minutes,
                    cost=float(metadata.get("cost") or 0.0),
                    distance_from_prev_km=round(distance_km, 2),
                    travel_from_previous_minutes=travel_minutes,
                    intensity_level=str(metadata.get("intensity_level") or "medium"),
                    note=(llm_activity.note if llm_activity else "Recommended stop"),
                )
            )

        days.append(
            DayPlan(
                day=day_number,
                title=(
                    itinerary.days[day_number - 1].title
                    if day_number - 1 < len(itinerary.days)
                    else f"Day {day_number}"
                ),
                total_km=round(total_km, 2),
                activities=activities,
            )
        )

    itinerary.days = days
    itinerary.total_km = round(sum(day.total_km for day in days), 2)
    itinerary.total_cost = round(
        sum(activity.cost for day in days for activity in day.activities),
        2,
    )


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
        has_fixed_daily_start = start_location is not None
        activity_pois = [
            poi for poi in selected_pois
            if not (start_location and poi.get("metadata", {}).get("poi_id") == start_location.get("metadata", {}).get("poi_id"))
        ]
        global_ordered_pois, global_summary = await optimize_route(
            activity_pois,
            should_optimize=request.optimize_route,
            start_location=start_location,
        )
        daily_groups = _split_ordered_pois_by_trip_days(
            global_ordered_pois,
            duration=request.duration,
        )

        ordered_pois: List[Dict[str, Any]] = []
        for day_number, daily_pois in enumerate(daily_groups, start=1):
            for day_route_order, poi in enumerate(daily_pois, start=1):
                metadata = poi.setdefault("metadata", {})
                if has_fixed_daily_start and start_location and day_route_order == 1 and day_number > 1:
                    metadata["distance_from_prev_km"] = round(
                        _distance_between_pois(start_location, poi),
                        2,
                    )
                metadata["day_number"] = day_number
                metadata["day_route_order"] = day_route_order
                metadata["route_order"] = len(ordered_pois) + 1
                ordered_pois.append(poi)

        total_km = sum(
            float(poi.get("metadata", {}).get("distance_from_prev_km") or 0.0)
            for poi in ordered_pois
        )
        optimizer = str(global_summary.get("optimizer", "none"))
        overall_source = str(global_summary.get("distance_source", "none"))

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

        _apply_deterministic_schedule(
            itinerary=itinerary,
            ordered_pois=ordered_pois,
            request=request,
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
                travel_from_previous_minutes=_travel_minutes(
                    float(poi.get("metadata", {}).get("distance_from_prev_km", 0.0) or 0.0),
                    request.transport.value,
                ),
            )
            for index, poi in enumerate(ordered_pois)
        ]

        logger.success("Custom itinerary generated successfully")
        return CustomItineraryResponse(
            itinerary=itinerary,
            route_summary=route_summary,
            optimized_poi_order=optimized_order,
        )
