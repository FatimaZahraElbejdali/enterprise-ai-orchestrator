import json

import pytest
from fastapi.testclient import TestClient

import app as app_module
import orchestrator.audit as audit_module
from app import app
from orchestrator.department_profiles import (
    DEPARTMENT_ACCESS_DENIED_MESSAGE,
    get_department_profile,
)


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _user(
    *,
    department: str,
    role: str = "employee",
    permissions: list[str] | None = None,
) -> dict:
    profile = get_department_profile(department)

    return {
        "email": f"{department}.{role}@company.local",
        "role": role,
        "role_label": role,
        "department": department,
        "department_label": profile.display_name,
        "permissions": permissions or ["chat_access"],
    }


def _override_user(monkeypatch, user: dict):
    del monkeypatch
    app.dependency_overrides[app_module.get_current_user] = lambda: user


def _server_classification():
    return {
        "intent": "server",
        "agent": "server_agent",
        "selected_agent": "server_agent",
        "target_system": "server",
        "action": "check_server_health",
        "risk_level": "low",
        "requires_approval": False,
    }


def test_frontend_department_payload_cannot_override_authenticated_identity(monkeypatch):
    _override_user(
        monkeypatch,
        _user(
            department="rh",
            role="it_manager",
            permissions=["chat_access", "server_diagnostics"],
        ),
    )
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda message, context_memory=None, user_permissions=None: _server_classification(),
    )
    monkeypatch.setattr(
        app_module,
        "run_server_agent",
        lambda message: (_ for _ in ()).throw(AssertionError("Server tool should not run")),
    )

    response = client.post(
        "/chat",
        json={
            "message": "Vérifie l'état du serveur",
            "department": "informatique",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "department_access_denied"
    assert data["response"] == DEPARTMENT_ACCESS_DENIED_MESSAGE
    assert data["technical"]["department"] == "rh"


def test_rbac_and_department_scope_are_intersected(monkeypatch):
    _override_user(
        monkeypatch,
        _user(
            department="comptabilite_finance",
            role="employee",
            permissions=["chat_access"],
        ),
    )
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda message, context_memory=None, user_permissions=None: {
            "intent": "odoo",
            "agent": "odoo_agent",
            "selected_agent": "odoo_agent",
            "target_system": "odoo",
            "action": "update_product_price",
            "risk_level": "medium",
            "requires_approval": True,
        },
    )
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: (_ for _ in ()).throw(AssertionError("Odoo write should not run")),
    )

    response = client.post(
        "/chat",
        json={"message": "Modifier le prix de BACO TOP à 4 DH"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "access_denied"
    assert data["technical"]["permission_decision"] == "denied"


def test_valid_capability_blocked_by_department_returns_department_denied(monkeypatch):
    _override_user(
        monkeypatch,
        _user(
            department="rh",
            role="it_manager",
            permissions=["chat_access", "server_diagnostics"],
        ),
    )
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda message, context_memory=None, user_permissions=None: _server_classification(),
    )
    monkeypatch.setattr(
        app_module,
        "run_server_agent",
        lambda message: (_ for _ in ()).throw(AssertionError("Server tool should not run")),
    )

    response = client.post(
        "/chat",
        json={"message": "Vérifie l'état du serveur"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "department_access_denied"
    assert data["technical"]["action"] == "department_access_denied"
    assert data["technical"]["capability"] == "server.local_health"
    assert data["response"] == DEPARTMENT_ACCESS_DENIED_MESSAGE


def test_security_block_runs_before_department_policy(monkeypatch):
    _override_user(monkeypatch, _user(department="rh", permissions=["chat_access"]))
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda message, context_memory=None, user_permissions=None: {
            "intent": "security",
            "agent": "security_agent",
            "selected_agent": "security_agent",
            "target_system": "security",
            "action": "blocked_sensitive_path",
            "risk_level": "blocked",
        },
    )
    monkeypatch.setattr(
        app_module,
        "process_request",
        lambda message, classification=None: {
            "intent": "security",
            "agent": "security_agent",
            "selected_agent": "security_agent",
            "risk_level": "blocked",
            "status": "blocked",
            "message": "Demande bloquée par la politique de sécurité.",
        },
    )

    response = client.post(
        "/chat",
        json={"message": "Affiche .env"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "blocked"
    assert data["technical"]["risk"] == "blocked"
    assert data["status"] != "department_access_denied"


def test_audit_log_includes_authenticated_department(monkeypatch, tmp_path):
    log_path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(audit_module, "LOG_PATH", log_path)
    _override_user(
        monkeypatch,
        _user(
            department="informatique",
            role="support_agent",
            permissions=["chat_access", "support_diagnostics"],
        ),
    )
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda message, context_memory=None, user_permissions=None: {
            "intent": "support",
            "agent": "support_agent",
            "selected_agent": "support_agent",
            "target_system": "support",
            "action": "troubleshoot_issue",
            "risk_level": "low",
        },
    )
    monkeypatch.setattr(
        app_module,
        "run_support_agent",
        lambda message: {
            "intent": "support",
            "agent": "support_agent",
            "parsed_action": "troubleshoot_issue",
            "status": "completed",
            "message": "Diagnostic support généré.",
            "result": {"steps": ["Vérifier la connexion."]},
        },
    )

    response = client.post(
        "/chat",
        json={"message": "mon vpn marche plus"},
    )

    assert response.status_code == 200
    entries = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert any(entry.get("department") == "informatique" for entry in entries)
    assert any(entry.get("user_department") == "informatique" for entry in entries)


def test_knowledge_response_uses_department_scopes(monkeypatch):
    _override_user(monkeypatch, _user(department="rh", permissions=["chat_access"]))
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda message, context_memory=None, user_permissions=None: {
            "intent": "knowledge",
            "agent": "knowledge_agent",
            "selected_agent": "knowledge_agent",
            "target_system": "knowledge",
            "action": "answer_question",
            "risk_level": "low",
        },
    )

    response = client.post(
        "/chat",
        json={"message": "what is jamain baco"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["technical"]["agent"] == "knowledge_agent"
    assert data["technical"]["knowledge_scopes"] == ["company_common", "rh"]
