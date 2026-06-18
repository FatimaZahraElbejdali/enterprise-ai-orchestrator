from orchestrator.model_router import select_model


def test_missing_key_uses_mock(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    route = select_model("support", "low")

    assert route["provider"] == "mock"
    assert route["model"] == "gpt-4.1-mini"


def test_support_intent_uses_mini_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_SUPPORT_MODEL", "gpt-4.1-mini")
    monkeypatch.setattr("orchestrator.model_router.is_openai_configured", lambda: True)

    route = select_model("support", "low")

    assert route["provider"] == "openai"
    assert route["model"] == "gpt-4.1-mini"


def test_knowledge_intent_uses_mini_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_KNOWLEDGE_MODEL", "gpt-4.1-mini")
    monkeypatch.setattr("orchestrator.model_router.is_openai_configured", lambda: True)

    route = select_model("knowledge", "low")

    assert route["provider"] == "openai"
    assert route["model"] == "gpt-4.1-mini"


def test_development_intent_uses_stronger_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_DEVELOPMENT_MODEL", "gpt-4.1")
    monkeypatch.setattr("orchestrator.model_router.is_openai_configured", lambda: True)

    route = select_model("development", "medium")

    assert route["provider"] == "openai"
    assert route["model"] == "gpt-4.1"


def test_security_intent_uses_stronger_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_SECURITY_MODEL", "gpt-4.1")
    monkeypatch.setattr("orchestrator.model_router.is_openai_configured", lambda: True)

    route = select_model("security", "low")

    assert route["provider"] == "openai"
    assert route["model"] == "gpt-4.1"


def test_server_intent_uses_server_mini_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_SERVER_MODEL", "gpt-4.1-mini")
    monkeypatch.setattr("orchestrator.model_router.is_openai_configured", lambda: True)

    route = select_model("server", "medium")

    assert route["provider"] == "openai"
    assert route["model"] == "gpt-4.1-mini"


def test_odoo_intent_uses_policy_engine(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("orchestrator.model_router.is_openai_configured", lambda: True)

    route = select_model("odoo", "high")

    assert route["provider"] == "mock"
    assert route["model"] == "policy_engine"
