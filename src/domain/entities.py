from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class Item:
    id: Optional[int]
    name: str
    description: Optional[str]
    created_at: datetime
