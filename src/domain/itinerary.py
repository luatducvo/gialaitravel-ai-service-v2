from pydantic import BaseModel
from typing import List

class Activity(BaseModel):
    time_slot: str
    poi_id: str
    poi_name: str
    lat: float
    lng: float
    duration_minutes: int
    cost: float
    distance_from_prev_km: float
    travel_from_previous_minutes: int = 0
    intensity_level: str
    note: str

class DayPlan(BaseModel):
    day: int
    title: str
    total_km: float
    activities: List[Activity]

class Itinerary(BaseModel):
    overview: str = ""
    days: List[DayPlan]
    total_cost: float
    total_km: float
