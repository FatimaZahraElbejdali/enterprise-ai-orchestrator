import os

from dotenv import load_dotenv

from models.gemini_classifier import classify_intent as classify_with_gemini
from orchestrator.intent_classifier import classify_with_confidence

load_dotenv()


def _agent_from_intent(intent: str) -> str:
    if intent == "odoo":
        return "odoo_agent"

    if intent == "support":
        return "support_agent"

    if intent == "knowledge":
        return "knowledge_agent"

    if intent == "development":
        return "development_agent"

    if intent == "security":
        return "security_agent"

    if intent == "server":
        return "server_agent"

    return "general_agent"


def classify_message(message: str):
    gemini_key = os.getenv("GEMINI_API_KEY")

    if gemini_key:
        gemini_result = classify_with_gemini(message)

        if gemini_result.get("classifier_source") == "gemini":
            return gemini_result

        fallback = classify_with_confidence(message)
        intent = fallback["intent"]

        return {
            "intent": intent,
            "selected_agent": _agent_from_intent(intent),
            "confidence": fallback["confidence"],
            "requires_approval": False,
            "classifier_source": "fallback_after_gemini_failure",
            "classifier_error": gemini_result.get("classifier_error"),
        }

    fallback = classify_with_confidence(message)
    intent = fallback["intent"]

    return {
        "intent": intent,
        "selected_agent": _agent_from_intent(intent),
        "confidence": fallback["confidence"],
        "requires_approval": False,
        "classifier_source": "keyword_fallback_no_api_key",
        "classifier_error": "No GEMINI_API_KEY found.",
    }