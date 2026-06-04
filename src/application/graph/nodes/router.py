"""
Node router: Entry-point có điều kiện của LangGraph pipeline.

Node này không thay đổi state mà chỉ đọc ``memory`` để quyết định node
tiếp theo. ``detect_step`` (từ ``working_memory``) phân tích trạng thái
hiện tại và trả về một trong các key:

- ``"cold_start"``  – Chưa có duration / group / transport.
- ``"elicit"``      – Đã có thông tin cơ bản, chưa có vibe_query.
- ``"plan"``        – Đã đủ thông tin, cần tạo / tạo lại itinerary.
- ``"refine"``      – Itinerary đang chờ xác nhận / điều chỉnh từ người dùng.
- ``"finalized"``   – Người dùng đã xác nhận itinerary.

Giá trị trả về được dùng trực tiếp như conditional edge key trong
``workflow.set_conditional_entry_point()``.
"""

from loguru import logger

from src.application.graph.state import AgentState
from src.domain.working_memory import detect_step


def router_node(state: AgentState) -> str:
    """LangGraph conditional entry-point – xác định node cần chạy tiếp theo.

    Args:
        state (AgentState): State hiện tại của LangGraph.

    Returns:
        str: Key định danh node tiếp theo, một trong:
        ``"cold_start"``, ``"elicit"``, ``"plan"``, ``"refine"``, ``"finalized"``.
    """
    memory = state["memory"]
    step = detect_step(memory)
    logger.info(f"Router detected step: {step}")
    return step
