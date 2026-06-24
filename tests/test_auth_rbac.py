from fastapi.testclient import TestClient

import app as app_module
from app import app
from tests.auth_helpers import auth_headers


client = TestClient(app)


def test_login_success():
    response = client.post(
        "/auth/login",
        json={
            "email": "admin@company.local",
            "password": "admin123",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"]
    assert data["user"]["email"] == "admin@company.local"
    assert data["user"]["role"] == "admin"
    assert data["user"]["role_label"] == "Administrateur"
    assert "all" in data["user"]["permissions"]


def test_login_failure():
    response = client.post(
        "/auth/login",
        json={
            "email": "admin@company.local",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Identifiants incorrects."


def test_unauthenticated_chat_rejected():
    response = client.post(
        "/chat",
        json={"message": "Je n’arrive pas à accéder à Odoo"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentification requise."


def test_employee_cannot_access_server_diagnostics():
    response = client.post(
        "/chat",
        json={"message": "Vérifie l’état des serveurs"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "access_denied"
    assert data["message"] == "Accès refusé : votre rôle ne permet pas d’effectuer cette action."


def test_employee_cannot_request_odoo_write():
    response = client.post(
        "/chat",
        json={"message": "Modifier le prix de BACO TOP à 4 DH"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "access_denied"
    assert data["message"] == "Accès refusé : votre rôle ne permet pas d’effectuer cette action."


def test_employee_can_ask_support_question(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "run_support_agent",
        lambda message: {
            "intent": "support",
            "agent": "support_agent",
            "parsed_action": "troubleshoot_issue",
            "tool_used": "support_knowledge_base",
            "status": "completed",
            "message": "Diagnostic support généré.",
            "result": {"steps": ["Vérifier la connexion."]},
        },
    )

    response = client.post(
        "/chat",
        json={"message": "Je n’arrive pas à accéder à Odoo"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "support_agent"
    assert data["status"] == "completed"


def test_readonly_viewer_can_read_limited_odoo_product_info(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: {
            "intent": "odoo",
            "agent": "odoo_agent",
            "parsed_action": "check_product_stock",
            "tool_used": "odoo_check_stock",
            "status": "completed",
            "approval_required": False,
            "requires_approval": False,
            "message": "Données produit consultées avec succès.",
        },
    )

    response = client.post(
        "/chat",
        json={"message": "Vérifier le stock de BACO CLEAN"},
        headers=auth_headers("viewer@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "odoo_agent"
    assert data["status"] == "completed"


def test_odoo_manager_can_request_write_but_still_requires_approval(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: {
            "intent": "odoo",
            "agent": "odoo_agent",
            "parsed_action": "update_product_price",
            "status": "pending_approval",
            "approval_required": True,
            "requires_approval": True,
            "message": "Cette action nécessite une validation humaine avant exécution dans Odoo.",
        },
    )

    response = client.post(
        "/chat",
        json={"message": "Modifier le prix de BACO TOP à 4 DH"},
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "odoo_agent"
    assert data["approval_required"] is True
    assert data["status"] == "pending_approval"


def test_it_manager_can_access_server_diagnostics():
    response = client.post(
        "/chat",
        json={"message": "Vérifie l’état des serveurs"},
        headers=auth_headers("it.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "server_agent"
    assert data["status"] == "completed"


def test_admin_can_access_logs_and_approvals():
    headers = auth_headers("admin@company.local")

    logs_response = client.get("/logs", headers=headers)
    approvals_response = client.get("/approvals", headers=headers)

    assert logs_response.status_code == 200
    assert approvals_response.status_code == 200
