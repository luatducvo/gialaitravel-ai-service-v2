"""Service for creating custom itineraries from backend-provided POI snapshots."""

from __future__ import annotations

from typing import Any, Dict, List

from langsmith import traceable
from loguru import logger

from src.application.graph.nodes.llm_planner import generate_itinerary_from_pois
from src.application.graph.nodes.route_optimizer import optimize_route
from src.presentation.schemas_itinerary import (
    CustomItineraryRequest,
    CustomItineraryResponse,
    OptimizedPoiItem,
    PoiInput,
    RouteSummaryResponse,
)


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

        ordered_pois, raw_summary = await optimize_route(
            selected_pois,
            should_optimize=request.optimize_route,
        )

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
        allowed_poi_ids = {poi.poi_id for poi in request.selected_pois}
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
