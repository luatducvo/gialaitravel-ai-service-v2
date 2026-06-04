from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class WorkingMemory(BaseModel):
    session_id: str
    current_step: str = "cold_start"  # cold_start, elicit, plan, refine, finalized
    
    # Cold-start constraints
    duration: Optional[str] = None
    group: Optional[str] = None
    transport: Optional[str] = None
    
    # Derived filters
    intensity_filter: List[str] = Field(default_factory=list)
    max_km_per_day: float = 35.0
    
    # Route optimization preference (set during cold_start from payload)
    optimize_route: bool = True

    # Elicitation
    vibe_query: Optional[str] = None
    
    # Itinerary
    current_itinerary: Optional[Dict[str, Any]] = None
    
    # Constraints learned from reflection
    learned_constraints: List[str] = Field(default_factory=list)
    
    # Conversation history
    messages: List[Dict[str, Any]] = Field(default_factory=list)

def detect_step(memory: WorkingMemory) -> str:
    if memory.current_step == "finalized":
        return "finalized"
    if not all([memory.duration, memory.group, memory.transport]):
        return "cold_start"
    if not memory.vibe_query:
        return "elicit"
    if not memory.current_itinerary:
        return "plan"
    return "refine"
