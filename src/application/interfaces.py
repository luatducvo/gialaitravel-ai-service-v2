from abc import ABC, abstractmethod
from typing import List, Optional
from src.domain.entities import Item

class ItemRepository(ABC):
    @abstractmethod
    def create(self, item: Item) -> Item:
        pass

    @abstractmethod
    def get_by_id(self, item_id: int) -> Optional[Item]:
        pass

    @abstractmethod
    def get_all(self) -> List[Item]:
        pass

class VectorStoreRepository(ABC):
    @abstractmethod
    def upsert_documents(self, documents: List[str], metadatas: List[dict]):
        pass

    @abstractmethod
    def similarity_search(self, query: str, k: int = 4) -> List[dict]:
        pass
