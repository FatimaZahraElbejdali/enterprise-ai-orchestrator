from orchestrator.model_router import select_model


def test_high_risk_uses_openai():
    assert select_model("support", "high") == "openai"


def test_knowledge_intent_uses_gemini():
    assert select_model("knowledge", "low") == "gemini"


def test_development_intent_uses_gemini():
    assert select_model("development", "medium") == "gemini"


def test_security_intent_uses_claude():
    assert select_model("security", "low") == "claude"


def test_server_intent_uses_claude():
    assert select_model("server", "medium") == "claude"


def test_unknown_intent_uses_mock():
    assert select_model("unknown", "low") == "mock"