from typing import Literal

ModelName = Literal["mock", "openai", "gemini", "claude"]


def select_model(intent: str, risk_level: str) -> ModelName:
    """
    Select the most suitable AI model based on intent and risk level.

    For now, this is rule-based.
    Later, it can be replaced with cost-aware, latency-aware,
    or policy-based model selection.
    """

    normalized_intent = intent.lower() if intent else "unknown"
    normalized_risk = risk_level.lower() if risk_level else "low"

    if normalized_risk == "high":
        return "openai"

    if normalized_intent in ["knowledge", "development"]:
        return "gemini"

    if normalized_intent in ["security", "server"]:
        return "claude"

    return "mock"