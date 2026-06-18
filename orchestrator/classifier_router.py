import os

from dotenv import load_dotenv

from models.gemini_classifier import classify_intent as classify_with_gemini
from models.deepseek_classifier import classify_with_deepseek
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


def _format_result(result: dict, source: str, error=None):
    intent = result.get("intent", "general")

    return {
        "intent": intent,
        "selected_agent": _agent_from_intent(intent),
        "confidence": result.get("confidence", 0.7),
        "requires_approval": result.get("requires_approval", False),
        "classifier_source": source,
        "classifier_error": error,
    }


def classify_message(message: str):
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if deepseek_key:
        try:
            deepseek_result = classify_with_deepseek(message)

            if deepseek_result.get("classifier_source") == "deepseek":
                return _format_result(deepseek_result, "deepseek")

        except Exception as error:
            deepseek_error = str(error)
    else:
        deepseek_error = "No DEEPSEEK_API_KEY found."

    if gemini_key:
        try:
            gemini_result = classify_with_gemini(message)

            if gemini_result.get("classifier_source") == "gemini":
                return _format_result(gemini_result, "gemini")

            gemini_error = gemini_result.get("classifier_error")

        except Exception as error:
            gemini_error = str(error)
    else:
        gemini_error = "No GEMINI_API_KEY found."

    fallback = classify_with_confidence(message)
    intent = fallback["intent"]

    return {
        "intent": intent,
        "selected_agent": _agent_from_intent(intent),
        "confidence": fallback["confidence"],
        "requires_approval": fallback.get("requires_approval", False),
        "classifier_source": "local_rules_fallback",
        "classifier_error": {
            "deepseek_error": deepseek_error,
            "gemini_error": gemini_error,
        },
    }