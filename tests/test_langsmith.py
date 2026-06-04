import os
from langsmith import Client
from dotenv import load_dotenv

load_dotenv()

def check_langsmith():
    print("Checking LangSmith connection...")
    try:
        # Client will automatically pick up LANGSMITH_API_KEY, LANGCHAIN_ENDPOINT, etc. from .env
        client = Client()
        projects = list(client.list_projects())
        print("✅ LangSmith connection SUCCESSFUL!")
        print(f"Found {len(projects)} projects in your LangSmith account:")
        for p in projects:
            print(f"  - {p.name}")
    except Exception as e:
        print(f"❌ LangSmith connection FAILED: {e}")

if __name__ == "__main__":
    check_langsmith()
