from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, MatchAny
from langchain_qdrant import QdrantVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from src.application.interfaces import VectorStoreRepository
from src.core.config import settings

def get_embeddings():
    return GoogleGenerativeAIEmbeddings(model=settings.EMBEDDING_MODEL, google_api_key=settings.GEMINI_API_KEY or "dummy_key")

class QdrantRepository(VectorStoreRepository):
    def __init__(self, client: QdrantClient):
        self.client = client
        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self.embeddings = get_embeddings()
        
        # Ensure collection exists
        try:
            self.client.get_collection(self.collection_name)
        except Exception:
            from qdrant_client.http.models import Distance, VectorParams
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
            )
            
        # Ensure payload indexes exist for metadata filtering
        from qdrant_client.http.models import PayloadSchemaType
        for field in ["aspect", "intensity_level", "transport_compatibility", "suitable_for"]:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass
            
        self.vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            embedding=self.embeddings,
            content_payload_key="text",
            metadata_payload_key="", # Bắt Langchain lấy toàn bộ flat payload làm metadata
        )

    def upsert_documents(self, documents: List[str], metadatas: List[dict]):
        self.vector_store.add_texts(texts=documents, metadatas=metadatas)

    def similarity_search(self, query: str, k: int = 4) -> List[dict]:
        return self._search(query=query, qdrant_filter=None, k=k)
        
    def filtered_search(self, query: str, filter_dict: Dict[str, Any], k: int = 4) -> List[dict]:
        must_conditions = []
        if "must" in filter_dict:
            for condition in filter_dict["must"]:
                key = condition["key"]
                match = condition["match"]
                if "value" in match:
                    must_conditions.append(FieldCondition(key=key, match=MatchValue(value=match["value"])))
                elif "any" in match:
                    must_conditions.append(FieldCondition(key=key, match=MatchAny(any=match["any"])))
        
        qdrant_filter = Filter(must=must_conditions) if must_conditions else None
        return self._search(query=query, qdrant_filter=qdrant_filter, k=k)

    def _search(self, query: str, qdrant_filter: Optional[Filter], k: int) -> List[dict]:
        safe_query = query if query and query.strip() else "Gia Lai"
        query_vector = self.embeddings.embed_query(safe_query)

        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=qdrant_filter,
                limit=k,
                with_payload=True,
                with_vectors=False,
            )
            points = response.points
        else:
            points = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=qdrant_filter,
                limit=k,
                with_payload=True,
                with_vectors=False,
            )

        return [self._point_to_result(point) for point in points]

    @staticmethod
    def _point_to_result(point: Any) -> dict:
        payload = point.payload or {}
        return {
            "page_content": payload.get("text", ""),
            "metadata": payload,
            "score": point.score,
        }
