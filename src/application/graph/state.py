"""
Định nghĩa schema trạng thái chia sẻ của LangGraph pipeline.

Module này khai báo ``AgentState`` – TypedDict duy nhất được truyền xuyên suốt
tất cả các node trong StateGraph. Mỗi node đọc từ state và trả về một dict
chứa các key cần cập nhật; LangGraph tự merge kết quả đó vào state hiện tại.
"""

from typing import TypedDict, Annotated, List, Dict, Any
from src.domain.working_memory import WorkingMemory
import operator


class AgentState(TypedDict, total=False):
    """Trạng thái chia sẻ xuyên suốt toàn bộ LangGraph pipeline.

    Các trường được chia thành hai nhóm:

    **Trường bền vững (persistent):**
        Tồn tại trong suốt phiên làm việc và được lưu vào session store.

        memory (WorkingMemory):
            Bộ nhớ làm việc của agent – chứa thông tin chuyến đi (duration,
            group, transport, vibe_query), itinerary hiện tại, bước hiện tại
            (current_step) và danh sách ràng buộc đã học.

        ws_responses (List[Dict[str, Any]]):
            Danh sách các message sẽ được stream về WebSocket client.
            Sử dụng ``operator.add`` để các node có thể append mà không ghi đè.

        user_message (str):
            Tin nhắn gốc của người dùng trong lượt hiện tại.

        user_payload (Dict[str, Any]):
            Dữ liệu JSON bổ sung từ client (ví dụ: thông tin form cold-start
            được gửi kèm theo message đầu tiên).

    **Trường tạm thời của pipeline (transients):**
        Chỉ tồn tại trong một lượt xử lý, không cần lưu lâu dài.

        qdrant_results (List[Dict[str, Any]]):
            Danh sách POI thô trả về từ ``qdrant_search_node`` trước khi
            được tối ưu hoá thứ tự.

        validated_pois (List[Dict[str, Any]]):
            Danh sách POI sau khi ``route_optimizer_node`` đã sắp xếp theo
            thuật toán nearest-neighbor và gắn thêm metadata
            ``route_order`` / ``distance_from_prev_km``.

        route_summary (Dict[str, Any]):
            Thông tin tóm tắt tuyến đường do ``route_optimizer_node`` tính:
            ``estimated_cost``, ``estimated_km``, ``optimizer``.

        critic_feedback (Dict[str, Any]):
            Phản hồi từ ``critic_node`` khi người dùng từ chối lịch trình,
            chứa ``event``, ``reason_tag`` và ``rejected_segment`` để
            ``llm_planner_node`` điều chỉnh lần tạo tiếp theo.
    """

    memory: WorkingMemory
    ws_responses: Annotated[List[Dict[str, Any]], operator.add]
    user_message: str
    user_payload: Dict[str, Any]

    # Pipeline transients
    qdrant_results: List[Dict[str, Any]]
    validated_pois: List[Dict[str, Any]]
    route_summary: Dict[str, Any]
    critic_feedback: Dict[str, Any]
