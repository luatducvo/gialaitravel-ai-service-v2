import uvicorn
from dotenv import load_dotenv
# Bắt buộc load đè file .env vào os.environ để LangChain nhận diện được
load_dotenv(override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.core.config import settings
from src.presentation.ws import chat
from src.presentation.api import itineraries
from src.core.logging import setup_logging

app = FastAPI(title=settings.PROJECT_NAME)

# Cho phép backend NestJS (AgentProxyGateway) mở WebSocket proxy tới service này
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production: giới hạn về AGENT_SERVICE_URL của backend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    setup_logging()

app.include_router(chat.router)
app.include_router(itineraries.router)

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
