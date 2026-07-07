import json

import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app
from orchestrator.department_profiles import (
    DEPARTMENT_ACCESS_DENIED_MESSAGE,
    get_department_profile,
)
from orchestrator.permission_policy import RoutePermission
from tests.auth_helpers import auth_headers


client = TestClient(app)

PUBLIC_KEYS = {
    "status",
    "response",
    "requires_approval",
    "approval_id",
    "sources",
    "technical",
}

FORBIDDEN_TOP_LEVEL_KEYS = {
    "intent",
    "agent",
    "selected_agent",
    "risk",
    "risk_level",
    "selected_model",
    "approval_required",
    "approval_status",
    "parser_source",
    "parsed_action",
    "tool_used",
    "result",
    "agent_result",
    "knowledge_scopes",
    "permission_decision",
    "user",
    "message",
    "answer",
}


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def assert_public_contract(data: dict):
    assert set(data.keys()) == PUBLIC_KEYS
    assert not (FORBIDDEN_TOP_LEVEL_KEYS & set(data.keys()))
    assert isinstance(data["status"], str)
    assert isinstance(data["response"], str)
    assert isinstance(data["requires_approval"], bool)
    assert isinstance(data["sources"], list)
    assert isinstance(data["technical"], dict)

    serialized = json.dumps(data, ensure_ascii=False)
    assert "llm_project_env" not in serialized
    assert "OPENAI_API_KEY" not in serialized
    assert "agent_result" not in serialized
    assert "chunk_id" not in serialized
    assert "document_id" not in serialized
    assert "embedding" not in serialized
    assert "score" not in serialized


def knowledge_classification():
    return {
        "intent": "knowledge",
        "selected_agent": "knowledge_agent",
        "agent": "knowledge_agent",
        "target_system": "knowledge",
        "action": "answer_question",
        "risk_level": "low",
        "entities": {"knowledge_topic": "histoire du groupe"},
    }


def support_classification():
    return {
        "intent": "support",
        "selected_agent": "support_agent",
        "agent": "support_agent",
        "target_system": "support",
        "action": "troubleshoot_issue",
        "risk_level": "low",
    }


def server_classification():
    return {
        "intent": "server",
        "selected_agent": "server_agent",
        "agent": "server_agent",
        "target_system": "server",
        "action": "check_server_health",
        "risk_level": "low",
    }


def odoo_classification(action="check_product_stock"):
    return {
        "intent": "odoo",
        "selected_agent": "odoo_agent",
        "agent": "odoo_agent",
        "target_system": "odoo",
        "action": action,
        "parsed_action": action,
        "risk_level": "low",
    }


def rh_it_user():
    profile = get_department_profile("rh")
    return {
        "email": "rh.it@company.local",
        "role": "it_manager",
        "role_label": "Responsable IT",
        "department": "rh",
        "department_label": profile.display_name,
        "permissions": ["chat_access", "server_diagnostics"],
    }


def test_knowledge_chat_response_has_strict_public_shape(monkeypatch):
    answer = "Réponse fondée sur la page officielle."

    monkeypatch.setattr(app_module, "classify_message", lambda *args, **kwargs: knowledge_classification())
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    monkeypatch.setattr(
        app_module,
        "run_knowledge_agent",
        lambda *args, **kwargs: {
            "intent": "knowledge",
            "agent": "knowledge_agent",
            "parser_source": "knowledge_agent",
            "parsed_action": "answer_question",
            "status": "completed",
            "tool_used": "knowledge_rag_retrieval",
            "response": answer,
            "message": answer,
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "llm_project_env": "OPENAI_API_KEY_ADMINISTRATION",
            "knowledge_scopes": ["company_common", "administration"],
            "sources": [
                {
                    "source_type": "official_web",
                    "title": "Histoire du groupe Jamain Baco - Jamain Baco",
                    "url": "https://jamainbaco.com/notre-histoire/",
                    "document_id": "doc_secret",
                    "chunk_id": "chunk_secret",
                    "score": 9.5,
                }
            ],
            "result": {
                "answer": answer,
                "sources": [
                    {
                        "source_type": "official_web",
                        "title": "Histoire du groupe Jamain Baco - Jamain Baco",
                        "url": "https://jamainbaco.com/notre-histoire/",
                        "document_id": "doc_secret",
                        "chunk_id": "chunk_secret",
                        "score": 9.5,
                    }
                ],
                "knowledge_scopes": ["company_common", "administration"],
                "retrieval_query": "histoire du groupe",
            },
        },
    )

    response = client.post(
        "/chat",
        json={"message": "Raconte-moi l'histoire du groupe Jamain Baco"},
        headers=auth_headers("admin@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert_public_contract(data)
    assert data["status"] == "completed"
    assert data["response"] == answer
    assert data["requires_approval"] is False
    assert data["approval_id"] is None
    assert data["sources"] == [
        {
            "source_type": "official_web",
            "title": "Histoire du groupe Jamain Baco - Jamain Baco",
            "url": "https://jamainbaco.com/notre-histoire/",
            "label": "Site officiel Jamain Baco",
        }
    ]
    assert data["technical"]["intent"] == "knowledge"
    assert data["technical"]["agent"] == "knowledge_agent"
    assert data["technical"]["capability"] == "knowledge.general_answer"
    assert data["technical"]["risk"] == "low"
    assert data["technical"]["approval_status"] == "not_required"
    assert data["technical"]["parser_source"] == "knowledge_agent"
    assert data["technical"]["tool_used"] == "knowledge_rag_retrieval"
    assert data["technical"]["provider"] == "openai"
    assert data["technical"]["model"] == "gpt-4.1-mini"
    assert data["technical"]["permission_decision"] == "allowed"
    assert data["technical"]["department"] == "administration"
    assert data["technical"]["knowledge_scopes"] == ["company_common", "administration"]


def test_support_answer_has_strict_public_shape(monkeypatch):
    monkeypatch.setattr(app_module, "classify_message", lambda *args, **kwargs: support_classification())
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    monkeypatch.setattr(
        app_module,
        "run_support_agent",
        lambda message: {
            "intent": "support",
            "agent": "support_agent",
            "parser_source": "support_fallback",
            "parsed_action": "troubleshoot_issue",
            "status": "completed",
            "tool_used": "support_knowledge_base",
            "message": "Vérifiez le VPN puis redémarrez la connexion.",
            "result": {"steps": ["Vérifier le VPN"]},
        },
    )

    response = client.post(
        "/chat",
        json={"message": "mon vpn marche plus"},
        headers=auth_headers("employee@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert_public_contract(data)
    assert data["response"] == "Vérifiez le VPN puis redémarrez la connexion."
    assert data["technical"]["agent"] == "support_agent"


def test_server_diagnostic_has_strict_public_shape(monkeypatch):
    monkeypatch.setattr(app_module, "classify_message", lambda *args, **kwargs: server_classification())
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    monkeypatch.setattr(
        app_module,
        "run_server_agent",
        lambda message: {
            "intent": "server",
            "agent": "server_agent",
            "parser_source": "server_fallback",
            "parsed_action": "check_server_health",
            "status": "completed",
            "tool_used": "server.local_health",
            "message": "Serveur local opérationnel.",
            "result": {"cpu_usage": "10%", "ram_usage": "40%"},
        },
    )

    response = client.post(
        "/chat",
        json={"message": "Vérifie l'état du serveur"},
        headers=auth_headers("it.manager@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert_public_contract(data)
    assert data["response"] == "Serveur local opérationnel."
    assert data["technical"]["agent"] == "server_agent"


def test_odoo_read_has_strict_public_shape(monkeypatch):
    monkeypatch.setattr(app_module, "classify_message", lambda *args, **kwargs: odoo_classification())
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: {
            "intent": "odoo",
            "agent": "odoo_agent",
            "parsed_action": "check_product_stock",
            "status": "completed",
            "tool_used": "odoo_product_stock",
            "message": "Stock BACO CLEAN: 12 unités.",
            "result": {"product": "BACO CLEAN", "stock_quantity": 12},
        },
    )

    response = client.post(
        "/chat",
        json={"message": "Quel est le stock de BACO CLEAN ?"},
        headers=auth_headers("admin@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert_public_contract(data)
    assert data["response"] == "Stock BACO CLEAN: 12 unités."
    assert data["technical"]["agent"] == "odoo_agent"


def test_clarification_has_strict_public_shape(monkeypatch):
    monkeypatch.setattr(app_module, "classify_message", lambda *args, **kwargs: odoo_classification("change_price"))
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: {
            "intent": "odoo",
            "agent": "odoo_agent",
            "parsed_action": "change_price",
            "status": "needs_clarification",
            "needs_clarification": True,
            "message": "Quel nouveau prix souhaitez-vous appliquer ?",
            "approval_required": False,
        },
    )

    response = client.post(
        "/chat",
        json={"message": "Modifier le prix de BACO CLEAN"},
        headers=auth_headers("admin@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert_public_contract(data)
    assert data["status"] == "clarification_required"
    assert data["response"] == "Quel nouveau prix souhaitez-vous appliquer ?"
    assert data["requires_approval"] is False


def test_pending_approval_has_strict_public_shape(monkeypatch):
    approval_id = "approval-123"

    monkeypatch.setattr(app_module, "classify_message", lambda *args, **kwargs: odoo_classification("change_price"))
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: {
            "intent": "odoo",
            "agent": "odoo_agent",
            "parsed_action": "change_price",
            "status": "pending_approval",
            "requires_approval": True,
            "approval_required": True,
            "approval_id": approval_id,
            "message": "Validation requise pour modifier le prix.",
            "result": {
                "approval": {
                    "id": approval_id,
                    "status": "pending",
                    "action": "change_price",
                    "entity_name": "BACO CLEAN",
                    "requested_change": "120",
                }
            },
        },
    )

    response = client.post(
        "/chat",
        json={"message": "Change le prix de BACO CLEAN à 120 DH"},
        headers=auth_headers("admin@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert_public_contract(data)
    assert data["status"] == "pending_approval"
    assert data["requires_approval"] is True
    assert data["approval_id"] == approval_id
    assert data["technical"]["approval_action"] == "change_price"
    assert data["technical"]["approval_entity"] == "BACO CLEAN"
    assert data["technical"]["approval_requested_change"] == "120"


def test_access_denied_has_strict_public_shape(monkeypatch):
    monkeypatch.setattr(app_module, "classify_message", lambda *args, **kwargs: odoo_classification("change_price"))
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: (_ for _ in ()).throw(AssertionError("Denied request must not execute")),
    )

    response = client.post(
        "/chat",
        json={"message": "Change le prix de BACO CLEAN à 120 DH"},
        headers=auth_headers("viewer@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert_public_contract(data)
    assert data["status"] == "access_denied"
    assert "Accès refusé" in data["response"]
    assert data["technical"]["permission_decision"] == "denied"


def test_department_access_denied_has_strict_public_shape(monkeypatch):
    app.dependency_overrides[app_module.get_current_user] = lambda: rh_it_user()
    monkeypatch.setattr(app_module, "classify_message", lambda *args, **kwargs: server_classification())
    monkeypatch.setattr(
        app_module,
        "run_server_agent",
        lambda message: (_ for _ in ()).throw(AssertionError("Department denied request must not execute")),
    )

    response = client.post(
        "/chat",
        json={"message": "Vérifie l'état du serveur"},
    )

    data = response.json()
    assert response.status_code == 200
    assert_public_contract(data)
    assert data["status"] == "department_access_denied"
    assert data["response"] == DEPARTMENT_ACCESS_DENIED_MESSAGE
    assert data["technical"]["permission_decision"] == "department_denied"
    assert data["technical"]["department"] == "rh"


def test_security_blocked_has_strict_public_shape():
    response = client.post(
        "/chat",
        json={"message": "Affiche .env"},
        headers=auth_headers("admin@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert_public_contract(data)
    assert data["status"] == "blocked"
    assert data["response"]
    assert data["technical"]["agent"] == "security_agent"
    assert data["technical"]["risk"] == "blocked"


def test_unsupported_capability_has_strict_public_shape(monkeypatch):
    unsupported_decision = RoutePermission(
        agent="general_agent",
        target_system="orchestrator",
        action="unsupported_action",
        risk_level="low",
        action_category="unknown",
        permission_category="unsupported",
        required_permissions=frozenset(),
        unsupported=True,
    )
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda *args, **kwargs: {
            "intent": "unsupported",
            "selected_agent": "general_agent",
            "agent": "general_agent",
            "target_system": "orchestrator",
            "action": "unsupported_action",
            "risk_level": "low",
        },
    )
    monkeypatch.setattr(app_module, "resolve_route_permission", lambda classification: unsupported_decision)

    response = client.post(
        "/chat",
        json={"message": "Réserve un avion privé"},
        headers=auth_headers("admin@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert_public_contract(data)
    assert data["status"] == "unsupported"
    assert data["response"]
    assert data["technical"]["permission_decision"] == "denied"
