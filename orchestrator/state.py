from typing import TypedDict

class AgentState(TypedDict):
    user_message: str
    intent: str
    selected_model: str
    selected_agent: str
    response: str