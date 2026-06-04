from qdrant_client import QdrantClient
from src.core.config import settings

def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
