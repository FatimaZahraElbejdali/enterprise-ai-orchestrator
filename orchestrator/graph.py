from orchestrator.router import (
    classify_intent,
    select_model
)

from models.openai_adapter import ask_gpt
from models.claude_adapter import ask_claude
from models.gemini_adapter import ask_gemini


def process_request(message: str):

    intent = classify_intent(message)

    model = select_model(intent)

    if model == "gpt":
        response = ask_gpt(message)

    elif model == "claude":
        response = ask_claude(message)

    else:
        response = ask_gemini(message)

    return {
        "intent": intent,
        "selected_model": model,
        "response": response
    }