from typing import Dict
from src.domain.working_memory import WorkingMemory

# Simple in-memory session store
# For production, use Redis
_sessions: Dict[str, WorkingMemory] = {}

def get_session(session_id: str) -> WorkingMemory:
    if session_id not in _sessions:
        _sessions[session_id] = WorkingMemory(session_id=session_id)
    return _sessions[session_id]

def save_session(session: WorkingMemory):
    _sessions[session.session_id] = session
