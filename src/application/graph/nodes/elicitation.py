"""
Node elicitation: Thu thập "vibe" – mong muốn và phong cách chuyến đi.

Node này được gọi sau khi ``cold_start`` đã thu thập đủ duration/group/transport.
Mục tiêu là lấy ``vibe_query`` từ người dùng – một câu mô tả tự do về trải nghiệm
họ muốn (ví dụ: "thiên nhiên, thác nước", "văn hóa bản địa Jrai").

Luồng xử lý:
    - Nếu ``memory.vibe_query`` đã có (resume session): bỏ qua, trả về memory.
    - Nếu ``user_message`` không rỗng: lưu làm ``vibe_query``,
      chuyển ``current_step`` sang ``"plan"``.
    - Nếu chưa có message: trả về ``ws_response`` type ``"elicitation_question"``
      kèm ba UI chips gợi ý và ``allow_free_text=True`` để người dùng nhập tự do.
"""

from loguru import logger

from src.application.graph.state import AgentState


def elicitation_node(state: AgentState) -> dict:
    """LangGraph node – thu thập vibe_query từ người dùng.

    Args:
        state (AgentState): State hiện tại của LangGraph.

    Returns:
        dict: Partial state update.

        - Nếu nhận được message: ``memory`` với ``vibe_query`` và
          ``current_step="plan"``, ``user_message=""`` (đã tiêu thụ).
        - Nếu chưa có message: ``ws_responses`` chứa elicitation question
          kèm UI chips gợi ý, ``memory`` và ``user_message`` không thay đổi.
        - Nếu ``vibe_query`` đã có: chỉ trả về ``memory`` (no-op).
    """
    memory = state["memory"]
    user_msg = state.get("user_message", "")
    logger.info("Entering elicitation node")

    if not memory.vibe_query:
        if user_msg:
            memory.vibe_query = user_msg
            logger.success(f"Elicitation: collected vibe_query={user_msg}")
            memory.current_step = "plan"
            return {"memory": memory, "user_message": ""}

        return {
            "ws_responses": [
                {
                    "type": "elicitation_question",
                    "step": "elicit",
                    "ui_chips": [
                        {
                            "label": "Thiên nhiên, thác nước, trekking nhẹ",
                            "value": (
                                "Mình muốn một lịch trình thiên nhiên, có thác nước, "
                                "rừng và trekking nhẹ."
                            ),
                        },
                        {
                            "label": "Đi thong thả, ngắm cảnh, chụp ảnh",
                            "value": (
                                "Mình muốn đi thong thả, ưu tiên hồ, chùa, cảnh đẹp "
                                "và các điểm dễ chụp ảnh."
                            ),
                        },
                        {
                            "label": "Văn hóa bản địa và ẩm thực",
                            "value": (
                                "Mình muốn khám phá văn hóa bản địa Jrai, thử món "
                                "địa phương và các trải nghiệm đời sống."
                            ),
                        },
                    ],
                    "allow_free_text": True,
                }
            ],
            "memory": memory,
            "user_message": user_msg,
        }

    return {"memory": memory}
