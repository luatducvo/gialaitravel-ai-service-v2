import os
from qdrant_client import QdrantClient

client = QdrantClient(location=":memory:")
with open("qdrant_methods.txt", "w") as f:
    f.write("\n".join(dir(client)))
