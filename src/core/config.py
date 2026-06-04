from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "gialaitravel-ai-service-v2"

    
    # LLM Provider Configuration (openai, gemini, deepseek)
    LLM_PROVIDER: str
    
    # API Keys
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    
    # Models
    OPENAI_MODEL: Optional[str] = None
    GEMINI_MODEL: Optional[str] = None
    DEEPSEEK_MODEL: Optional[str] = None
    
    # Qdrant VectorDB
    QDRANT_URL: str
    QDRANT_API_KEY: str
    EMBEDDING_MODEL: str = "models/gemini-embedding-2"
    QDRANT_COLLECTION_NAME: str = "gialai-data"

    # External enrichment APIs
    TAVILY_API_KEY: Optional[str] = None
    TAVILY_TIMEOUT_SECONDS: float = 15.0
    TAVILY_MAX_RETRIES: int = 2
    GOOGLE_MAPS_API_KEY: Optional[str] = None

    # LangSmith Observability
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: Optional[str] = None
    LANGCHAIN_TRACING_V2: Optional[str] = None
    LANGCHAIN_ENDPOINT: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
