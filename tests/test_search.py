import os
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, MatchAny
from src.infrastructure.qdrant_repo import QdrantRepository
from src.domain.working_memory import WorkingMemory
from dotenv import load_dotenv

load_dotenv(override=True)

qdrant_client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
repo = QdrantRepository(client=qdrant_client)

memory = WorkingMemory(
    session_id="test",
    duration="3d2n",
    group="couple",
    transport="motorbike"
)
memory.intensity_filter = ["low", "medium", "high"]

print("Attempting unfiltered search...")
results = repo.similarity_search("thác nước", k=2)
print("Unfiltered results:", results)

print("\nAttempting filtered search...")
must = [
    {"key": "aspect", "match": {"value": "vibe_poi"}},
    {"key": "transport_compatibility", "match": {"any": ["motorbike"]}},
]
results2 = repo.filtered_search("thác nước", {"must": must}, k=2)
print("Filtered results:", results2)
