from fastapi.testclient import TestClient

import agents.knowledge_agent as knowledge_agent
import app as app_module
from app import app
from tests.auth_helpers import auth_headers


client = TestClient(app)


def semantic_classification(
    *,
    request_type,
    capability,
    execution_mode,
    domain="knowledge",
    agent="knowledge_agent",
    action=None,
    topic=None,
    clarification_needed=False,
    missing_parameters=None,
):
    return {
        "intent": "general_information_question",
        "request_type": request_type,
        "domain": domain,
        "capability": capability,
        "execution_mode": execution_mode,
        "agent": agent,
        "selected_agent": agent,
        "target_system": domain,
        "action": action or capability.rsplit(".", 1)[-1],
        "risk_level": "low",
        "risk": "low",
        "requires_approval": False,
        "approval_required": False,
        "entities": {"knowledge_topic": topic} if topic else {},
        "parameters": {},
        "clarification_needed": clarification_needed,
        "missing_parameters": missing_parameters or [],
        "semantic_request": {
            "request_type": request_type,
            "domain": domain,
            "capability": capability,
            "requires_internal_context": execution_mode == "retrieval_grounded",
            "topic": topic,
            "entities": {"knowledge_topic": topic} if topic else {},
            "parameters": {},
            "clarification_needed": clarification_needed,
            "missing_parameters": missing_parameters or [],
        },
        "confidence": "high",
        "classifier_source": "openai_structured",
        "semantic_source": "openai_structured",
    }


def test_creative_generation_uses_direct_llm_without_retrieval(monkeypatch):
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda *args, **kwargs: semantic_classification(
            request_type="creative_generation",
            capability="knowledge.creative_generation",
            execution_mode="llm_direct",
            action="creative_generation",
            topic="nouveau nom pour l'application",
        ),
    )
    monkeypatch.setattr(
        knowledge_agent,
        "search_knowledge",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Creative generation should not retrieve RAG context")
        ),
    )
    monkeypatch.setattr(knowledge_agent, "is_openai_configured", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        knowledge_agent,
        "generate_response",
        lambda **kwargs: {
            "success": True,
            "content": "Voici trois pistes de nom pour l'application.",
            "provider": "openai",
            "model": "test-model",
            "error": None,
        },
    )

    response = client.post(
        "/chat",
        json={
            "message": "est ce que tu peux suggérer un autre nom pour l'application, je veux plus Enterprise AI Orchestrator"
        },
        headers=auth_headers("admin@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "completed"
    assert data["response"] == "Voici trois pistes de nom pour l'application."
    assert data["sources"] == []
    assert data["technical"]["capability"] == "knowledge.creative_generation"
    assert data["technical"]["execution_mode"] == "llm_direct"
    assert data["technical"]["classifier_source"] == "openai_structured"
    assert data["technical"]["semantic_source"] == "openai_structured"
    assert data["technical"]["tool_used"] == "knowledge_creative_generation"


def test_general_answer_uses_direct_llm_without_retrieval(monkeypatch):
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda *args, **kwargs: semantic_classification(
            request_type="general_knowledge",
            capability="knowledge.general_answer",
            execution_mode="llm_direct",
            action="answer_question",
            topic="ERP",
        ),
    )
    monkeypatch.setattr(
        knowledge_agent,
        "search_knowledge",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("General answers should not retrieve RAG context")
        ),
    )
    monkeypatch.setattr(knowledge_agent, "is_openai_configured", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        knowledge_agent,
        "generate_response",
        lambda **kwargs: {
            "success": True,
            "content": "Un ERP aide à gérer des processus métier.",
            "provider": "openai",
            "model": "test-model",
            "error": None,
        },
    )

    response = client.post(
        "/chat",
        json={"message": "Qu'est-ce qu'un ERP ?"},
        headers=auth_headers("admin@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "completed"
    assert data["response"] == "Un ERP aide à gérer des processus métier."
    assert data["sources"] == []
    assert data["technical"]["capability"] == "knowledge.general_answer"
    assert data["technical"]["execution_mode"] == "llm_direct"
    assert data["technical"]["tool_used"] == "public_llm_answer"


def test_enterprise_knowledge_uses_retrieval_grounded_mode(monkeypatch):
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda *args, **kwargs: semantic_classification(
            request_type="enterprise_knowledge",
            capability="knowledge.enterprise_answer",
            execution_mode="retrieval_grounded",
            action="enterprise_answer",
            topic="histoire du groupe Jamain Baco",
        ),
    )
    monkeypatch.setattr(knowledge_agent, "is_openai_configured", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        knowledge_agent,
        "search_knowledge",
        lambda query, allowed_scopes, limit=4: [
            {
                "chunk_id": "hidden",
                "document_id": "hidden",
                "text": "Le site officiel présente l'histoire du groupe Jamain Baco.",
                "score": 4.0,
                "source_type": "official_web",
                "department_scope": "company_common",
                "title": "Histoire du groupe",
                "canonical_url": "https://jamainbaco.com/notre-histoire/",
                "source_domain": "jamainbaco.com",
            }
        ],
    )

    response = client.post(
        "/chat",
        json={"message": "c quoi l'histoire du groupe jamain baco"},
        headers=auth_headers("admin@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert data["technical"]["capability"] == "knowledge.enterprise_answer"
    assert data["technical"]["execution_mode"] == "retrieval_grounded"
    assert data["technical"]["tool_used"] == "knowledge_rag_retrieval"
    assert data["sources"][0]["source_type"] == "official_web"


def test_missing_parameters_return_clarification_without_execution(monkeypatch):
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda *args, **kwargs: semantic_classification(
            request_type="enterprise_action",
            domain="odoo",
            agent="odoo_agent",
            capability="odoo.product_price_update",
            execution_mode="tool",
            action="update_product_price",
            clarification_needed=True,
            missing_parameters=["new_price"],
        ),
    )
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: (_ for _ in ()).throw(
            AssertionError("Incomplete action must not execute Odoo")
        ),
    )

    response = client.post(
        "/chat",
        json={"message": "Modifier le prix de BACO CLEAN"},
        headers=auth_headers("admin@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "clarification_required"
    assert "new_price" in data["response"]
    assert data["technical"]["capability"] == "odoo.product_price_update"


def test_unknown_capability_returns_unsupported_without_execution(monkeypatch):
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    route = semantic_classification(
        request_type="enterprise_action",
        domain="odoo",
        agent="odoo_agent",
        capability="odoo.arbitrary_xmlrpc",
        execution_mode=None,
        action="unsupported_capability",
    )
    route["capability_validation_error"] = "Capability is not registered: odoo.arbitrary_xmlrpc"
    monkeypatch.setattr(app_module, "classify_message", lambda *args, **kwargs: route)
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: (_ for _ in ()).throw(
            AssertionError("Unknown capability must not execute Odoo")
        ),
    )

    response = client.post(
        "/chat",
        json={"message": "Exécute une méthode Odoo arbitraire"},
        headers=auth_headers("admin@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "unsupported"
    assert data["technical"]["capability"] == "odoo.arbitrary_xmlrpc"
