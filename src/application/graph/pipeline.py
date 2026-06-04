"""
LangGraph pipeline: định nghĩa và khởi chạy workflow lập kế hoạch du lịch Gia Lai.

Workflow được xây dựng dưới dạng ``StateGraph[AgentState]`` với entry-point
có điều kiện (``router_node``) và bốn pha chính:

1. **cold_start** – Thu thập thông tin cơ bản (duration, group, transport).
   - Kết thúc → ``elicit`` hoặc ``END``.

2. **elicit** – Hỏi người dùng về "vibe" chuyến đi (mong muốn, phong cách).
   - Kết thúc → ``qdrant_search`` hoặc ``END``.

3. **plan** (pipeline nối tiếp):
   ``qdrant_search`` → ``route_optimizer`` → ``llm_planner`` → ``END``

   - ``qdrant_search``: Tìm kiếm POI phù hợp từ Qdrant theo vibe & bộ lọc.
   - ``route_optimizer``: Sắp xếp POI theo thuật toán nearest-neighbor,
     tính chi phí và khoảng cách ước tính.
   - ``llm_planner``: Gọi LLM để sinh ``Itinerary`` có cấu trúc.

4. **refine** (critic):
   - Xử lý confirm / refine / câu hỏi realtime / phản hồi điều chỉnh.
   - Kết thúc → ``qdrant_search`` (tạo lại) hoặc ``finalized`` hoặc ``END``.

5. **finalized** – Gửi lịch trình đã xác nhận về client.

Functions:
    create_workflow: Tạo và compile ``StateGraph``.
    run_pipeline: Hàm async entry-point được trace bởi LangSmith;
        áp dụng guardrail trước khi invoke graph.
"""

from langgraph.graph import StateGraph, END
from src.application.graph.state import AgentState
from src.application.graph.nodes.router import router_node
from src.application.graph.nodes.cold_start import cold_start_node
from src.application.graph.nodes.elicitation import elicitation_node
from src.application.graph.nodes.qdrant_search import qdrant_search_node
from src.application.graph.nodes.route_optimizer import route_optimizer_node
from src.application.graph.nodes.llm_planner import llm_planner_node
from src.application.graph.nodes.critic import critic_node
from src.application.graph.nodes.finalize import finalize_node
from src.application.guardrails import check_user_message_scope
from loguru import logger
from langsmith import traceable

def create_workflow():
    """Xây dựng và compile LangGraph ``StateGraph`` cho toàn bộ pipeline.

    Các node được đăng ký:
        - ``cold_start``     : Thu thập duration / group / transport.
        - ``elicit``         : Thu thập vibe_query.
        - ``qdrant_search``  : Tìm kiếm POI từ Qdrant.
        - ``route_optimizer``: Tối ưu thứ tự POI và tính chi phí / khoảng cách.
        - ``llm_planner``    : Sinh itinerary bằng LLM.
        - ``critic``         : Xử lý phản hồi, realtime search, confirm/refine.
        - ``finalized``      : Phát lịch trình đã xác nhận về client.

    Conditional edges:
        - ``router_node`` tại entry-point phân luồng dựa trên ``memory.current_step``.
        - ``cold_start`` → ``elicit`` nếu step == "elicit", ngược lại ``END``.
        - ``elicit``     → ``qdrant_search`` nếu step == "plan", ngược lại ``END``.
        - ``critic``     → ``qdrant_search`` | ``finalized`` | ``END``.

    Returns:
        CompiledGraph: Graph đã compile, sẵn sàng gọi ``ainvoke``.
    """
    workflow = StateGraph(AgentState)
    
    workflow.add_node("cold_start", cold_start_node)
    workflow.add_node("elicit", elicitation_node)
    workflow.add_node("qdrant_search", qdrant_search_node)
    workflow.add_node("route_optimizer", route_optimizer_node)
    workflow.add_node("llm_planner", llm_planner_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("finalized", finalize_node)
    
    workflow.set_conditional_entry_point(
        router_node,
        {
            "cold_start": "cold_start",
            "elicit": "elicit",
            "plan": "qdrant_search",
            "refine": "critic",
            "finalized": "finalized"
        }
    )
    
    def cold_start_condition(state: AgentState):
        if state["memory"].current_step == "elicit":
            return "elicit"
        return END
        
    workflow.add_conditional_edges("cold_start", cold_start_condition)
    
    def elicit_condition(state: AgentState):
        if state["memory"].current_step == "plan":
            return "qdrant_search"
        return END
        
    workflow.add_conditional_edges("elicit", elicit_condition)
    
    # Planner chain
    workflow.add_edge("qdrant_search", "route_optimizer")
    workflow.add_edge("route_optimizer", "llm_planner")
    workflow.add_edge("llm_planner", END)
    
    def critic_condition(state: AgentState):
        if state["memory"].current_step == "plan":
            return "qdrant_search"
        if state["memory"].current_step == "finalized":
            return "finalized"
        return END
        
    workflow.add_conditional_edges("critic", critic_condition)
    
    workflow.add_edge("finalized", END)
    
    return workflow.compile()

@traceable(name="planner_pipeline")
async def run_pipeline(session_id: str, message: str, memory, payload: dict | None = None):
    """Điểm vào async chính của AI pipeline, được trace bởi LangSmith.

    Thực hiện theo thứ tự:
    1. Gọi ``check_user_message_scope`` để kiểm tra guardrail. Nếu bị chặn,
       trả về ngay ``ws_responses`` với type ``"guardrail"`` mà không invoke graph.
    2. Compile workflow qua ``create_workflow()``.
    3. Invoke graph với ``initial_state`` và trả về ``final_state``.

    Args:
        session_id (str): Định danh phiên làm việc – dùng để ghi log.
        message (str): Tin nhắn của người dùng trong lượt hiện tại.
        memory (WorkingMemory): Bộ nhớ làm việc đã được load từ session store.
        payload (dict | None): Dữ liệu JSON bổ sung từ client (cold-start form,
            thông tin kỹ thuật…). Mặc định ``None`` (sẽ thành ``{}``).

    Returns:
        dict: ``final_state`` sau khi graph xử lý xong, hoặc dict chứa
        ``ws_responses`` với guardrail message nếu tin nhắn bị chặn.
    """
    has_itinerary = bool(memory.current_itinerary)
    guardrail = check_user_message_scope(
        message,
        current_step=memory.current_step,
        has_itinerary=has_itinerary,
    )
    if not guardrail.allowed:
        logger.warning(f"Blocked user message by guardrail: {guardrail.reason}")
        return {
            "memory": memory,
            "user_message": "",
            "ws_responses": [{
                "type": "guardrail",
                "step": memory.current_step,
                "agent_message": guardrail.message,
                "reason": guardrail.reason,
            }],
        }

    graph = create_workflow()
    initial_state = {
        "memory": memory,
        "user_message": message,
        "user_payload": payload or {},
        "ws_responses": []
    }
    logger.info(f"Invoking graph for session {session_id}")
    final_state = await graph.ainvoke(initial_state)
    return final_state
