from typing import List, Optional
from sqlalchemy.orm import Session
from src.domain.entities import Item
from src.application.interfaces import ItemRepository
from src.infrastructure.models import ItemModel

class SQLAlchemyItemRepository(ItemRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, item: Item) -> Item:
        db_item = ItemModel(
            name=item.name,
            description=item.description,
            created_at=item.created_at
        )
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        item.id = db_item.id
        return item

    def get_by_id(self, item_id: int) -> Optional[Item]:
        db_item = self.db.query(ItemModel).filter(ItemModel.id == item_id).first()
        if not db_item:
            return None
        return Item(
            id=db_item.id,
            name=db_item.name,
            description=db_item.description,
            created_at=db_item.created_at
        )

    def get_all(self) -> List[Item]:
        db_items = self.db.query(ItemModel).all()
        return [
            Item(
                id=i.id,
                name=i.name,
                description=i.description,
                created_at=i.created_at
            ) for i in db_items
        ]
