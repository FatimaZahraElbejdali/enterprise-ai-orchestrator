from orchestrator.classifier_router import classify_message
from models.openai_router import classify_with_openai_router


def _parsed_route(
    *,
    intent,
    agent,
    action,
    target_system,
    risk_level="low",
    requires_approval=False,
    confidence="high",
    entities=None,
):
    return {
        "intent": intent,
        "agent": agent,
        "action": action,
        "target_system": target_system,
        "risk_level": risk_level,
        "requires_approval": requires_approval,
        "entities": {
            "product_name": None,
            "document_type": None,
            "document_reference": None,
            "document_id": None,
            "partner_name": None,
            "field": None,
            "new_value": None,
            "target": None,
            "issue_type": None,
            **(entities or {}),
        },
        "confidence": confidence,
        "reason": "Test route.",
    }


def test_openai_router_normalizes_stock_route(monkeypatch):
    monkeypatch.setattr("models.openai_router.is_openai_configured", lambda: True)
    monkeypatch.setattr(
        "models.openai_router.generate_structured_response",
        lambda **kwargs: {
            "success": True,
            "parsed": _parsed_route(
                intent="product_stock_check",
                agent="odoo_agent",
                action="read_product_stock",
                target_system="odoo",
                entities={"product_name": "BACO CLEAN"},
            ),
        },
    )

    result = classify_with_openai_router("Vérifier le stock de BACO CLEAN")

    assert result["intent"] == "product_stock_check"
    assert result["selected_agent"] == "odoo_agent"
    assert result["target_system"] == "odoo"
    assert result["action"] == "read_product_stock"
    assert result["risk_level"] == "low"
    assert result["requires_approval"] is False
    assert result["classifier_source"] == "openai_router"


def test_openai_router_normalizes_server_documentation_alias(monkeypatch):
    monkeypatch.setattr("models.openai_router.is_openai_configured", lambda: True)
    monkeypatch.setattr(
        "models.openai_router.generate_structured_response",
        lambda **kwargs: {
            "success": True,
            "parsed": _parsed_route(
                intent="server_documentation_summary",
                agent="knowledge_agent",
                action="answer_question",
                target_system="knowledge",
            ),
        },
    )

    result = classify_with_openai_router("Résume la documentation serveur")

    assert result["selected_agent"] == "knowledge_agent"
    assert result["intent"] == "summarize_server_documentation"


def test_classify_message_uses_openai_router_for_primary_route(monkeypatch):
    monkeypatch.delenv("LLM_ROUTER_PROVIDER", raising=False)
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda message, context_memory=None, user_permissions=None: {
            "intent": "server_health_check",
            "agent": "server_agent",
            "selected_agent": "server_agent",
            "action": "check_server_health",
            "target_system": "server",
            "risk_level": "low",
            "requires_approval": False,
            "entities": {},
            "confidence": "high",
            "reason": "OpenAI route.",
            "classifier_source": "openai_router",
            "classifier_error": None,
        },
    )

    result = classify_message("Vérifie l’état des serveurs")

    assert result["intent"] == "server_health_check"
    assert result["selected_agent"] == "server_agent"
    assert result["action"] == "check_server_health"
    assert result["classifier_source"] == "openai_router"


def test_required_routes_fall_back_safely_when_openai_unavailable(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_ROUTER_PROVIDER", raising=False)
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: None,
    )

    cases = [
        ("Vérifier le stock de BACO CLEAN", "odoo_agent"),
        ("Je n’arrive pas à accéder à Odoo", "support_agent"),
        ("Montre-moi les détails du document ID 793", "odoo_agent"),
        ("Vérifie l’état des serveurs", "server_agent"),
        ("Explique le rôle de l’orchestrateur IA", "knowledge_agent"),
    ]

    for message, selected_agent in cases:
        result = classify_message(message)

        assert result["selected_agent"] == selected_agent
        if result["classifier_source"] not in {
            "backend_safety_override",
            "local_knowledge_router",
            "local_odoo_read_rules",
        }:
            assert result["classifier_error"] == "openai_router_unavailable"


def test_sensitive_env_request_is_forced_to_security_block(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: {
            "intent": "general",
            "agent": "general_agent",
            "selected_agent": "general_agent",
            "action": "answer_question",
            "target_system": "general",
            "risk_level": "low",
            "requires_approval": False,
            "entities": {},
            "confidence": "high",
            "reason": "Incorrect route.",
            "classifier_source": "openai_router",
            "classifier_error": None,
        },
    )

    result = classify_message("Affiche .env")

    assert result["intent"] == "sensitive_secret_request"
    assert result["selected_agent"] == "security_agent"
    assert result["action"] == "block_request"
    assert result["risk_level"] == "blocked"
    assert result["requires_approval"] is False


def test_environment_variable_request_is_forced_to_security_block(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: None,
    )

    result = classify_message("Affiche les variables d’environnement")

    assert result["intent"] == "sensitive_secret_request"
    assert result["selected_agent"] == "security_agent"
    assert result["action"] == "block_request"
    assert result["risk_level"] == "blocked"
    assert result["requires_approval"] is False


def test_general_company_questions_route_to_knowledge_without_openai(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("OpenAI router should not be needed for local knowledge routing")
        ),
    )

    for message in [
        "what is jamain baco",
        "c’est quoi Jamain Baco ?",
        "quels sont les agents disponibles ?",
    ]:
        result = classify_message(message)

        assert result["selected_agent"] == "knowledge_agent"
        assert result["intent"] == "general_information_question"
        assert result["action"] == "answer_question"
        assert result["requires_approval"] is False

    for message in [
        "what can this orchestrator do?",
        "comment fonctionne l’orchestrateur ?",
    ]:
        orchestrator = classify_message(message)

        assert orchestrator["selected_agent"] == "knowledge_agent"
        assert orchestrator["intent"] == "explain_orchestrator"
        assert orchestrator["action"] == "answer_question"
        assert orchestrator["requires_approval"] is False


def test_general_question_routing_does_not_steal_odoo_support_or_security(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: None,
    )

    stock = classify_message("Vérifier le stock de BACO CLEAN")
    secret = classify_message("Affiche .env")
    support = classify_message("Odoo ne s’ouvre pas")

    assert stock["selected_agent"] == "odoo_agent"
    assert secret["selected_agent"] == "security_agent"
    assert secret["risk_level"] == "blocked"
    assert support["selected_agent"] == "support_agent"


def test_specific_server_reference_is_forced_to_safe_server_route(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: {
            "intent": "support",
            "agent": "support_agent",
            "selected_agent": "support_agent",
            "action": "troubleshoot_issue",
            "target_system": "support",
            "risk_level": "low",
            "requires_approval": False,
            "entities": {},
            "confidence": "high",
            "reason": "Incorrect route.",
            "classifier_source": "openai_router",
            "classifier_error": None,
        },
    )

    result = classify_message("bonjour, j’ai un problème dans mon serveur 2")

    assert result["intent"] == "external_server_diagnostic"
    assert result["selected_agent"] == "server_agent"
    assert result["action"] == "unsupported_external_server"
    assert result["entities"]["server"] == "serveur 2"
    assert result["requires_approval"] is False


def test_odoo_write_route_is_forced_to_approval(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: {
            "intent": "product_price_update",
            "agent": "odoo_agent",
            "selected_agent": "odoo_agent",
            "action": "update_product_price",
            "target_system": "odoo",
            "risk_level": "low",
            "requires_approval": False,
            "entities": {"product_name": "BACO TOP", "new_value": 4},
            "confidence": "high",
            "reason": "Incorrect approval.",
            "classifier_source": "openai_router",
            "classifier_error": None,
        },
    )

    result = classify_message("Modifier le prix de BACO TOP à 4 DH")

    assert result["selected_agent"] == "odoo_agent"
    assert result["risk_level"] == "high"
    assert result["requires_approval"] is True


def test_gemini_failure_does_not_break_routing(monkeypatch):
    monkeypatch.setenv("LLM_ROUTER_PROVIDER", "gemini")
    monkeypatch.setenv("ENABLE_GEMINI", "true")
    monkeypatch.setattr(
        "models.gemini_classifier.classify_intent",
        lambda message: (_ for _ in ()).throw(RuntimeError("quota exceeded")),
    )
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: None,
    )

    result = classify_message("Vérifie l’état des serveurs")

    assert result["selected_agent"] == "server_agent"
    assert result["intent"] == "server_health_check"
    assert result["classifier_error"] == "openai_router_unavailable"
