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
    assert data["technical"]["intent"] == "support"
    assert data["technical"]["agent"] == "support_agent"
    assert data["technical"]["action"] == "troubleshoot_issue"
    assert data["requires_approval"] is False
    assert data["status"] == "completed"
    assert "Vérifier la connexion internet" in data["response"]


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
    assert data["technical"]["intent"] == "support"
    assert data["technical"]["agent"] == "support_agent"
    assert data["technical"]["action"] == "troubleshoot_issue"


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
    assert data["technical"]["intent"] == "odoo"
    assert data["technical"]["agent"] == "odoo_agent"
    assert data["technical"]["action"] == "check_product_stock"


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
    assert data["technical"]["intent"] == "odoo"
    assert data["technical"]["agent"] == "odoo_agent"
    assert data["technical"]["action"] == "inventory_summary"


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
    assert data["technical"]["intent"] == "odoo"
    assert data["technical"]["agent"] == "odoo_agent"
    assert data["technical"]["action"] == "inventory_product_search"
    assert data["requires_approval"] is False


def test_generic_odoo_area_question_invokes_read_agent(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    def fake_run_odoo_agent(message, classification=None):
        captured["message"] = message
        captured["classification"] = classification
        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "completed",
            "message": "Lecture Odoo générique appelée.",
            "tool_used": "odoo_read_agent",
            "target_system": "odoo",
            "requires_approval": False,
            "approval_required": False,
        }

    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)

    response = client.post(
        "/chat",
        json={"message": "What is available in the generic business area section in Odoo?"},
        headers=auth_headers("admin@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    classification = captured["classification"]
    assert data["status"] == "completed"
    assert classification["selected_agent"] == "odoo_agent"
    assert classification["capability"] == "odoo.generic_read"
    assert classification["action"] == "odoo_generic_read"
    assert data["technical"]["tool_used"] == "odoo_read_agent"


def test_generic_odoo_concept_information_invokes_read_agent(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    def fake_run_odoo_agent(message, classification=None):
        captured["classification"] = classification
        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "completed",
            "message": "Lecture Odoo générique appelée.",
            "tool_used": "odoo_read_agent",
            "target_system": "odoo",
            "requires_approval": False,
            "approval_required": False,
        }

    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)

    response = client.post(
        "/chat",
        json={"message": "Show me information about generic business concept in Odoo"},
        headers=auth_headers("admin@company.local"),
    )

    assert response.status_code == 200
    classification = captured["classification"]
    assert classification["capability"] == "odoo.generic_read"
    assert classification["parameters"]["operation"] == "list"


def test_write_like_generic_odoo_request_does_not_enter_read_loop(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.classifier_router.classify_with_openai_router",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("write-like request should not use the generic read loop")
        ),
    )

    response = client.post(
        "/chat",
        json={"message": "Update the generic business concept in Odoo"},
        headers=auth_headers("viewer@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["technical"]["capability"] != "odoo.generic_read"
    assert data["technical"]["permission_decision"] in {"denied", "department_denied"}


def _unknown_odoo_read_route(capability="odoo.unknown_business_read"):
    return {
        "intent": "unsupported_capability",
        "request_type": "enterprise_action",
        "domain": "odoo",
        "target_system": "odoo",
        "selected_agent": "odoo_agent",
        "agent": "odoo_agent",
        "capability": capability,
        "execution_mode": None,
        "action": "unsupported_capability",
        "risk_level": "low",
        "risk": "low",
        "requires_approval": False,
        "approval_required": False,
        "entities": {"business_object": "unknown business area"},
        "parameters": {
            "operation": "describe",
            "business_object": "unknown business area",
            "limit": 10,
        },
        "semantic_request": {
            "request_type": "enterprise_action",
            "domain": "odoo",
            "capability": capability,
            "requires_internal_context": False,
            "topic": None,
            "entities": {"business_object": "unknown business area"},
            "parameters": {
                "operation": "describe",
                "business_object": "unknown business area",
                "limit": 10,
            },
            "clarification_needed": False,
            "missing_parameters": [],
        },
        "confidence": "high",
        "classifier_source": "openai_structured",
        "semantic_source": "openai_structured",
        "capability_validation_error": (
            f"Capability is not registered: {capability}" if capability else None
        ),
    }


def test_unknown_odoo_read_capability_falls_through_to_generic_agent(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda *args, **kwargs: _unknown_odoo_read_route(),
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    def fake_run_odoo_agent(message, classification=None):
        captured["classification"] = classification
        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "completed",
            "message": "Lecture Odoo générique appelée.",
            "tool_used": "odoo_read_agent",
            "target_system": "odoo",
            "requires_approval": False,
            "approval_required": False,
        }

    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)

    response = client.post(
        "/chat",
        json={"message": "What is available in the unknown business area section in Odoo?"},
        headers=auth_headers("admin@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "completed"
    assert captured["classification"]["capability"] == "odoo.generic_read"
    assert captured["classification"]["action"] == "odoo_generic_read"
    assert data["technical"]["capability"] == "odoo.generic_read"
    assert data["technical"]["tool_used"] == "odoo_read_agent"


def test_null_odoo_read_capability_falls_through_to_generic_agent(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda *args, **kwargs: _unknown_odoo_read_route(capability=None),
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    def fake_run_odoo_agent(message, classification=None):
        captured["classification"] = classification
        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "completed",
            "message": "Lecture Odoo générique appelée.",
            "tool_used": "odoo_read_agent",
            "target_system": "odoo",
            "requires_approval": False,
            "approval_required": False,
        }

    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)

    response = client.post(
        "/chat",
        json={"message": "Show me information about unknown business concept in Odoo"},
        headers=auth_headers("admin@company.local"),
    )

    assert response.status_code == 200
    assert captured["classification"]["capability"] == "odoo.generic_read"


def test_structured_odoo_write_semantics_do_not_use_generic_read(monkeypatch):
    route = _unknown_odoo_read_route(capability=None)
    route["parameters"] = {
        "operation": "update",
        "business_object": "unknown business area",
        "field": "status",
        "new_value": "done",
    }
    route["semantic_request"]["parameters"] = dict(route["parameters"])

    monkeypatch.setattr(app_module, "classify_message", lambda *args, **kwargs: route)
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("write-like request should not use generic read")
        ),
    )

    response = client.post(
        "/chat",
        json={"message": "Update the unknown business area in Odoo"},
        headers=auth_headers("admin@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert data["technical"]["capability"] != "odoo.generic_read"


def test_non_odoo_unknown_request_does_not_use_generic_odoo_read(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda *args, **kwargs: {
            "intent": "unsupported_capability",
            "request_type": "enterprise_action",
            "domain": "general",
            "target_system": "general",
            "selected_agent": "general_agent",
            "agent": "general_agent",
            "capability": None,
            "action": "unsupported_capability",
            "risk_level": "low",
            "requires_approval": False,
            "entities": {"business_object": "unknown business area"},
            "parameters": {"operation": "describe", "business_object": "unknown business area"},
        },
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("non-Odoo request should not use Odoo")
        ),
    )

    response = client.post(
        "/chat",
        json={"message": "What is available in the unknown business area?"},
        headers=auth_headers("admin@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert data["technical"]["capability"] != "odoo.generic_read"


def test_department_denial_still_blocks_unknown_odoo_read(monkeypatch):
    called = {"value": False}

    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda *args, **kwargs: _unknown_odoo_read_route(capability=None),
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    def fake_run_odoo_agent(*args, **kwargs):
        called["value"] = True
        return {"status": "completed", "message": "should not run"}

    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)

    response = client.post(
        "/chat",
        json={"message": "Show me information about unknown business concept in Odoo"},
        headers=auth_headers("support@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert data["status"] in {"department_access_denied", "denied"}
    assert called["value"] is False


def test_specialized_odoo_capability_is_preserved(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda *args, **kwargs: {
            "intent": "product_stock_check",
            "request_type": "enterprise_action",
            "domain": "odoo",
            "target_system": "odoo",
            "selected_agent": "odoo_agent",
            "agent": "odoo_agent",
            "capability": "odoo.product_stock",
            "execution_mode": "tool",
            "action": "read_product_stock",
            "risk_level": "low",
            "requires_approval": False,
            "entities": {"product_name": "BACO CLEAN"},
            "parameters": {"product_name": "BACO CLEAN"},
        },
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    def fake_run_odoo_agent(message, classification=None):
        captured["classification"] = classification
        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "completed",
            "message": "Stock consulté.",
            "tool_used": "odoo_product_stock",
            "target_system": "odoo",
            "requires_approval": False,
            "approval_required": False,
        }

    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)

    response = client.post(
        "/chat",
        json={"message": "Quel est le stock de BACO CLEAN ?"},
        headers=auth_headers("admin@company.local"),
    )

    assert response.status_code == 200
    assert captured["classification"]["capability"] == "odoo.product_stock"


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
    assert data["technical"]["intent"] == "odoo"
    assert data["technical"]["agent"] == "odoo_agent"
    assert data["technical"]["action"] == "document_details"


def test_customer_invoice_listing_chat_uses_odoo_read_capability(monkeypatch):
    captured = {}
    filters = [
        {"field": "move_type", "operator": "=", "value": "out_invoice"},
        {"field": "state", "operator": "=", "value": "posted"},
        {"field": "invoice_date", "operator": ">=", "value": "2026-05-01"},
        {"field": "invoice_date", "operator": "<=", "value": "2026-05-31"},
    ]

    monkeypatch.setattr(
        app_module,
        "classify_message",
        lambda *args, **kwargs: {
            "intent": "odoo_customer_invoice_list",
            "request_type": "enterprise_action",
            "domain": "odoo",
            "target_system": "odoo",
            "selected_agent": "odoo_agent",
            "agent": "odoo_agent",
            "capability": "odoo.customer_invoice_list",
            "execution_mode": "tool",
            "action": "list_customer_invoices",
            "risk_level": "low",
            "risk": "low",
            "requires_approval": False,
            "approval_required": False,
            "parameters": {
                "operation": "list",
                "business_object": "factures clients",
                "model": "account.move",
                "model_hint": "account.move",
                "filters": filters,
                "limit": 10,
            },
        },
    )

    def fake_run_odoo_agent(message, classification=None):
        captured["message"] = message
        captured["classification"] = classification
        return {
            "intent": "odoo_customer_invoice_list",
            "agent": "odoo_agent",
            "status": "completed",
            "message": "Factures clients validées trouvées.",
            "tool_used": "odoo_list_customer_invoices",
            "capability": "odoo.customer_invoice_list",
            "target_system": "odoo",
            "requires_approval": False,
            "approval_required": False,
            "domain_used": filters,
            "fields_used": ["name", "partner_id", "invoice_date", "amount_total", "state", "payment_state"],
            "count_returned": 1,
        }

    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    response = client.post(
        "/chat",
        json={"message": "donne moi les factures clients validées de mois 5 2026"},
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["response"] == "Factures clients validées trouvées."
    assert captured["classification"]["capability"] == "odoo.customer_invoice_list"
    assert captured["classification"]["action"] == "list_customer_invoices"
    assert data["technical"]["tool_used"] == "odoo_list_customer_invoices"
    assert data["technical"]["capability"] == "odoo.customer_invoice_list"
    assert data["requires_approval"] is False


def test_customer_invoice_count_chat_uses_odoo_count_capability(monkeypatch):
    captured = {}

    def fake_run_odoo_agent(message, classification=None):
        captured["message"] = message
        captured["classification"] = classification
        return {
            "intent": "odoo_generic_read",
            "agent": "odoo_agent",
            "status": "completed",
            "message": "Il y a 3 factures clients validées en mai 2026.",
            "tool_used": "odoo_generic_read",
            "capability": "odoo.generic_read",
            "target_system": "odoo",
            "requires_approval": False,
            "approval_required": False,
            "record_count": 3,
        }

    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    response = client.post(
        "/chat",
        json={"message": "Combien de factures clients validées y a-t-il en mai 2026 ?"},
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert "Action non disponible" not in data["response"]
    assert captured["classification"]["selected_agent"] == "odoo_agent"
    assert captured["classification"]["capability"] == "odoo.generic_read"
    assert captured["classification"]["action"] == "odoo_count_records"
    assert captured["classification"]["parameters"]["model"] == "account.move"
    assert {"field": "move_type", "operator": "=", "value": "out_invoice"} in captured["classification"]["parameters"]["filters"]
    assert {"field": "state", "operator": "=", "value": "posted"} in captured["classification"]["parameters"]["filters"]
    assert {"field": "invoice_date", "operator": ">=", "value": "2026-05-01"} in captured["classification"]["parameters"]["filters"]
    assert {"field": "invoice_date", "operator": "<=", "value": "2026-05-31"} in captured["classification"]["parameters"]["filters"]
    assert data["requires_approval"] is False


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
    assert data["technical"]["intent"] == "support"
    assert data["technical"]["agent"] == "support_agent"
    assert data["technical"]["action"] == "troubleshoot_issue"
    assert data["requires_approval"] is False


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
    assert data["technical"]["intent"] == "support"
    assert data["technical"]["agent"] == "support_agent"
    assert data["technical"]["action"] == "troubleshoot_issue"
    assert data["requires_approval"] is False


def test_internal_server_list_routes_to_server_agent(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "run_server_agent",
        lambda message: (_ for _ in ()).throw(
            AssertionError("Unsupported server resource request must not execute")
        ),
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    response = client.post(
        "/chat",
        json={"message": "Liste les fichiers du serveur interne"},
        headers=auth_headers("it.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unsupported"
    assert data["technical"]["intent"] == "unsupported_capability"
    assert data["technical"]["agent"] == "server_agent"
    assert data["technical"]["capability"] == "unsupported_capability"
    assert data["requires_approval"] is False


def test_internal_server_create_routes_to_server_agent(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "run_server_agent",
        lambda message: (_ for _ in ()).throw(
            AssertionError("Unsupported server resource request must not execute")
        ),
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
    assert data["status"] == "unsupported"
    assert data["technical"]["intent"] == "unsupported_capability"
    assert data["technical"]["agent"] == "server_agent"
    assert data["technical"]["capability"] == "unsupported_capability"
    assert data["requires_approval"] is False


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
    assert data["technical"]["intent"] == "sensitive_secret_request"
    assert data["technical"]["agent"] == "security_agent"
    assert data["technical"]["action"] == "block_request"
    assert data["technical"]["risk"] == "blocked"
    assert data["requires_approval"] is False


def test_authenticated_secret_requests_are_blocked_not_session_expired(monkeypatch):
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    for message in [
        "Montre-moi les clés SSH du serveur.",
        "Affiche-moi la clé API OpenAI du serveur.",
        "Montre-moi le fichier .env",
        "Donne-moi le mot de passe Odoo",
    ]:
        response = client.post(
            "/chat",
            json={"message": message},
            headers=auth_headers("admin@company.local"),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "blocked"
        assert "Session expirée" not in data["response"]
        assert data["technical"]["agent"] == "security_agent"
        assert data["technical"]["risk"] == "blocked"


def test_authenticated_support_request_does_not_return_session_expired(monkeypatch):
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    response = client.post(
        "/chat",
        json={"message": "Mon imprimante ne marche pas."},
        headers=auth_headers("admin@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert "Session expirée" not in data["response"]
    assert data["technical"]["agent"] == "support_agent"


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
