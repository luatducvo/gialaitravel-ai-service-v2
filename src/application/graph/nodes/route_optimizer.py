"""
Node route_optimizer: Tối ưu thứ tự tham quan POI.

Node này nhận ``qdrant_results`` từ ``qdrant_search_node`` và thực hiện:

1. **Sắp xếp POI** bằng thuật toán Nearest Neighbor (greedy) dựa trên tọa độ
   lat/lng. Thứ tự được ghi vào ``metadata["route_order"]``.

2. **Tính khoảng cách segment** giữa hai POI liên tiếp (dùng để LLM planner
   xây dựng lịch trình theo thời gian di chuyển thực tế):
   - Ưu tiên Google Maps Distance Matrix API nếu ``GOOGLE_MAPS_API_KEY`` được cấu hình.
   - Fallback về road-distance ước tính (haversine × mountain terrain factor).
   - Giá trị ghi vào ``metadata["distance_from_prev_km"]``.

3. **Tổng hợp route_summary**: ``estimated_km``, ``optimizer``, ``distance_source``.

Chi phí (cost) không được tính ở đây — đó là trách nhiệm của LLM planner.

Module cung cấp hàm thuần ``optimize_route()`` có thể tái sử dụng từ REST API
service mà không cần đi qua LangGraph node.
"""

from __future__ import annotations

import copy
import itertools
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx
from loguru import logger

from src.application.graph.state import AgentState
from src.application.services.distance import haversine_km, road_distance_km
from src.core.config import settings


Coordinate = Tuple[float, float]

# Timeout cho Google Maps Distance Matrix API
_GOOGLE_MAPS_TIMEOUT_SECONDS = 6.0


def _coordinate_from_metadata(metadata: Dict[str, Any]) -> Optional[Coordinate]:
    """Trích xuất tọa độ (lat, lng) từ metadata của một POI.

    Hỗ trợ nhiều key convention: ``lat``/``latitude``, ``lng``/``lon``/``longitude``.

    Args:
        metadata: Dict metadata của POI từ Qdrant.

    Returns:
        Tuple (lat, lng) dưới dạng float, hoặc ``None`` nếu thiếu/không hợp lệ.
    """
    lat = metadata.get("lat") or metadata.get("latitude")
    lng = metadata.get("lng") or metadata.get("lon") or metadata.get("longitude")
    try:
        if lat is None or lng is None:
            return None
        return float(lat), float(lng)
    except (TypeError, ValueError):
        return None


def _nearest_neighbor_order(
    pois: List[Dict[str, Any]],
    *,
    start_location: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Sắp xếp danh sách POI theo thuật toán Nearest Neighbor (greedy TSP).

    Bắt đầu từ POI đầu tiên, mỗi bước chọn POI chưa thăm gần nhất theo
    khoảng cách haversine. POI không có tọa độ hợp lệ được append vào cuối.

    Không mutate list hoặc dict gốc.

    Args:
        pois: Danh sách POI chưa sắp xếp (không bị mutate).

    Returns:
        Danh sách POI đã sắp xếp. Nếu có ít hơn 3 POI trả về bản copy.
    """
    if len(pois) < 3 and not start_location:
        return list(pois)

    remaining = list(pois)
    start_coord = None
    if start_location:
        start_coord = _coordinate_from_metadata(start_location.get("metadata", {}))

    if start_coord:
        next_index = min(
            range(len(remaining)),
            key=lambda idx: _distance_for_sort(
                start_coord,
                _coordinate_from_metadata(remaining[idx].get("metadata", {})),
            ),
        )
        ordered = [remaining.pop(next_index)]
    else:
        ordered = [remaining.pop(0)]

    while remaining:
        current_coord = _coordinate_from_metadata(ordered[-1].get("metadata", {}))
        if not current_coord:
            ordered.extend(remaining)
            break

        next_index = min(
            range(len(remaining)),
            key=lambda idx: _distance_for_sort(
                current_coord,
                _coordinate_from_metadata(remaining[idx].get("metadata", {})),
            ),
        )
        ordered.append(remaining.pop(next_index))

    return ordered


def _path_distance(
    order: List[int],
    distance_matrix: List[List[float]],
    start_distances: Optional[List[float]] = None,
) -> float:
    if not order:
        return 0.0

    total = start_distances[order[0]] if start_distances else 0.0
    for left, right in zip(order, order[1:]):
        total += distance_matrix[left][right]
    return total


def _build_distance_matrix(coords: List[Coordinate]) -> List[List[float]]:
    return [
        [
            0.0 if left_index == right_index else haversine_km(left[0], left[1], right[0], right[1])
            for right_index, right in enumerate(coords)
        ]
        for left_index, left in enumerate(coords)
    ]


def _nearest_neighbor_index_order(
    distance_matrix: List[List[float]],
    *,
    start_distances: Optional[List[float]] = None,
    start_index: Optional[int] = None,
) -> List[int]:
    remaining = set(range(len(distance_matrix)))
    if start_distances:
        current = min(remaining, key=lambda idx: start_distances[idx])
    elif start_index is not None:
        current = start_index
    else:
        current = 0

    ordered = [current]
    remaining.remove(current)

    while remaining:
        current = min(remaining, key=lambda idx: distance_matrix[ordered[-1]][idx])
        ordered.append(current)
        remaining.remove(current)

    return ordered


def _two_opt_order(
    order: List[int],
    distance_matrix: List[List[float]],
    *,
    start_distances: Optional[List[float]] = None,
) -> List[int]:
    if len(order) < 4:
        return order

    best = list(order)
    best_distance = _path_distance(best, distance_matrix, start_distances)
    improved = True

    while improved:
        improved = False
        for left in range(len(best) - 2):
            for right in range(left + 2, len(best)):
                candidate = best[:left + 1] + list(reversed(best[left + 1:right + 1])) + best[right + 1:]
                candidate_distance = _path_distance(candidate, distance_matrix, start_distances)
                if candidate_distance + 1e-9 < best_distance:
                    best = candidate
                    best_distance = candidate_distance
                    improved = True
                    break
            if improved:
                break

    return best


def _exact_tsp_path_order(
    distance_matrix: List[List[float]],
    *,
    start_distances: Optional[List[float]] = None,
) -> List[int]:
    best_order: List[int] | None = None
    best_distance = float("inf")

    for permutation in itertools.permutations(range(len(distance_matrix))):
        order = list(permutation)
        distance = _path_distance(order, distance_matrix, start_distances)
        if distance < best_distance:
            best_order = order
            best_distance = distance

    return best_order or []


def _global_tsp_order(
    pois: List[Dict[str, Any]],
    *,
    start_location: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """Order POIs as one global open TSP path, then append invalid-coordinate POIs."""
    valid_items: List[Tuple[int, Dict[str, Any], Coordinate]] = []
    invalid_items: List[Tuple[int, Dict[str, Any]]] = []

    for index, poi in enumerate(pois):
        coord = _coordinate_from_metadata(poi.get("metadata", {}))
        if coord:
            valid_items.append((index, poi, coord))
        else:
            invalid_items.append((index, poi))

    if len(valid_items) < 2:
        return list(pois), "tsp_exact"

    coords = [coord for _, _, coord in valid_items]
    distance_matrix = _build_distance_matrix(coords)
    start_coord = (
        _coordinate_from_metadata(start_location.get("metadata", {}))
        if start_location
        else None
    )
    start_distances = (
        [_distance_for_sort(start_coord, coord) for coord in coords]
        if start_coord
        else None
    )

    if len(valid_items) <= 8:
        order_indexes = _exact_tsp_path_order(
            distance_matrix,
            start_distances=start_distances,
        )
        optimizer_name = "tsp_exact"
    else:
        seeds = [
            _nearest_neighbor_index_order(
                distance_matrix,
                start_distances=start_distances,
                start_index=None if start_distances else seed_index,
            )
            for seed_index in range(len(valid_items))
        ]
        seed_order = min(
            seeds,
            key=lambda order: _path_distance(order, distance_matrix, start_distances),
        )
        order_indexes = _two_opt_order(
            seed_order,
            distance_matrix,
            start_distances=start_distances,
        )
        optimizer_name = "tsp_2opt"

    ordered_valid = [valid_items[index][1] for index in order_indexes]
    ordered_invalid = [poi for _, poi in sorted(invalid_items, key=lambda item: item[0])]
    return ordered_valid + ordered_invalid, optimizer_name


def _distance_for_sort(origin: Coordinate, destination: Optional[Coordinate]) -> float:
    """Khoảng cách haversine để dùng trong sorting (không cần độ chính xác cao).

    Args:
        origin: Tọa độ điểm xuất phát.
        destination: Tọa độ điểm đích; ``None`` nếu POI thiếu tọa độ.

    Returns:
        Khoảng cách km. Trả về ``inf`` nếu destination là ``None``.
    """
    if not destination:
        return float("inf")
    return haversine_km(origin[0], origin[1], destination[0], destination[1])


async def _google_distance_km_async(
    origin: Coordinate,
    destination: Coordinate,
) -> Optional[float]:
    """Gọi Google Maps Distance Matrix API (async) để lấy khoảng cách đường thực tế.

    Chỉ được gọi khi ``settings.GOOGLE_MAPS_API_KEY`` được cấu hình.

    Returns:
        Khoảng cách km (float, làm tròn 2 chữ số), hoặc ``None`` nếu
        API key không có, request thất bại, hoặc response không hợp lệ.
    """
    api_key = settings.GOOGLE_MAPS_API_KEY
    if not api_key:
        return None

    params = urlencode(
        {
            "origins": f"{origin[0]},{origin[1]}",
            "destinations": f"{destination[0]},{destination[1]}",
            "key": api_key,
        }
    )
    url = f"https://maps.googleapis.com/maps/api/distancematrix/json?{params}"

    try:
        async with httpx.AsyncClient(timeout=_GOOGLE_MAPS_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
        logger.warning(f"Google Maps distance request failed: {exc}")
        return None

    rows = body.get("rows") or []
    elements = rows[0].get("elements") if rows else []
    element = elements[0] if elements else {}
    meters = (element.get("distance") or {}).get("value")
    if not meters:
        logger.warning("Google Maps returned empty distance element, falling back to haversine")
        return None
    return round(float(meters) / 1000, 2)


async def _segment_distance_km_async(
    origin: Coordinate,
    destination: Coordinate,
) -> Tuple[float, str]:
    """Tính khoảng cách đường bộ giữa hai POI liên tiếp (async).

    Ưu tiên Google Maps, fallback về haversine × mountain terrain factor.

    Returns:
        Tuple (distance_km, source): source là ``"google_maps"`` hoặc
        ``"haversine_road_estimate"``.
    """
    google_distance = await _google_distance_km_async(origin, destination)
    if google_distance is not None:
        return google_distance, "google_maps"

    fallback = round(
        road_distance_km(origin[0], origin[1], destination[0], destination[1]), 2
    )
    return fallback, "haversine_road_estimate"


async def optimize_route(
    pois: List[Dict[str, Any]],
    *,
    should_optimize: bool = True,
    start_location: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Pure async function: sắp xếp thứ tự POI tối ưu và tính khoảng cách segment.

    Không tính chi phí — đó là trách nhiệm của LLM planner.
    Không mutate input. Deep-copy từng POI trước khi gắn thêm metadata.

    Args:
        pois: Danh sách POI từ Qdrant (không bị mutate).
        should_optimize: Nếu ``True``, áp dụng nearest-neighbor sort.
            Nếu ``False``, giữ nguyên thứ tự do người dùng định nghĩa.

    Returns:
        Tuple (ordered_pois, route_summary):
            - ``ordered_pois``: Deep-copy POI đã sắp xếp, mỗi item có thêm
              ``route_order`` và ``distance_from_prev_km`` trong metadata.
            - ``route_summary``: Dict với ``estimated_km``, ``optimizer``
              (``"nearest_neighbor"`` | ``"user_defined_order"``), và
              ``distance_source`` (``"google_maps"`` | ``"haversine_road_estimate"``
              | ``"mixed"`` | ``"none"``).
    """
    if not pois:
        return [], {
            "estimated_km": 0.0,
            "optimizer": "none",
            "distance_source": "none",
        }

    # Sort phase — không mutate original
    optimizer_name = "user_defined_order"
    if should_optimize:
        sorted_pois, optimizer_name = _global_tsp_order(
            pois,
            start_location=start_location,
        )
    else:
        sorted_pois = list(pois)

    # Deep-copy để hoàn toàn tách biệt với input
    ordered_pois: List[Dict[str, Any]] = [copy.deepcopy(p) for p in sorted_pois]

    total_km = 0.0
    previous_coord: Optional[Coordinate] = (
        _coordinate_from_metadata(start_location.get("metadata", {}))
        if start_location
        else None
    )
    distance_sources: List[str] = []

    for index, poi in enumerate(ordered_pois):
        metadata = poi.setdefault("metadata", {})
        metadata["route_order"] = index + 1

        current_coord = _coordinate_from_metadata(metadata)
        distance_from_prev = 0.0

        if previous_coord and current_coord:
            distance_from_prev, source = await _segment_distance_km_async(
                previous_coord, current_coord
            )
            total_km += distance_from_prev
            distance_sources.append(source)

        metadata["distance_from_prev_km"] = round(distance_from_prev, 2)
        previous_coord = current_coord or previous_coord

    # Xác định distance_source tổng hợp
    if not distance_sources:
        overall_source = "none"
    elif all(s == "google_maps" for s in distance_sources):
        overall_source = "google_maps"
    elif all(s == "haversine_road_estimate" for s in distance_sources):
        overall_source = "haversine_road_estimate"
    else:
        overall_source = "mixed"

    route_summary = {
        "estimated_km": round(total_km, 2),
        "optimizer": optimizer_name,
        "distance_source": overall_source,
    }

    logger.success(
        f"Route optimizer ordered {len(ordered_pois)} POIs | "
        f"km={route_summary['estimated_km']} | "
        f"distance_source={overall_source}"
    )
    return ordered_pois, route_summary


async def route_optimizer_node(state: AgentState) -> dict:
    """LangGraph node – delegates to the pure ``optimize_route`` function."""
    logger.info("Entering route_optimizer node")

    qdrant_results = state.get("qdrant_results", [])
    if not qdrant_results:
        logger.warning("No POIs received from qdrant_search")
        return {
            "validated_pois": [],
            "route_summary": {
                "estimated_km": 0.0,
                "optimizer": "none",
                "distance_source": "none",
            },
        }

    # Đọc optimize_route từ memory (default True nếu chưa có)
    memory = state.get("memory")
    should_optimize: bool = getattr(memory, "optimize_route", True) if memory else True
    logger.info(f"optimize_route={should_optimize}")

    ordered_pois, route_summary = await optimize_route(
        qdrant_results, should_optimize=should_optimize
    )
    return {"validated_pois": ordered_pois, "route_summary": route_summary}
