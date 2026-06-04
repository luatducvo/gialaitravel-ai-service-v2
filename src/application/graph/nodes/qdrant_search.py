"""
Node qdrant_search: Tìm kiếm POI từ Qdrant phù hợp với vibe và profile người dùng.

Đây là bước đầu tiên trong pipeline plan (qdrant_search → route_optimizer → llm_planner).
Node thực hiện hai lần tìm kiếm song song trên collection Qdrant:

- **vibe_poi** (k=10): Các địa điểm phù hợp với phong cách / trải nghiệm mong muốn.
- **logistics_poi** (k=10): Các địa điểm hạ tầng (nhà hàng, khách sạn, trạm xăng…).

Kết quả được merge và dedup theo ``poi_id`` (POI trùng lặp chỉ giữ lần đầu).
Bộ lọc Qdrant được xây dựng qua ``build_qdrant_filter`` – đảm bảo POI phù hợp với
``intensity_level``, ``transport_compatibility`` và ``suitable_for`` của chuyến đi.

Node bị bỏ qua (trả về ``{}``) nếu itinerary đã tồn tại và không ở bước ``"plan"``.
"""

from src.application.graph.state import AgentState
from qdrant_client import QdrantClient
from src.infrastructure.qdrant_repo import QdrantRepository
from src.core.config import settings
from loguru import logger

def build_qdrant_filter(memory, aspect: str) -> dict:
    """Xây dựng Qdrant filter dict dựa trên profile chuyến đi.

    Args:
        memory (WorkingMemory): Bộ nhớ làm việc chứa group, transport,
            intensity_filter.
        aspect (str): Loại POI cần tìm kiếm, ví dụ ``"vibe_poi"`` hoặc
            ``"logistics_poi"``.

    Returns:
        dict: Qdrant filter theo cú pháp ``{"must": [...]}`` với các điều kiện:
            - ``aspect``: khớp chính xác với tham số ``aspect``.
            - ``intensity_level``: khớp một trong các giá trị ``intensity_filter``.
            - ``transport_compatibility``: khớp ``memory.transport`` (nếu có).
            - ``suitable_for``: khớp ``memory.group`` (nếu có).
    """
    intensity_filter = memory.intensity_filter or (
        ["low"] if memory.group in ["family", "elderly"] else ["low", "medium", "high"]
    )
    must = [{"key": "aspect", "match": {"value": aspect}}]
    if intensity_filter:
        must.append({"key": "intensity_level", "match": {"any": intensity_filter}})
    if memory.transport:
        must.append({"key": "transport_compatibility", "match": {"any": [memory.transport]}})
    if memory.group:
        must.append({"key": "suitable_for", "match": {"any": [memory.group]}})
    return {"must": must}

def qdrant_search_node(state: AgentState) -> dict:
    """LangGraph node – tìm kiếm POI từ Qdrant.

    Args:
        state (AgentState): State hiện tại của LangGraph.

    Returns:
        dict: ``{"qdrant_results": List[Dict]}`` chứa các POI đã dedup,
        hoặc ``{}`` nếu itinerary đã tồn tại và không ở bước plan,
        hoặc ``{"qdrant_results": []}`` nếu gặp lỗi kết nối Qdrant.
    """
    memory = state["memory"]
    logger.info("Entering qdrant_search node")
    
    # If we already have a finalized itinerary or if we are not generating one, skip search
    if memory.current_itinerary and memory.current_step != "plan":
        return {}
        
    try:
        qdrant_client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        repo = QdrantRepository(client=qdrant_client)
        
        vibe_results = repo.filtered_search(
            query=memory.vibe_query, 
            filter_dict=build_qdrant_filter(memory, "vibe_poi"), 
            k=10
        )
        logistics_results = repo.filtered_search(
            query=memory.vibe_query, 
            filter_dict=build_qdrant_filter(memory, "logistics_poi"), 
            k=10
        )
        
        seen_pois = set()
        merged_results = []
        for res in vibe_results + logistics_results:
            poi_id = res["metadata"].get("poi_id")
            if poi_id and poi_id not in seen_pois:
                seen_pois.add(poi_id)
                merged_results.append(res)
                
        logger.success(f"Qdrant search found {len(merged_results)} unique POIs")
        return {"qdrant_results": merged_results}
        
    except Exception as e:
        logger.error(f"Error in qdrant_search: {e}")
        return {"qdrant_results": []}
