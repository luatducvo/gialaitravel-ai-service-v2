import os
from qdrant_client import QdrantClient
from dotenv import load_dotenv

load_dotenv()

client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))

try:
    info = client.get_collection(os.getenv("QDRANT_COLLECTION_NAME"))
    print(f"Collection '{os.getenv('QDRANT_COLLECTION_NAME')}' exists with {info.points_count} points.")
    
    # Let's inspect one point to see its metadata format
    points = client.scroll(
        collection_name=os.getenv("QDRANT_COLLECTION_NAME"),
        limit=1
    )
    if points[0]:
        print("\nSample Point Metadata:")
        print(points[0][0].payload)
except Exception as e:
    print(f"Error accessing collection: {e}")
