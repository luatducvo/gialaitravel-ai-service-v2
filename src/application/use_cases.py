from typing import List
from src.domain.entities import Item
from src.application.interfaces import ItemRepository
from datetime import datetime

class ItemService:
    def __init__(self, repository: ItemRepository):
        self.repository = repository

    def create_item(self, name: str, description: str = None) -> Item:
        item = Item(
            id=None,
            name=name,
            description=description,
            created_at=datetime.utcnow()
        )
        return self.repository.create(item)

    def get_item(self, item_id: int) -> Item:
        item = self.repository.get_by_id(item_id)
        if not item:
            raise ValueError(f"Item {item_id} not found")
        return item

    def list_items(self) -> List[Item]:
        return self.repository.get_all()
