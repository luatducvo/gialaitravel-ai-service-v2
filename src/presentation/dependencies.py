from fastapi import Depends
from src.application.services.itinerary_service import CustomItineraryService

def get_custom_itinerary_service() -> CustomItineraryService:
    return CustomItineraryService()
