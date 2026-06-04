from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from src.infrastructure.session_store import get_session, save_session
from src.application.graph.pipeline import run_pipeline
import json

router = APIRouter(prefix="/ws", tags=["websocket"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_json(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

manager = ConnectionManager()

@router.websocket("/chat")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await manager.connect(websocket)
    logger.info(f"WebSocket connected: session_id={session_id}")
    
    try:
        # Load memory
        memory = get_session(session_id)
        
        # Nếu chưa có thông tin chuyến đi, tự động trigger pipeline 1 lần để nhả Form
        if not memory.duration and memory.current_step == "cold_start":
            final_state = await run_pipeline(session_id, "", memory)
            save_session(final_state["memory"])
            for resp in final_state.get("ws_responses", []):
                await manager.send_json(resp, websocket)
                
        while True:
            data = await websocket.receive_text()
            try:
                input_data = json.loads(data)
                payload = input_data.get("payload", {})
                user_message = payload.get("chip_value") or payload.get("message", "")

                # Load memory
                memory = get_session(session_id)

                # Run graph
                final_state = await run_pipeline(session_id, user_message, memory, payload=payload)

                # Save memory
                save_session(final_state["memory"])

                # Send back responses
                for resp in final_state.get("ws_responses", []):
                    await manager.send_json(resp, websocket)

            except json.JSONDecodeError:
                logger.error("Invalid JSON received")
                await manager.send_json(
                    {
                        "type": "error",
                        "agent_message": "Dữ liệu gửi lên không hợp lệ. Vui lòng thử lại.",
                    },
                    websocket,
                )
            except Exception as e:
                logger.exception(f"Unhandled error processing message for session {session_id}: {e}")
                try:
                    await manager.send_json(
                        {
                            "type": "error",
                            "agent_message": (
                                "Mình gặp sự cố khi xử lý yêu cầu của bạn. "
                                "Vui lòng thử lại sau ít giây nhé 🙏"
                            ),
                        },
                        websocket,
                    )
                except Exception:
                    pass  # WebSocket may already be closed
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"WebSocket disconnected: session_id={session_id}")
