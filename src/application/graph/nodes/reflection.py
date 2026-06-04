"""
Node reflection: Phiên bản cũ (legacy) của pha refine/critic.

.. deprecated::
    Node này đã được thay thế hoàn toàn bởi ``critic_node``
    (``src/application/graph/nodes/critic.py``).
    ``critic_node`` bổ sung:
    - Realtime search (Tavily) cho câu hỏi sự kiện, review, chi tiết POI.
    - Phân loại ``reason_tag`` cho feedback điều chỉnh lịch trình.
    - Fuzzy matching tên POI trong itinerary.

    File này được giữ lại để tham khảo lịch sử. **Không sử dụng trong pipeline.**
"""

from loguru import logger

from src.application.graph.state import AgentState


def reflection_node(state: AgentState) -> dict:
    """Legacy node – xử lý confirm/refine/feedback (đã thay thế bởi critic_node).

    .. deprecated::
        Dùng ``critic_node`` thay thế. Node này không được đăng ký trong
        ``pipeline.py`` và sẽ không được gọi trong pipeline hiện tại.

    Args:
        state (AgentState): State hiện tại của LangGraph.

    Returns:
        dict: Partial state update tương tự critic_node nhưng không có
        realtime search và phân loại reason_tag.
    """
    memory = state["memory"]
    user_msg = state.get("user_message", "")
    logger.info("Entering reflection node")

    if user_msg == "confirm":
        logger.success("User confirmed the itinerary!")
        memory.current_step = "finalized"
        return {"memory": memory, "user_message": ""}
    elif user_msg == "refine":
        return {
            "ws_responses": [{
                "type": "refinement_options",
                "step": "refine",
                "agent_message": "Bạn muốn điều chỉnh phần nào của lịch trình?",
                "ui_chips": [
                    {"label": "Thay đổi điểm đến", "value": "change_poi"},
                    {"label": "Giảm thời gian di chuyển", "value": "reduce_travel"},
                    {"label": "Khác", "value": "custom"},
                ],
            }],
            "memory": memory,
            "user_message": "",
        }
    elif user_msg:
        logger.info(f"Received refinement feedback: {user_msg}")
        memory.learned_constraints.append(user_msg)
        memory.current_step = "plan"
        memory.current_itinerary = None
        return {"memory": memory, "user_message": ""}

    return {"memory": memory}
