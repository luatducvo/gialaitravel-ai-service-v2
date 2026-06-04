"""
Node finalize: Phát lịch trình đã được xác nhận về WebSocket client.

Đây là node cuối cùng trong pipeline, được kích hoạt khi ``memory.current_step``
chuyển sang ``"finalized"`` (sau khi người dùng xác nhận qua critic_node).

Node chỉ có một nhiệm vụ: đóng gói ``memory.current_itinerary`` vào
``ws_response`` type ``"finalized"`` và trả về để stream về client.
Không có logic phức tạp – toàn bộ xử lý đã hoàn tất ở các node trước.
"""

from loguru import logger

from src.application.graph.state import AgentState


def finalize_node(state: AgentState) -> dict:
    """LangGraph node – gửi lịch trình đã xác nhận về client.

    Args:
        state (AgentState): State hiện tại của LangGraph.

    Returns:
        dict: Partial state update với ``ws_responses`` chứa một message
        type ``"finalized"`` kèm toàn bộ itinerary, và ``memory`` không đổi.
    """
    memory = state["memory"]
    logger.info("Entering finalize node")

    ws_response = {
        "type": "finalized",
        "step": "finalized",
        "agent_message": "Lịch trình đã được xác nhận. Chúc bạn có chuyến đi tuyệt vời ở Gia Lai.",
        "itinerary": memory.current_itinerary,
    }

    return {"ws_responses": [ws_response], "memory": memory}
