"""
Node planner: Phiên bản cũ (legacy) của pha plan.

.. deprecated::
    Node này đã được thay thế bởi pipeline ba bước:
    ``qdrant_search_node`` → ``route_optimizer_node`` → ``llm_planner_node``.

    Pipeline mới tách bạch rõ ràng trách nhiệm:
    - Qdrant search: chỉ tìm kiếm POI, không gọi LLM.
    - Route optimizer: tối ưu thứ tự + tính chi phí / quãng đường.
    - LLM planner: chỉ sinh ngôn ngữ tự nhiên từ dữ liệu đã xử lý.

    File này được giữ lại để tham khảo. **Không sử dụng trong pipeline hiện tại.**
"""

from src.application.graph.state import AgentState
from qdrant_client import QdrantClient
from src.infrastructure.qdrant_repo import QdrantRepository
from src.core.config import settings
from src.domain.itinerary import Itinerary
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger

def build_qdrant_filter(memory, aspect: str) -> dict:
    """Xây dựng Qdrant filter dict dựa trên profile chuyến đi (legacy).

    .. deprecated::
        Dùng ``build_qdrant_filter`` trong ``qdrant_search.py`` thay thế.

    Args:
        memory (WorkingMemory): Bộ nhớ làm việc chứa group, transport,
            intensity_filter.
        aspect (str): Loại POI, ví dụ ``"vibe_poi"`` hoặc ``"logistics_poi"``.

    Returns:
        dict: Qdrant filter theo cú pháp ``{"must": [...]}``.
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

def get_llm():
    """Khởi tạo LLM client dựa trên ``settings.LLM_PROVIDER`` (legacy).

    .. deprecated::
        Dùng ``get_llm`` trong ``llm_planner.py`` thay thế.

    Returns:
        BaseChatModel: Instance của LLM client đã cấu hình.
    """
    provider = settings.LLM_PROVIDER.lower()
    if provider == "gemini":
        return ChatGoogleGenerativeAI(model=settings.GEMINI_MODEL, google_api_key=settings.GEMINI_API_KEY, temperature=0.2)
    elif provider == "deepseek":
        return ChatOpenAI(
            model=settings.DEEPSEEK_MODEL, 
            api_key=settings.DEEPSEEK_API_KEY, 
            base_url="https://api.deepseek.com", 
            temperature=0.2
        )
    else:
        return ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0.2)

def planner_node(state: AgentState) -> dict:
    """Legacy node – tìm kiếm POI và sinh itinerary trong một bước (đã thay thế).

    .. deprecated::
        Thay bằng pipeline: ``qdrant_search_node`` → ``route_optimizer_node``
        → ``llm_planner_node``. Node này không được đăng ký trong ``pipeline.py``.

    Args:
        state (AgentState): State hiện tại của LangGraph.

    Returns:
        dict: Partial state update với ``memory`` (itinerary) và ``ws_responses``.
    """
    memory = state["memory"]
    logger.info("Entering planner node")
    
    if not memory.current_itinerary:
        try:
            qdrant_client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
            repo = QdrantRepository(client=qdrant_client)
            
            vibe_results = repo.filtered_search(
                query=memory.vibe_query, 
                filter_dict=build_qdrant_filter(memory, "vibe_poi"), 
                k=5
            )
            logistics_results = repo.filtered_search(
                query=memory.vibe_query, 
                filter_dict=build_qdrant_filter(memory, "logistics_poi"), 
                k=5
            )
            
            seen_pois = set()
            merged_results = []
            for res in vibe_results + logistics_results:
                poi_id = res["metadata"].get("poi_id")
                if poi_id and poi_id not in seen_pois:
                    seen_pois.add(poi_id)
                    merged_results.append(res)
                    
            context_str = "\n".join([f"- {res['metadata'].get('poi_name', 'Unknown')}: {res['page_content']} (Cost: {res['metadata'].get('cost', 0)})" for res in merged_results])
            
            llm = get_llm()
            structured_llm = llm.with_structured_output(Itinerary)
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", "Bạn là một chuyên gia du lịch Gia Lai. Hãy tạo lịch trình {duration} cho nhóm {group} di chuyển bằng {transport}."),
                ("user", "Yêu cầu: {vibe}\n\nDữ liệu POI gợi ý:\n{context}\n\nCác lưu ý đã học được: {constraints}")
            ])
            
            chain = prompt | structured_llm
            itinerary = chain.invoke({
                "duration": memory.duration,
                "group": memory.group,
                "transport": memory.transport,
                "vibe": memory.vibe_query,
                "context": context_str,
                "constraints": ", ".join(memory.learned_constraints) if memory.learned_constraints else "Không có"
            })
            memory.current_itinerary = itinerary.model_dump()
            logger.success("Planner generated itinerary successfully")
            
        except Exception as e:
            logger.error(f"Error generating itinerary: {e}")
            memory.current_itinerary = {"error": "Could not generate itinerary"}

    ws_response = {
        "type": "itinerary",
        "step": "plan",
        "agent_message": "Đây là lịch trình mình đã thiết kế cho bạn.",
        "itinerary": memory.current_itinerary,
        "ui_chips": [
            {"label": "Hài lòng, xác nhận lịch trình", "value": "confirm"},
            {"label": "Cần điều chỉnh", "value": "refine"}
        ]
    }
    
    memory.current_step = "refine"
    return {"memory": memory, "ws_responses": [ws_response]}
