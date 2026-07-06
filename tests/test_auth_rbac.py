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


def test_employee_company_question_returns_static_context():
    response = client.post(
        "/chat",
        json={"message": "what is jamain baco"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "knowledge_agent"
    assert data["status"] == "completed"
    assert data["approval_required"] is False
    assert "Jamain Baco est l'entreprise" in data["message"]
    assert "développé et testé" in data["message"]
    assert "action n’est pas encore disponible" not in data["message"]
    assert "Knowledge Agent received" not in data["message"]
    assert "No specific tool matched" not in data["message"]


def test_employee_french_company_question_returns_static_context():
    response = client.post(
        "/chat",
        json={"message": "c’est quoi Jamain Baco ?"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "knowledge_agent"
    assert data["status"] == "completed"
    assert "Jamain Baco est l'entreprise" in data["message"]


def test_public_knowledge_question_uses_llm(monkeypatch):
    generated_answer = "Réponse publique générée par le LLM de test."
    monkeypatch.setattr(
        "agents.knowledge_agent.is_openai_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "agents.knowledge_agent.generate_response",
        lambda prompt, system_prompt=None: {
            "provider": "openai",
            "model": "test-model",
            "success": True,
            "content": generated_answer,
            "error": None,
        },
    )

    response = client.post(
        "/chat",
        json={"message": "où se situe le Maroc ?"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "knowledge_agent"
    assert data["status"] == "completed"
    assert data["approval_required"] is False
    assert data["message"]
    assert data["message"] == generated_answer
    assert data["message"] != (
        "Je n'ai pas encore suffisamment d'informations internes pour répondre "
        "précisément à cette question."
    )
    assert data["selected_model"]["provider"] == "openai"
    assert data["selected_model"]["model"] == "test-model"


def test_general_advice_question_uses_llm_not_internal_docs(monkeypatch):
    generated_answer = "Conseil généré par le LLM de test."
    calls = []

    monkeypatch.setattr(
        "agents.knowledge_agent.is_openai_configured",
        lambda: True,
    )

    def fake_generate_response(prompt, system_prompt=None):
        calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return {
            "provider": "openai",
            "model": "test-model",
            "success": True,
            "content": generated_answer,
            "error": None,
        }

    monkeypatch.setattr(
        "agents.knowledge_agent.generate_response",
        fake_generate_response,
    )

    response = client.post(
        "/chat",
        json={
            "message": (
                "Quels conseils donnerais-tu pour améliorer une présentation "
                "d’un projet d’orchestrateur IA ?"
            )
        },
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "knowledge_agent"
    assert data["status"] == "completed"
    assert data["approval_required"] is False
    assert data["message"] == generated_answer
    assert data["message"] != (
        "Je n'ai pas encore suffisamment d'informations internes pour répondre "
        "précisément à cette question."
    )
    assert data["tool_used"] == "public_llm_answer"
    assert data["selected_model"]["provider"] == "openai"
    assert len(calls) == 1


def test_unknown_company_details_are_answered_carefully():
    response = client.post(
        "/chat",
        json={"message": "who is the CEO of Jamain Baco?"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "knowledge_agent"
    assert data["message"] == (
        "Je n'ai pas encore suffisamment d'informations internes pour répondre "
        "précisément à cette question."
    )


def test_public_general_definition_uses_llm(monkeypatch):
    generated_answer = "Réponse conceptuelle générée par le LLM de test."
    calls = []

    monkeypatch.setattr(
        "agents.knowledge_agent.is_openai_configured",
        lambda: True,
    )

    def fake_generate_response(prompt, system_prompt=None):
        calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return {
            "provider": "openai",
            "model": "test-model",
            "success": True,
            "content": generated_answer,
            "error": None,
        }

    monkeypatch.setattr(
        "agents.knowledge_agent.generate_response",
        fake_generate_response,
    )

    for prompt in ["qu’est-ce qu’un ERP ?", "what is an API?"]:
        response = client.post(
            "/chat",
            json={"message": prompt},
            headers=auth_headers("employee@company.local"),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["agent"] == "knowledge_agent"
        assert data["message"] == generated_answer
        assert "Knowledge Agent received" not in data["message"]
        assert "No specific tool matched" not in data["message"]
        assert "knowledge_agent" not in data["message"]
        assert "public_llm_answer" not in data["message"]

    assert len(calls) == 2


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


def test_unknown_odoo_action_does_not_execute_tools(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda message, context_memory=None, user_permissions=None: {
            "intent": "odoo",
            "agent": "odoo_agent",
            "selected_agent": "odoo_agent",
            "target_system": "odoo",
            "action": "unknown",
            "risk_level": "low",
            "requires_approval": False,
        },
    )
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: (_ for _ in ()).throw(AssertionError("Odoo tool execution should be blocked")),
    )

    response = client.post(
        "/chat",
        json={"message": "Fais une action Odoo non définie"},
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unsupported"
    assert data["tool_used"] is None
