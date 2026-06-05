"""Service (Use Case) for creating custom itineraries from user-selected POIs."""

from __future__ import annotations

import asyncio
import random
from typing import List

from loguru import logger
from langsmith import traceable

from src.application.graph.nodes.route_optimizer import optimize_route
from src.application.graph.nodes.llm_planner import generate_itinerary_from_pois
from src.infrastructure.vector_db import get_qdrant_client
from src.infrastructure.qdrant_repo import QdrantRepository
from src.presentation.schemas_itinerary import (
    CustomItineraryRequest,
    CustomItineraryResponse,
    OptimizedPoiItem,
    RouteSummaryResponse,
)


def _sanitize_poi_dict(poi: dict) -> dict:
    """Đảm bảo POI dict từ Qdrant hoặc fallback có đầy đủ cấu trúc metadata tối thiểu."""
    metadata = poi.setdefault("metadata", {})
    
    # Đồng bộ hóa các trường tọa độ
    lat = metadata.get("lat") or metadata.get("latitude") or 13.982
    lng = metadata.get("lng") or metadata.get("longitude") or metadata.get("lon") or 108.005
    metadata["lat"] = float(lat)
    metadata["lng"] = float(lng)
    
    # Đồng bộ hóa chi phí
    cost = metadata.get("cost") or metadata.get("estimated_cost") or 0.0
    metadata["cost"] = float(cost)
    metadata["estimated_cost"] = float(cost)
    
    # Các trường định danh và mô tả khác
    metadata.setdefault("poi_id", f"poi_{abs(hash(metadata.get('poi_name', '')))}")
    metadata.setdefault("poi_name", poi.get("page_content", "Unknown POI"))
    metadata.setdefault("category", "attraction")
    metadata.setdefault("duration_minutes", 60)
    metadata.setdefault("intensity_level", "medium")
    
    return poi


class CustomItineraryService:
    """Orchestrates route optimization + LLM itinerary generation for user-selected POIs."""

    def __init__(self):
        self.qdrant_client = get_qdrant_client()
        self.repo = QdrantRepository(client=self.qdrant_client)

    @traceable(name="custom_itinerary_service")
    async def create_custom_itinerary(
        self, request: CustomItineraryRequest
    ) -> CustomItineraryResponse:
        logger.info(
            f"Creating custom itinerary: {len(request.poi_names)} POI names"
        )

        resolved_pois: List[dict] = []
        exclude_ids = set()

        # 1. Phân giải các POI chính song song từ Qdrant
        tasks = [asyncio.to_thread(self.repo.similarity_search, name, 1) for name in request.poi_names]
        search_results_lists = await asyncio.gather(*tasks)

        # Danh sách chỉ mục cần thay thế (nếu tìm kiếm thất bại / score < 0.65)
        indices_to_replace = []

        for idx, (name, results) in enumerate(zip(request.poi_names, search_results_lists)):
            if results and results[0].get("score", 0.0) >= 0.65:
                poi = _sanitize_poi_dict(results[0])
                poi_id = poi["metadata"]["poi_id"]
                if poi_id not in exclude_ids:
                    resolved_pois.append(poi)
                    exclude_ids.add(poi_id)
                    logger.info(f"Resolved POI '{name}' to '{poi['metadata']['poi_name']}' (Score: {results[0].get('score', 0.0):.2f})")
                else:
                    # Tránh trùng lặp POI, coi như cần thay thế bằng điểm khác
                    logger.warning(f"POI '{poi['metadata']['poi_name']}' bị trùng lặp. Sẽ thay thế.")
                    indices_to_replace.append(idx)
            else:
                logger.warning(f"Không thể phân giải POI: '{name}' (Score < 0.65 hoặc không tìm thấy). Sẽ thay thế.")
                indices_to_replace.append(idx)

        # 2. Lấy các địa điểm ngẫu nhiên để thay thế cho những địa điểm không tìm thấy
        if indices_to_replace:
            # Query 50 điểm du lịch Gia Lai làm nguồn thay thế ngẫu nhiên
            random_pool = await asyncio.to_thread(self.repo.similarity_search, "điểm du lịch Gia Lai", 50)
            valid_candidates = [
                _sanitize_poi_dict(item)
                for item in random_pool
                if item.get("metadata", {}).get("poi_id") not in exclude_ids
            ]
            
            # Trộn ngẫu nhiên các ứng viên
            random.shuffle(valid_candidates)
            
            for idx in indices_to_replace:
                if valid_candidates:
                    replacement = valid_candidates.pop(0)
                    resolved_pois.append(replacement)
                    exclude_ids.add(replacement["metadata"]["poi_id"])
                    logger.info(f"Thay thế POI tại chỉ mục {idx} bằng POI ngẫu nhiên từ Qdrant: '{replacement['metadata']['poi_name']}'")
                else:
                    # Fallback cực hạn nếu hết ứng viên ngẫu nhiên
                    fallback_name = request.poi_names[idx]
                    fallback_poi = _sanitize_poi_dict({
                        "page_content": fallback_name,
                        "metadata": {
                            "poi_id": f"fallback_{abs(hash(fallback_name))}",
                            "poi_name": fallback_name,
                            "lat": 13.982,
                            "lng": 108.005,
                            "category": "attraction",
                            "cost": 0.0,
                            "duration_minutes": 60,
                            "intensity_level": "medium"
                        }
                    })
                    resolved_pois.append(fallback_poi)
                    logger.warning(f"Không còn ứng viên ngẫu nhiên, sử dụng fallback Pleiku cho: '{fallback_name}'")

        # 3. Tối ưu hóa lộ trình di chuyển (luôn bật tối ưu hóa lộ trình làm mặc định)
        ordered_pois, raw_summary = await optimize_route(
            resolved_pois, should_optimize=True
        )

        route_summary = RouteSummaryResponse(
            estimated_km=raw_summary["estimated_km"],
            optimizer=raw_summary["optimizer"],
            distance_source=raw_summary.get("distance_source", "none"),
            total_pois=len(ordered_pois),
        )

        # 4. Xác định thời gian đi dựa trên số lượng địa điểm thực tế
        num_pois = len(ordered_pois)
        if num_pois <= 4:
            duration = "1 ngày"
        elif num_pois <= 8:
            duration = "2 ngày 1 đêm"
        elif num_pois <= 12:
            duration = "3 ngày 2 đêm"
        else:
            duration = "4 ngày 3 đêm"

        group_val = "friends"
        transport_val = "motorbike"
        vibe_text = "Khám phá tự do các địa điểm đã chọn tại Gia Lai"

        # 5. Gọi LLM để sinh lịch trình chi tiết
        itinerary = await generate_itinerary_from_pois(
            ordered_pois=ordered_pois,
            route_summary=raw_summary,
            duration=duration,
            group=group_val,
            transport=transport_val,
            vibe=vibe_text,
        )

        logger.success("Custom itinerary generated successfully")

        # 6. Định dạng kết quả trả về
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
            itinerary=itinerary,
            route_summary=route_summary,
            optimized_poi_order=optimized_order,
        )

