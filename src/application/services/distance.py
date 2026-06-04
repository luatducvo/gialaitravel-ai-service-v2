import math

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate the great circle distance between two points on the earth."""
    R = 6371  # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def road_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Estimate actual road distance based on mountain terrain factor."""
    return haversine_km(lat1, lng1, lat2, lng2) * 1.4  # Mountain road factor
