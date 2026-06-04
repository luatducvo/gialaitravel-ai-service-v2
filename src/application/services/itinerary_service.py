"""Service (Use Case) for creating custom itineraries from user-selected POIs."""

from __future__ import annotations

from typing import List

from loguru import logger
from langsmith import traceable

from src.application.graph.nodes.route_optimizer import optimize_route
from src.application.graph.nodes.llm_planner import generate_itinerary_from_pois
from src.presentation.schemas_itinerary import (
    CustomItineraryRequest,
    CustomItineraryResponse,
    OptimizedPoiItem,
    PoiInput,
    RouteSummaryResponse,
)


def _poi_input_to_dict(poi: PoiInput) -> dict:
    """Convert a ``PoiInput`` schema into the dict format expected by the route optimizer."""
    return {
        "page_content": poi.description or poi.poi_name,
        "metadata": {
            "poi_id": poi.poi_id,
            "poi_name": poi.poi_name,
            "lat": poi.lat,
            "lng": poi.lng,
            "category": poi.category,
            "estimated_cost": poi.estimated_cost or 0.0,
            "cost": poi.estimated_cost or 0.0,
            "duration_minutes": poi.duration_minutes or 60,
            "intensity_level": poi.intensity_level.value if poi.intensity_level else "medium",
            "image_url": poi.image_url,
        },
    }


class CustomItineraryService:
    """Orchestrates route optimization + LLM itinerary generation for user-selected POIs."""

    @traceable(name="custom_itinerary_service")
    async def create_custom_itinerary(
        self, request: CustomItineraryRequest
    ) -> CustomItineraryResponse:
        logger.info(
            f"Creating custom itinerary: {len(request.pois)} POIs, "
            f"duration={request.duration}, group={request.group}, transport={request.transport}"
        )

        # 1. Convert PoiInput → dict format
        pois_as_dicts: List[dict] = []
        if request.start_location:
            pois_as_dicts.append(_poi_input_to_dict(request.start_location))
        pois_as_dicts.extend(_poi_input_to_dict(p) for p in request.pois)

        # 2. Route optimization
        ordered_pois, raw_summary = await optimize_route(
            pois_as_dicts, should_optimize=request.optimize_route
        )

        route_summary = RouteSummaryResponse(
            estimated_km=raw_summary["estimated_km"],
            optimizer=raw_summary["optimizer"],
            distance_source=raw_summary.get("distance_source", "none"),
            total_pois=len(ordered_pois),
        )

        # 3. Build vibe / note text for LLM
        vibe_text = request.note or "Khám phá theo lựa chọn cá nhân"

        # 4. LLM itinerary generation
        itinerary = await generate_itinerary_from_pois(
            ordered_pois=ordered_pois,
            route_summary=raw_summary,
            duration=request.duration,
            group=request.group.value,
            transport=request.transport.value,
            vibe=vibe_text,
        )

        logger.success("Custom itinerary generated successfully")

        # 5. Compose response
        optimized_order = [
            OptimizedPoiItem(
                poi_id=poi.get("metadata", {}).get("poi_id", ""),
                poi_name=poi.get("metadata", {}).get("poi_name", ""),
                lat=poi.get("metadata", {}).get("lat") or poi.get("metadata", {}).get("latitude"),
                lng=poi.get("metadata", {}).get("lng") or poi.get("metadata", {}).get("longitude"),
                route_order=poi.get("metadata", {}).get("route_order", idx + 1),
                distance_from_prev_km=poi.get("metadata", {}).get("distance_from_prev_km", 0.0),
            )
            for idx, poi in enumerate(ordered_pois)
        ]

        return CustomItineraryResponse(
            itinerary=itinerary.model_dump(),
            route_summary=route_summary,
            optimized_poi_order=optimized_order,
        )
