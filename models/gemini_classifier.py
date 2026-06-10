import json
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

GEMINI_MODEL = "models/gemini-2.0-flash"
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "8"))

VALID_AGENTS = {
    "support_agent",
    "development_agent",
    "security_agent",
    "server_agent",
    "odoo_agent",
    "knowledge_agent",
    "general_agent",
}


def _classification_failed(error: Exception | str):
    return {
        "intent": "classification_failed",
        "selected_agent": "general_agent",
        "confidence": 0.0,
        "requires_approval": False,
        "classifier_source": "gemini_failed",
        "classifier_error": str(error),
    }


def _parse_bool(value):
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() == "true"

    return False


def _normalize_classification(classification):
    if not isinstance(classification, dict):
        return _classification_failed("Classifier returned non-object JSON")

    required_fields = {
        "intent",
        "selected_agent",
        "confidence",
        "requires_approval",
    }
    missing_fields = sorted(required_fields - set(classification))
    if missing_fields:
        return _classification_failed(
            f"Classifier response missing fields: {', '.join(missing_fields)}"
        )

    selected_agent = classification.get("selected_agent")
    if selected_agent not in VALID_AGENTS:
        return _classification_failed(
            f"Classifier returned invalid selected_agent: {selected_agent}"
        )

    try:
        confidence = float(classification["confidence"])
    except (TypeError, ValueError):
        return _classification_failed(
            f"Classifier returned invalid confidence: {classification['confidence']}"
        )

    confidence = max(0.0, min(confidence, 1.0))

    return {
        "intent": str(classification.get("intent", "general")),
        "selected_agent": selected_agent,
        "confidence": confidence,
        "requires_approval": _parse_bool(
            classification.get("requires_approval", False)
        ),
        "classifier_source": "gemini",
        "classifier_error": None,
    }


def classify_intent(message: str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return _classification_failed("GEMINI_API_KEY is not set")

    prompt = f"""
You are an enterprise AI orchestration classifier.

Classify the user request into one of these agents:

- support_agent
- development_agent
- security_agent
- server_agent
- odoo_agent
- knowledge_agent
- general_agent

Allowed intent values:
- support
- development
- security
- server
- odoo
- knowledge
- general

Return ONLY valid JSON with this exact schema:

{{
  "intent": "support",
  "selected_agent": "support_agent",
  "confidence": 0.95,
  "requires_approval": false,
  "classifier_source": "gemini",
  "classifier_error": null
}}

User request:
{message}
"""

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            prompt,
            generation_config={
                "response_mime_type": "application/json",
            },
            request_options={
                "timeout": GEMINI_TIMEOUT_SECONDS,
            },
        )
        return _normalize_classification(json.loads(response.text.strip()))

    except Exception as error:
        return _classification_failed(error)