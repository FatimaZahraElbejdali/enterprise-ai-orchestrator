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


def _semantic_route(
    *,
    request_type,
    domain,
    capability,
    requires_internal_context=False,
    topic=None,
    entities=None,
    parameters=None,
    clarification_needed=False,
    missing_parameters=None,
    confidence="high",
):
    return {
        "request_type": request_type,
        "domain": domain,
        "capability": capability,
        "requires_internal_context": requires_internal_context,
        "topic": topic,
        "entities": entities or {},
        "parameters": parameters or {},
        "clarification_needed": clarification_needed,
        "missing_parameters": missing_parameters or [],
        "confidence": confidence,
        "reason": "Test semantic route.",
    }


def _mock_semantic_router(monkeypatch, parsed):
    monkeypatch.setattr("models.openai_router.is_openai_configured", lambda: True)
    monkeypatch.setattr(
        "models.openai_router.generate_structured_response",
        lambda **kwargs: {"success": True, "parsed": parsed},
    )


def test_openai_router_validates_creative_generation_capability(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="creative_generation",
            domain="knowledge",
            capability="knowledge.creative_generation",
            topic="nouveau nom pour l'application",
        ),
    )

    result = classify_with_openai_router(
        "est ce que tu peux suggérer un autre nom pour l'application"
    )

    assert result["request_type"] == "creative_generation"
    assert result["selected_agent"] == "knowledge_agent"
    assert result["capability"] == "knowledge.creative_generation"
    assert result["execution_mode"] == "llm_direct"
    assert result["action"] == "creative_generation"
    assert result["classifier_source"] == "openai_structured"
    assert result["semantic_source"] == "openai_structured"


def test_openai_router_validates_enterprise_knowledge_capability(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_knowledge",
            domain="knowledge",
            capability="knowledge.enterprise_answer",
            requires_internal_context=True,
            topic="histoire du groupe Jamain Baco",
        ),
    )

    result = classify_with_openai_router("c quoi l'histoire du groupe jamain baco")

    assert result["selected_agent"] == "knowledge_agent"
    assert result["capability"] == "knowledge.enterprise_answer"
    assert result["execution_mode"] == "retrieval_grounded"
    assert result["entities"]["knowledge_topic"] == "histoire du groupe Jamain Baco"


def test_openai_router_validates_general_and_writing_capabilities(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="general_knowledge",
            domain="knowledge",
            capability="knowledge.general_answer",
            topic="Odoo",
        ),
    )

    general = classify_with_openai_router("Qu'est-ce qu'Odoo ?")
    assert general["capability"] == "knowledge.general_answer"
    assert general["execution_mode"] == "llm_direct"

    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="writing_assistance",
            domain="knowledge",
            capability="knowledge.writing_assistance",
            topic="reformulation",
        ),
    )

    writing = classify_with_openai_router("Reformule ce message")
    assert writing["capability"] == "knowledge.writing_assistance"
    assert writing["action"] == "writing_assistance"


def test_openai_router_validates_support_and_odoo_execution_modes(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="troubleshooting",
            domain="support",
            capability="support.troubleshooting",
            topic="accès Odoo",
        ),
    )

    support = classify_with_openai_router("Odoo ne s'ouvre pas")
    assert support["selected_agent"] == "support_agent"
    assert support["capability"] == "support.troubleshooting"
    assert support["execution_mode"] == "llm_direct"

    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="odoo",
            capability="odoo.product_stock",
            entities={"product_name": "BACO CLEAN"},
        ),
    )

    odoo_read = classify_with_openai_router("Quel est le stock de BACO CLEAN ?")
    assert odoo_read["selected_agent"] == "odoo_agent"
    assert odoo_read["capability"] == "odoo.product_stock"
    assert odoo_read["execution_mode"] == "tool"
    assert odoo_read["requires_approval"] is False

    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="odoo",
            capability="odoo.product_price_update",
            parameters={"product_name": "BACO CLEAN", "new_price": 5},
        ),
    )

    odoo_write = classify_with_openai_router("Modifier le prix de BACO CLEAN à 5")
    assert odoo_write["capability"] == "odoo.product_price_update"
    assert odoo_write["execution_mode"] == "tool"
    assert odoo_write["requires_approval"] is True
    assert odoo_write["risk_level"] == "medium"

    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="odoo",
            capability="odoo.generic_read",
            parameters={
                "operation": "list",
                "business_object": "subscriptions",
                "limit": 5,
            },
        ),
    )

    generic_read = classify_with_openai_router("Liste les abonnements")
    assert generic_read["selected_agent"] == "odoo_agent"
    assert generic_read["capability"] == "odoo.generic_read"
    assert generic_read["action"] == "odoo_generic_read"
    assert generic_read["execution_mode"] == "tool"
    assert generic_read["requires_approval"] is False
    assert generic_read["parameters"]["business_object"] == "subscriptions"


def test_openai_router_normalizes_server_domain_placeholder_to_registered_diagnostic(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="server",
            capability="server",
            parameters={
                "operation": "check",
                "metric": "cpu",
            },
        ),
    )

    result = classify_with_openai_router("Check the configured server CPU")

    assert result["selected_agent"] == "server_agent"
    assert result["domain"] == "server"
    assert result["capability"] == "server.cpu_usage"
    assert result["action"] == "check_cpu_usage"
    assert result["execution_mode"] == "tool"


def test_openai_router_normalizes_server_status_placeholder_to_local_health(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="server",
            capability="server",
            parameters={
                "operation": "status",
            },
        ),
    )

    result = classify_with_openai_router("Check configured server status")

    assert result["selected_agent"] == "server_agent"
    assert result["capability"] == "server.local_health"
    assert result["action"] == "check_server_health"


def test_openai_router_normalizes_french_server_state_placeholder_to_health(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="server",
            capability="server",
            parameters={
                "operation": "read",
                "target": "état des serveurs",
            },
        ),
    )

    result = classify_with_openai_router("Vérifie l’état des serveurs")

    assert result["selected_agent"] == "server_agent"
    assert result["domain"] == "server"
    assert result["capability"] == "server.local_health"
    assert result["action"] == "check_server_health"


def test_openai_router_normalizes_missing_server_status_capability_to_health(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="server",
            capability=None,
            parameters={
                "operation": "read",
                "target": "état des serveurs",
            },
        ),
    )

    result = classify_with_openai_router("Vérifie l’état des serveurs")

    assert result["selected_agent"] == "server_agent"
    assert result["domain"] == "server"
    assert result["capability"] == "server.local_health"
    assert result["action"] == "check_server_health"


def test_openai_router_clears_clarification_for_registered_server_health(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="server",
            capability="server.local_health",
            clarification_needed=True,
            missing_parameters=["metric"],
            parameters={
                "operation": "status",
                "target": "état des serveurs",
            },
        ),
    )

    result = classify_with_openai_router("Vérifie l’état des serveurs")

    assert result["selected_agent"] == "server_agent"
    assert result["capability"] == "server.local_health"
    assert result["clarification_needed"] is False
    assert result["missing_parameters"] == []


def test_classify_message_clears_clarification_for_registered_server_health(monkeypatch):
    monkeypatch.delenv("LLM_ROUTER_PROVIDER", raising=False)
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: {
            "intent": "server_health_check",
            "request_type": "enterprise_action",
            "domain": "server",
            "capability": "server.local_health",
            "execution_mode": "tool",
            "agent": "server_agent",
            "selected_agent": "server_agent",
            "action": "check_server_health",
            "target_system": "server",
            "risk_level": "low",
            "requires_approval": False,
            "clarification_needed": True,
            "missing_parameters": ["metric"],
            "parameters": {"operation": "status"},
            "entities": {},
            "confidence": "high",
            "reason": "Provider asked for an unnecessary metric.",
            "classifier_source": "openai_structured",
            "semantic_source": "openai_structured",
        },
    )

    result = classify_message("Vérifie l’état des serveurs")

    assert result["selected_agent"] == "server_agent"
    assert result["capability"] == "server.local_health"
    assert result["clarification_needed"] is False
    assert result["missing_parameters"] == []


def test_classify_message_defaults_server_health_clarification_to_registered_capability(monkeypatch):
    monkeypatch.delenv("LLM_ROUTER_PROVIDER", raising=False)
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: {
            "intent": "server_issue_clarification",
            "request_type": "enterprise_action",
            "domain": "server",
            "capability": None,
            "execution_mode": None,
            "agent": "server_agent",
            "selected_agent": "server_agent",
            "action": "clarify_server_issue",
            "target_system": "server",
            "risk_level": "low",
            "requires_approval": False,
            "clarification_needed": True,
            "missing_parameters": ["metric"],
            "parameters": {},
            "entities": {},
            "confidence": "high",
            "reason": "Provider asked for an unnecessary metric.",
            "classifier_source": "openai_structured",
            "semantic_source": "openai_structured",
        },
    )

    result = classify_message("Vérifie l’état des serveurs")

    assert result["selected_agent"] == "server_agent"
    assert result["capability"] == "server.local_health"
    assert result["action"] == "check_server_health"
    assert result["clarification_needed"] is False
    assert result["missing_parameters"] == []


def test_openai_router_keeps_unsupported_server_placeholder_unsupported(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="server",
            capability="server",
            parameters={
                "operation": "create",
                "target": "internal file",
            },
        ),
    )

    result = classify_with_openai_router("Create something on the internal server")

    assert result["selected_agent"] == "server_agent"
    assert result["action"] == "unsupported_capability"
    assert result["capability_validation_error"]
    assert result.get("capability") != "server.local_health"


def test_openai_router_keeps_server_documentation_placeholder_in_knowledge(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="general_knowledge",
            domain="server",
            capability="server",
            topic="server documentation",
            parameters={
                "operation": "summarize",
            },
        ),
    )

    result = classify_with_openai_router("Résume la documentation serveur")

    assert result["selected_agent"] == "knowledge_agent"
    assert result["domain"] == "knowledge"
    assert result["capability"] == "knowledge.general_answer"
    assert result["execution_mode"] == "llm_direct"


def test_openai_router_preserves_documentation_summary_intent_when_mislabeled_writing(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="writing_assistance",
            domain="knowledge",
            capability="knowledge.writing_assistance",
            topic="documentation serveur",
            parameters={
                "operation": "summarize",
            },
        ),
    )

    result = classify_with_openai_router("Résumé la documentation serveur")

    assert result["selected_agent"] == "knowledge_agent"
    assert result["intent"] == "summarize_server_documentation"
    assert result["capability"] == "knowledge.general_answer"
    assert result["execution_mode"] == "llm_direct"


def test_openai_router_overrides_server_capability_for_documentation_summary(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="writing_assistance",
            domain="server",
            capability="server.local_health",
            topic="documentation serveur",
            parameters={
                "operation": "summarize",
            },
        ),
    )

    result = classify_with_openai_router("Résumé la documentation serveur")

    assert result["selected_agent"] == "knowledge_agent"
    assert result["intent"] == "summarize_server_documentation"
    assert result["capability"] == "knowledge.general_answer"


def test_openai_router_rejects_unknown_capability(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="odoo",
            capability="odoo.arbitrary_xmlrpc",
        ),
    )

    result = classify_with_openai_router("Appelle une méthode Odoo arbitraire")

    assert result["action"] == "unsupported_capability"
    assert result["capability_validation_error"]
    assert result["classifier_error"] == "capability_validation_failed"


def test_openai_router_normalizes_general_knowledge_without_capability(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="general_knowledge",
            domain="general",
            capability=None,
        ),
    )

    result = classify_with_openai_router("Explique une API REST")

    assert result["domain"] == "knowledge"
    assert result["selected_agent"] == "knowledge_agent"
    assert result["capability"] == "knowledge.general_answer"
    assert result["execution_mode"] == "llm_direct"


def test_openai_router_normalizes_writing_without_capability(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="writing_assistance",
            domain="general",
            capability=None,
        ),
    )

    result = classify_with_openai_router("Reformule ce texte")

    assert result["domain"] == "knowledge"
    assert result["selected_agent"] == "knowledge_agent"
    assert result["capability"] == "knowledge.writing_assistance"
    assert result["execution_mode"] == "llm_direct"


def test_openai_router_normalizes_direct_knowledge_capability_wrong_domain(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="writing_assistance",
            domain="general",
            capability="knowledge.writing_assistance",
        ),
    )

    result = classify_with_openai_router("Reformule ce texte")

    assert result["domain"] == "knowledge"
    assert result["selected_agent"] == "knowledge_agent"
    assert result["capability"] == "knowledge.writing_assistance"
    assert result["execution_mode"] == "llm_direct"


def test_openai_router_normalizes_creative_without_capability(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="creative_generation",
            domain="general",
            capability=None,
        ),
    )

    result = classify_with_openai_router("Donne-moi cinq idées")

    assert result["domain"] == "knowledge"
    assert result["selected_agent"] == "knowledge_agent"
    assert result["capability"] == "knowledge.creative_generation"
    assert result["execution_mode"] == "llm_direct"


def test_openai_router_normalizes_generic_read_search_alias_for_dynamic_models(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="odoo",
            capability="odoo.generic_read_search",
            parameters={
                "operation": "list",
                "business_object": "subscription",
                "model": "subscription",
            },
        ),
    )

    result = classify_with_openai_router("Liste les abonnements")

    assert result["capability"] == "odoo.generic_read"
    assert result["action"] == "odoo_generic_read"
    assert result["parameters"]["business_object"] == "subscription"


def test_openai_router_normalizes_product_search_for_non_product_business_object(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="odoo",
            capability="odoo.product_search",
            parameters={
                "operation": "list",
                "business_object": "subscription.plan",
                "model": "subscription.plan",
            },
        ),
    )

    result = classify_with_openai_router("Liste les plans abonnement")

    assert result["capability"] == "odoo.generic_read"
    assert result["action"] == "odoo_generic_read"


def test_openai_router_normalizes_uncapable_odoo_read_to_generic_read(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="odoo",
            capability=None,
            parameters={
                "operation": "describe",
                "business_object": "generic business area",
                "limit": 10,
            },
        ),
    )

    result = classify_with_openai_router(
        "What is available in the generic business area section in Odoo?"
    )

    assert result["selected_agent"] == "odoo_agent"
    assert result["capability"] == "odoo.generic_read"
    assert result["action"] == "odoo_generic_read"
    assert result["execution_mode"] == "tool"


def test_openai_router_keeps_uncapable_odoo_write_unsupported(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="odoo",
            capability=None,
            parameters={
                "operation": "update",
                "business_object": "generic business concept",
                "field": "status",
                "new_value": "done",
            },
        ),
    )

    result = classify_with_openai_router(
        "Update the generic business concept status in Odoo"
    )

    assert result["selected_agent"] == "odoo_agent"
    assert result["action"] == "unsupported_capability"
    assert result["capability_validation_error"]


def test_openai_router_preserves_missing_parameters(monkeypatch):
    _mock_semantic_router(
        monkeypatch,
        _semantic_route(
            request_type="enterprise_action",
            domain="odoo",
            capability="odoo.product_price_update",
            clarification_needed=True,
            missing_parameters=["new_price"],
            parameters={"product_name": "BACO CLEAN"},
        ),
    )

    result = classify_with_openai_router("Modifier le prix de BACO CLEAN")

    assert result["capability"] == "odoo.product_price_update"
    assert result["clarification_needed"] is True
    assert result["missing_parameters"] == ["new_price"]


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


def test_classify_message_normalizes_provider_server_placeholder_to_registered_capability(monkeypatch):
    monkeypatch.delenv("LLM_ROUTER_PROVIDER", raising=False)
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: {
            "intent": "server",
            "request_type": "enterprise_action",
            "domain": "server",
            "capability": "server",
            "execution_mode": "tool",
            "agent": "server_agent",
            "selected_agent": "server_agent",
            "action": "server",
            "target_system": "server",
            "risk_level": "low",
            "requires_approval": False,
            "parameters": {"operation": "check", "metric": "ram"},
            "entities": {},
            "confidence": "high",
            "reason": "Provider returned a domain placeholder.",
            "classifier_source": "openai_structured",
            "semantic_source": "openai_structured",
        },
    )

    result = classify_message("Check configured server RAM")

    assert result["selected_agent"] == "server_agent"
    assert result["domain"] == "server"
    assert result["capability"] == "server.ram_usage"
    assert result["action"] == "check_ram_usage"
    assert result["execution_mode"] == "tool"


def test_classify_message_keeps_provider_server_placeholder_unsupported(monkeypatch):
    monkeypatch.delenv("LLM_ROUTER_PROVIDER", raising=False)
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: {
            "intent": "server",
            "request_type": "enterprise_action",
            "domain": "server",
            "capability": "server",
            "execution_mode": "tool",
            "agent": "server_agent",
            "selected_agent": "server_agent",
            "action": "server",
            "target_system": "server",
            "risk_level": "low",
            "requires_approval": False,
            "parameters": {"operation": "create", "target": "internal server item"},
            "entities": {},
            "confidence": "high",
            "reason": "Provider returned a domain placeholder.",
            "classifier_source": "openai_structured",
            "semantic_source": "openai_structured",
        },
    )

    result = classify_message("Create an internal server item")

    assert result["selected_agent"] == "server_agent"
    assert result["action"] == "unsupported_capability"
    assert result["capability"] == "unsupported_capability"
    assert result["capability_validation_error"]


def test_classify_message_keeps_server_documentation_placeholder_in_knowledge(monkeypatch):
    monkeypatch.delenv("LLM_ROUTER_PROVIDER", raising=False)
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: {
            "intent": "server",
            "request_type": "general_knowledge",
            "domain": "server",
            "capability": "server",
            "execution_mode": "tool",
            "agent": "server_agent",
            "selected_agent": "server_agent",
            "action": "server",
            "target_system": "server",
            "risk_level": "low",
            "requires_approval": False,
            "parameters": {"operation": "summarize"},
            "entities": {},
            "confidence": "high",
            "reason": "Provider returned a domain placeholder.",
            "classifier_source": "openai_structured",
            "semantic_source": "openai_structured",
        },
    )

    result = classify_message("Résume la documentation serveur")

    assert result["selected_agent"] == "knowledge_agent"
    assert result["domain"] == "knowledge"
    assert result["capability"] == "knowledge.general_answer"
    assert result["execution_mode"] == "llm_direct"


def test_classify_message_routes_company_topic_general_answer_to_retrieval(monkeypatch):
    monkeypatch.delenv("LLM_ROUTER_PROVIDER", raising=False)
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: {
            "intent": "general_information_question",
            "request_type": "general_knowledge",
            "domain": "knowledge",
            "capability": "knowledge.general_answer",
            "execution_mode": "llm_direct",
            "agent": "knowledge_agent",
            "selected_agent": "knowledge_agent",
            "action": "answer_question",
            "target_system": "knowledge",
            "risk_level": "low",
            "requires_approval": False,
            "topic": "histoire du groupe Jamain Baco",
            "parameters": {},
            "entities": {"knowledge_topic": "histoire du groupe Jamain Baco"},
            "confidence": "high",
            "reason": "Provider mislabeled an enterprise topic as general.",
            "classifier_source": "openai_structured",
            "semantic_source": "openai_structured",
        },
    )

    result = classify_message("c quoi l'histoire du groupe jamain baco")

    assert result["selected_agent"] == "knowledge_agent"
    assert result["domain"] == "knowledge"
    assert result["capability"] == "knowledge.enterprise_answer"
    assert result["execution_mode"] == "retrieval_grounded"


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


def test_general_company_questions_use_limited_fallback_when_openai_unavailable(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: None,
    )

    for message in [
        "what is jamain baco",
        "c’est quoi Jamain Baco ?",
        "quels sont les agents disponibles ?",
    ]:
        result = classify_message(message)

        assert result["selected_agent"] == "knowledge_agent"
        assert result["intent"] == "general_information_question"
        assert result["action"] == "enterprise_answer"
        assert result["capability"] == "knowledge.enterprise_answer"
        assert result["execution_mode"] == "retrieval_grounded"
        assert result["requires_approval"] is False
        assert result["classifier_error"] == "openai_router_unavailable"

    for message in [
        "what can this orchestrator do?",
        "comment fonctionne l’orchestrateur ?",
    ]:
        orchestrator = classify_message(message)

        assert orchestrator["selected_agent"] == "knowledge_agent"
        assert orchestrator["intent"] == "explain_orchestrator"
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
