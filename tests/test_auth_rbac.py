from fastapi.testclient import TestClient

import app as app_module
from app import app
from orchestrator.approval_store import get_approvals
from tests.auth_helpers import auth_headers
from tests.semantic_helpers import make_semantic_request


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
    assert data["user"]["department"] == "administration"
    assert data["user"]["department_label"] == "Administration"
    assert "all" in data["user"]["permissions"]


def test_login_returns_demo_user_department():
    response = client.post(
        "/auth/login",
        json={
            "email": "it.manager@company.local",
            "password": "it123",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user"]["role"] == "it_manager"
    assert data["user"]["department"] == "informatique"
    assert data["user"]["department_label"] == "Informatique"


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
    assert data["response"] == "Accès refusé : votre rôle ne permet pas d’effectuer cette action."


def _price_update_semantic_route():
    return make_semantic_request(
        request_type="enterprise_action",
        domain="odoo",
        capability="odoo.product_price_update",
        agent="odoo_agent",
        action="update_product_price",
        execution_mode="tool",
        risk_level="medium",
        requires_approval=True,
        entities={"product_name": "BACO TOP"},
        parameters={"new_price": 4},
    )


def _company_knowledge_semantic_route(topic="Jamain Baco"):
    return make_semantic_request(
        request_type="enterprise_knowledge",
        domain="knowledge",
        capability="knowledge.enterprise_answer",
        agent="knowledge_agent",
        action="enterprise_answer",
        execution_mode="retrieval_grounded",
        risk_level="low",
        requires_approval=False,
        topic=topic,
    )


def _official_company_chunk(text=None):
    return {
        "chunk_id": "hidden_chunk",
        "document_id": "hidden_doc",
        "text": text
        or (
            "Jamain Baco est présenté par la source officielle comme un groupe "
            "avec une histoire, des activités et des équipes."
        ),
        "score": 4.0,
        "source_type": "official_web",
        "department_scope": "company_common",
        "title": "Histoire du groupe Jamain Baco",
        "canonical_url": "https://jamainbaco.com/notre-histoire/",
        "source_domain": "jamainbaco.com",
    }


def test_employee_cannot_request_odoo_write(monkeypatch):
    before_approval_ids = {item.get("id") for item in get_approvals()}
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda message, context_memory=None, user_permissions=None: _price_update_semantic_route(),
    )
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda message: (_ for _ in ()).throw(
            AssertionError("Unauthorized Odoo write must not reach approval/tool handling")
        ),
    )

    response = client.post(
        "/chat",
        json={"message": "Modifier le prix de BACO TOP à 4 DH"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "access_denied"
    assert data["response"] == "Accès refusé : votre rôle ne permet pas d’effectuer cette action."
    assert data["requires_approval"] is False
    assert data["approval_id"] is None
    assert data["technical"]["capability"] == "odoo.product_price_update"
    assert {item.get("id") for item in get_approvals()} == before_approval_ids


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
    assert data["technical"]["agent"] == "support_agent"
    assert data["status"] == "completed"


def test_employee_company_question_uses_enterprise_knowledge_rag(monkeypatch):
    calls = []
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda message, context_memory=None, user_permissions=None: _company_knowledge_semantic_route(
            "Jamain Baco"
        ),
    )
    monkeypatch.setattr(
        "agents.knowledge_agent.is_openai_configured",
        lambda *args, **kwargs: False,
    )

    def fake_search(query, allowed_scopes, limit=4):
        calls.append({
            "query": query,
            "allowed_scopes": allowed_scopes,
            "limit": limit,
        })
        return [_official_company_chunk()]

    monkeypatch.setattr(
        "agents.knowledge_agent.search_knowledge",
        fake_search,
    )

    response = client.post(
        "/chat",
        json={"message": "what is jamain baco"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["technical"]["agent"] == "knowledge_agent"
    assert data["technical"]["capability"] == "knowledge.enterprise_answer"
    assert data["technical"]["execution_mode"] == "retrieval_grounded"
    assert data["technical"]["tool_used"] == "knowledge_rag_retrieval"
    assert data["status"] == "completed"
    assert data["requires_approval"] is False
    assert "source officielle" in data["response"]
    assert "Jamain Baco" in data["response"]
    assert data["sources"] == [
        {
            "source_type": "official_web",
            "title": "Histoire du groupe Jamain Baco",
            "url": "https://jamainbaco.com/notre-histoire/",
            "label": "Site officiel Jamain Baco",
        }
    ]
    assert calls[0]["allowed_scopes"][0] == "company_common"
    assert "action n’est pas encore disponible" not in data["response"]
    assert "Knowledge Agent received" not in data["response"]
    assert "No specific tool matched" not in data["response"]


def test_employee_french_company_question_uses_enterprise_knowledge_rag(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda message, context_memory=None, user_permissions=None: _company_knowledge_semantic_route(
            "Jamain Baco"
        ),
    )
    monkeypatch.setattr(
        "agents.knowledge_agent.is_openai_configured",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "agents.knowledge_agent.search_knowledge",
        lambda query, allowed_scopes, limit=4: [_official_company_chunk()],
    )

    response = client.post(
        "/chat",
        json={"message": "c’est quoi Jamain Baco ?"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["technical"]["agent"] == "knowledge_agent"
    assert data["technical"]["capability"] == "knowledge.enterprise_answer"
    assert data["status"] == "completed"
    assert "Jamain Baco" in data["response"]
    assert data["sources"][0]["source_type"] == "official_web"


def test_employee_company_question_without_rag_context_is_careful(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda message, context_memory=None, user_permissions=None: _company_knowledge_semantic_route(
            "Jamain Baco"
        ),
    )
    monkeypatch.setattr(
        "agents.knowledge_agent.search_knowledge",
        lambda query, allowed_scopes, limit=4: [],
    )

    response = client.post(
        "/chat",
        json={"message": "what is jamain baco"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["technical"]["capability"] == "knowledge.enterprise_answer"
    assert data["technical"]["execution_mode"] == "retrieval_grounded"
    assert data["response"] == (
        "Je n'ai pas encore suffisamment d'informations internes pour répondre "
        "précisément à cette question."
    )
    assert data["sources"] == []


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
    assert data["technical"]["agent"] == "knowledge_agent"
    assert data["status"] == "completed"
    assert data["requires_approval"] is False
    assert data["response"]
    assert data["response"] == generated_answer
    assert data["response"] != (
        "Je n'ai pas encore suffisamment d'informations internes pour répondre "
        "précisément à cette question."
    )
    assert data["technical"]["provider"] == "openai"
    assert data["technical"]["model"] == "test-model"


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
    assert data["technical"]["agent"] == "knowledge_agent"
    assert data["status"] == "completed"
    assert data["requires_approval"] is False
    assert data["response"] == generated_answer
    assert data["response"] != (
        "Je n'ai pas encore suffisamment d'informations internes pour répondre "
        "précisément à cette question."
    )
    assert data["sources"] == []
    assert data["technical"]["tool_used"] in {
        "public_llm_answer",
        "knowledge_creative_generation",
    }
    assert data["technical"]["provider"] == "openai"
    assert len(calls) == 1


def test_harmless_general_input_uses_direct_llm_without_internal_sources(monkeypatch):
    generated_answer = "Réponse conversationnelle générée par le LLM de test."
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
        json={"message": "Just checking in."},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["response"] == generated_answer
    assert data["requires_approval"] is False
    assert data["approval_id"] is None
    assert data["sources"] == []
    assert data["technical"]["agent"] == "knowledge_agent"
    assert data["technical"]["domain"] == "knowledge"
    assert data["technical"]["execution_mode"] == "llm_direct"
    assert data["technical"]["tool_used"] == "public_llm_answer"
    assert data["technical"]["provider"] == "openai"
    assert len(calls) == 1


def test_unsupported_backend_action_still_does_not_execute(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "run_server_agent",
        lambda message: (_ for _ in ()).throw(
            AssertionError("Unsupported server resource action must not execute")
        ),
    )

    response = client.post(
        "/chat",
        json={"message": "Create an internal server file"},
        headers=auth_headers("admin@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unsupported"
    assert data["requires_approval"] is False
    assert data["technical"]["agent"] == "server_agent"
    assert data["technical"]["capability"] == "unsupported_capability"
    assert data["technical"].get("tool_used") is None


def test_unknown_company_details_are_answered_carefully():
    response = client.post(
        "/chat",
        json={"message": "who is the CEO of Jamain Baco?"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["technical"]["agent"] == "knowledge_agent"
    assert data["response"] == (
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
        assert data["technical"]["agent"] == "knowledge_agent"
        assert data["response"] == generated_answer
        assert "Knowledge Agent received" not in data["response"]
        assert "No specific tool matched" not in data["response"]
        assert "knowledge_agent" not in data["response"]
        assert "public_llm_answer" not in data["response"]

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
    assert data["technical"]["agent"] == "odoo_agent"
    assert data["status"] == "completed"


def test_chat_odoo_connection_status_uses_odoo_status_capability(monkeypatch):
    captured = {}

    def fake_run_odoo_agent(message, classification=None):
        captured["classification"] = classification
        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "selected_agent": "odoo_agent",
            "parsed_action": "odoo_status",
            "tool_used": "odoo_test_connection",
            "target_system": "odoo",
            "capability": "odoo.connection_status",
            "status": "completed",
            "approval_required": False,
            "requires_approval": False,
            "message": "Odoo est connecté.",
            "result": {"connected": True, "mode": "real_odoo"},
        }

    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    response = client.post(
        "/chat",
        json={"message": "Est-ce que Odoo est connecté ?"},
        headers=auth_headers("viewer@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["technical"]["agent"] == "odoo_agent"
    assert data["technical"]["capability"] == "odoo.connection_status"
    assert captured["classification"]["capability"] == "odoo.connection_status"
    assert "connecté" in data["response"]


def test_orchestrator_role_explanation_uses_direct_knowledge_not_rag(monkeypatch):
    calls = []

    def fake_generate_response(prompt, system_prompt=None, **kwargs):
        calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return {
            "success": True,
            "response": "L’orchestrateur IA aide à router les demandes et à appliquer les contrôles internes.",
            "provider": "openai",
            "model": "gpt-test",
            "error": None,
        }

    monkeypatch.setattr("agents.knowledge_agent.is_openai_configured", lambda: True)
    monkeypatch.setattr("agents.knowledge_agent.generate_response", fake_generate_response)
    monkeypatch.setattr(
        "agents.knowledge_agent.search_knowledge",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("project role explanation must not use RAG retrieval")
        ),
    )

    response = client.post(
        "/chat",
        json={"message": "C’est quoi le rôle de l’orchestrateur IA ?"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["technical"]["agent"] == "knowledge_agent"
    assert data["technical"]["capability"] == "knowledge.general_answer"
    assert data["technical"]["execution_mode"] == "llm_direct"
    assert data["sources"] == []
    assert calls


def test_odoo_manager_can_request_write_but_still_requires_approval(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda message, context_memory=None, user_permissions=None: _price_update_semantic_route(),
    )
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
            "approval_id": "approval-test-id",
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
    assert data["technical"]["agent"] == "odoo_agent"
    assert data["technical"]["capability"] == "odoo.product_price_update"
    assert data["technical"]["execution_mode"] == "tool"
    assert data["requires_approval"] is True
    assert data["approval_id"] == "approval-test-id"
    assert data["status"] == "pending_approval"


def test_it_manager_can_access_server_diagnostics():
    response = client.post(
        "/chat",
        json={"message": "Vérifie l’état des serveurs"},
        headers=auth_headers("it.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["technical"]["agent"] == "server_agent"
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
    assert data["technical"].get("tool_used") is None
