from fastapi.testclient import TestClient

import app as app_module
from app import app
from tests.auth_helpers import auth_headers


client = TestClient(app)


def fake_support_agent(message):
    return {
        "intent": "support",
        "agent": "support_agent",
        "parser_source": "support_fallback",
        "parsed_action": "troubleshoot_issue",
        "response": "Vérifier la connexion internet et l’URL utilisée.",
        "message": "Vérifier la connexion internet et l’URL utilisée.",
        "tool_used": "diagnose_odoo_access_issue",
        "result": {
            "title": "Problème d’accès à Odoo",
            "steps": [
                "Vérifier la connexion internet",
                "Vérifier l’URL utilisée",
                "Vérifier identifiant/mot de passe",
                "Tester navigation privée ou autre navigateur",
                "Vider cache/cookies",
                "Vérifier VPN ou réseau interne si nécessaire",
                "Vérifier si d’autres utilisateurs ont le même problème",
                "Contacter l’administrateur IT si le problème persiste",
            ],
            "escalation": "Contacter l’administrateur IT si le problème persiste.",
        },
    }


def test_odoo_access_problem_routes_to_support_agent(monkeypatch):
    monkeypatch.setattr(app_module, "run_support_agent", fake_support_agent)
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: (_ for _ in ()).throw(AssertionError("Should not route to Odoo")),
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    response = client.post(
        "/chat",
        json={"message": "Je n’arrive pas à accéder à Odoo, quelles étapes dois-je vérifier ?"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "support"
    assert data["agent"] == "support_agent"
    assert data["parsed_action"] == "troubleshoot_issue"
    assert data["requires_approval"] is False
    assert data["status"] == "completed"
    assert "Vérifier la connexion internet" in data["result"]["steps"]


def test_odoo_not_opening_routes_to_support_agent(monkeypatch):
    monkeypatch.setattr(app_module, "run_support_agent", fake_support_agent)
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: (_ for _ in ()).throw(AssertionError("Should not route to Odoo")),
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    response = client.post(
        "/chat",
        json={"message": "Odoo ne s’ouvre pas"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "support"
    assert data["agent"] == "support_agent"
    assert data["parsed_action"] == "troubleshoot_issue"


def test_stock_request_still_routes_to_odoo_agent(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: {
            "intent": "odoo",
            "agent": "odoo_agent",
            "parsed_action": "check_product_stock",
            "status": "completed",
        },
    )

    response = client.post(
        "/chat",
        json={"message": "Vérifier le stock de BACO CLEAN"},
        headers=auth_headers("viewer@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "odoo"
    assert data["agent"] == "odoo_agent"
    assert data["parsed_action"] == "check_product_stock"


def test_inventory_summary_routes_to_odoo_agent(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: {
            "intent": "odoo",
            "agent": "odoo_agent",
            "parsed_action": "inventory_summary",
            "status": "completed",
            "approval_required": False,
        },
    )

    response = client.post(
        "/chat",
        json={"message": "Combien de produits avons-nous en stock ?"},
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "odoo"
    assert data["agent"] == "odoo_agent"
    assert data["parsed_action"] == "inventory_summary"


def test_inventory_product_existence_question_routes_to_odoo_agent(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: {
            "intent": "odoo",
            "agent": "odoo_agent",
            "parsed_action": "inventory_product_search",
            "status": "completed",
            "approval_required": False,
        },
    )

    response = client.post(
        "/chat",
        json={
            "message": "Est-ce que des produits de nettoyage sont intégrés dans l’inventaire Odoo ?"
        },
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "odoo"
    assert data["agent"] == "odoo_agent"
    assert data["parsed_action"] == "inventory_product_search"
    assert data["approval_required"] is False


def test_invoice_details_request_still_routes_to_odoo_agent(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: {
            "intent": "odoo",
            "agent": "odoo_agent",
            "parsed_action": "document_details",
            "status": "completed",
        },
    )

    response = client.post(
        "/chat",
        json={"message": "Montre-moi les détails de la facture FNP/2026/04016"},
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "odoo"
    assert data["agent"] == "odoo_agent"
    assert data["parsed_action"] == "document_details"


def test_wifi_problem_routes_to_support_agent(monkeypatch):
    monkeypatch.setattr(app_module, "run_support_agent", fake_support_agent)
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    response = client.post(
        "/chat",
        json={"message": "J’ai un problème de connexion Wi-Fi"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "support"
    assert data["agent"] == "support_agent"
    assert data["parsed_action"] == "troubleshoot_issue"
    assert data["approval_required"] is False


def test_slow_computer_routes_to_support_agent(monkeypatch):
    monkeypatch.setattr(app_module, "run_support_agent", fake_support_agent)
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    response = client.post(
        "/chat",
        json={"message": "Mon ordinateur est lent"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "support"
    assert data["agent"] == "support_agent"
    assert data["parsed_action"] == "troubleshoot_issue"
    assert data["approval_required"] is False


def test_internal_server_list_routes_to_server_agent(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "run_server_agent",
        lambda message: {
            "intent": "server",
            "agent": "server_agent",
            "parser_source": "server_fallback",
            "parsed_action": "list_internal_files",
            "status": "completed",
            "message": "Fichiers listés.",
            "result": {"success": True, "files": []},
        },
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    response = client.post(
        "/chat",
        json={"message": "Liste les fichiers du serveur interne"},
        headers=auth_headers("it.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "server"
    assert data["agent"] == "server_agent"
    assert data["parsed_action"] == "list_internal_files"
    assert data["approval_required"] is False


def test_internal_server_create_routes_to_server_agent(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "run_server_agent",
        lambda message: {
            "intent": "server",
            "agent": "server_agent",
            "parser_source": "server_fallback",
            "parsed_action": "create_internal_file",
            "status": "completed",
            "message": "Fichier créé.",
            "result": {"success": True, "filename": "test-note.txt"},
        },
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    response = client.post(
        "/chat",
        json={
            "message": "Crée un fichier serveur nommé test-note.txt avec le contenu: Ceci est un test"
        },
        headers=auth_headers("it.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "server"
    assert data["agent"] == "server_agent"
    assert data["parsed_action"] == "create_internal_file"
    assert data["approval_required"] is False


def test_internal_server_env_path_is_blocked(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "run_server_agent",
        lambda message: {
            "intent": "server",
            "agent": "server_agent",
            "parser_source": "server_fallback",
            "parsed_action": "blocked_sensitive_path",
            "status": "blocked",
            "message": "Chemin refusé.",
            "result": {"success": False, "blocked": True, "message": "Chemin refusé."},
        },
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    response = client.post(
        "/chat",
        json={"message": "Lis le fichier serveur ../.env"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "sensitive_secret_request"
    assert data["agent"] == "security_agent"
    assert data["parsed_action"] == "block_request"
    assert data["risk_level"] == "blocked"
    assert data["approval_required"] is False


def test_frontend_sanitizes_sensitive_odoo_diagnostic_fields():
    source = open("frontend/app/chat/page.tsx", encoding="utf-8").read()

    assert "sanitizeForDisplay" in source
    assert "formatSafeOdooStatus" in source
    assert "NEXT_PUBLIC_CHAT_DEBUG" in source
    assert "SHOW_TECHNICAL_DETAILS &&" in source
    assert "Détails techniques" in source
    assert '<p className="eyebrow">Réponse</p>' not in source
    assert '<section className="decisionGrid">' not in source

    for key in [
        "url",
        "database",
        "username",
        "uid",
        "database_configured",
        "username_configured",
        "password_or_api_key_configured",
        "api_key",
        "password",
        "token",
        "secret",
    ]:
        assert f'"{key}"' in source
