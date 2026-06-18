import os

from models.openai_adapter import is_openai_configured


MINI_INTENTS = {
    "classification",
    "classification_failed",
    "support",
    "knowledge",
    "general",
    "chat",
}

STRONG_INTENT_ENV = {
    "development": "OPENAI_DEVELOPMENT_MODEL",
    "security": "OPENAI_SECURITY_MODEL",
}

MINI_INTENT_ENV = {
    "classification": "OPENAI_CLASSIFIER_MODEL",
    "classification_failed": "OPENAI_SUPPORT_MODEL",
    "support": "OPENAI_SUPPORT_MODEL",
    "knowledge": "OPENAI_KNOWLEDGE_MODEL",
    "server": "OPENAI_SERVER_MODEL",
    "general": "OPENAI_DEFAULT_MODEL",
    "chat": "OPENAI_DEFAULT_MODEL",
}


def _model_from_env(env_name: str, default: str) -> str:
    return os.getenv(env_name) or default


def select_model(intent: str, risk_level: str = "low") -> dict:
    """
    Select a provider/model route without granting the model execution authority.
    Odoo remains controlled by deterministic local policy and connector code.
    """

    normalized_intent = intent.lower() if intent else "general"
    normalized_risk = risk_level.lower() if risk_level else "low"

    if normalized_intent == "odoo":
        return {
            "provider": "mock",
            "model": "policy_engine",
            "reason": "Odoo actions are handled by deterministic local policy, approvals, and the Odoo connector.",
        }

    if not is_openai_configured():
        return {
            "provider": "mock",
            "model": _model_from_env("OPENAI_DEFAULT_MODEL", "gpt-4.1-mini"),
            "reason": "OPENAI_API_KEY is not configured; using local fallback.",
        }

    if normalized_intent in STRONG_INTENT_ENV or normalized_risk == "high":
        env_name = STRONG_INTENT_ENV.get(normalized_intent, "OPENAI_SECURITY_MODEL")
        default = "gpt-4.1" if normalized_intent in {"development", "security"} else "gpt-4.1-mini"

        return {
            "provider": "openai",
            "model": _model_from_env(env_name, default),
            "reason": "Selected stronger model for high-risk, development, or security reasoning.",
        }

    if normalized_intent in MINI_INTENTS or normalized_intent == "server":
        env_name = MINI_INTENT_ENV.get(normalized_intent, "OPENAI_DEFAULT_MODEL")

        return {
            "provider": "openai",
            "model": _model_from_env(env_name, "gpt-4.1-mini"),
            "reason": "Selected mini model for normal enterprise chat and assistance.",
        }

    return {
        "provider": "openai",
        "model": _model_from_env("OPENAI_DEFAULT_MODEL", "gpt-4.1-mini"),
        "reason": "Selected default OpenAI model for general fallback reasoning.",
    }
