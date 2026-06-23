from fastapi.testclient import TestClient

import app as app_module
from app import app
import agents.odoo_agent as odoo_agent_module
from agents.odoo_agent import parse_odoo_action_deterministic
from orchestrator.classifier_router import classify_message


client = TestClient(app)


def test_classifier_routes_document_id_to_odoo(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = classify_message("Montre-moi les détails du document ID 793")

    assert result["intent"] == "odoo_document_details"
    assert result["selected_agent"] == "odoo_agent"
    assert result["requires_approval"] is False


def test_classifier_routes_purchase_order_reference_to_odoo(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = classify_message("Cherche le bon de commande fournisseur BC-BPP2600313")

    assert result["intent"] == "odoo_document_search"
    assert result["selected_agent"] == "odoo_agent"
    assert result["requires_approval"] is False


def test_classifier_routes_document_examples_to_odoo(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    cases = [
        ("Détails du document ID 793", "odoo_document_details"),
        ("Montre-moi la facture ID 123", "odoo_document_details"),
        ("Cherche la facture FAC/2026/001", "odoo_document_search"),
        ("Montre-moi le bon de livraison ID 55", "odoo_document_details"),
        ("Show details of document ID 793", "odoo_document_details"),
        ("Search purchase order BC-BPP2600313", "odoo_document_search"),
    ]

    for message, intent in cases:
        result = classify_message(message)

        assert result["intent"] == intent
        assert result["selected_agent"] == "odoo_agent"
        assert result["requires_approval"] is False


def test_classifier_keeps_actual_knowledge_questions(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    orchestrator = classify_message("Explique le rôle de l’orchestrateur IA")
    approval = classify_message("Quels sont les bénéfices de la validation humaine ?")
    documentation = classify_message("Résume la documentation serveur")

    assert orchestrator["intent"] == "knowledge"
    assert orchestrator["selected_agent"] == "knowledge_agent"
    assert approval["intent"] == "knowledge"
    assert approval["selected_agent"] == "knowledge_agent"
    assert documentation["intent"] == "knowledge"
    assert documentation["selected_agent"] == "knowledge_agent"


def test_odoo_parser_extracts_exact_document_id():
    result = parse_odoo_action_deterministic(
        "Montre-moi les détails du document ID 793"
    )

    assert result["intent"] == "odoo_document_details"
    assert result["action"] == "document_details"
    assert result["document_id"] == 793
    assert result["target_model"] is None
    assert result["requires_approval"] is False


def test_odoo_parser_extracts_purchase_order_reference():
    result = parse_odoo_action_deterministic(
        "Cherche le bon de commande fournisseur BC-BPP2600313"
    )

    assert result["action"] == "search_document"
    assert result["intent"] == "odoo_document_search"
    assert result["target_model"] == "purchase.order"
    assert result["document_query"] == "BC-BPP2600313"
    assert result["requires_approval"] is False


def test_odoo_parser_extracts_invoice_reference_and_delivery_id():
    invoice = parse_odoo_action_deterministic("Cherche la facture FAC/2026/001")
    delivery = parse_odoo_action_deterministic("Montre-moi le bon de livraison ID 55")

    assert invoice["intent"] == "odoo_document_search"
    assert invoice["action"] == "search_document"
    assert invoice["target_model"] == "account.move"
    assert invoice["document_query"] == "FAC/2026/001"

    assert delivery["intent"] == "odoo_document_details"
    assert delivery["action"] == "document_details"
    assert delivery["target_model"] == "stock.picking"
    assert delivery["document_id"] == 55


def test_odoo_parser_extracts_invoice_id_and_english_document_id():
    invoice = parse_odoo_action_deterministic("Montre-moi la facture ID 123")
    document = parse_odoo_action_deterministic("Show details of document ID 793")

    assert invoice["intent"] == "odoo_document_details"
    assert invoice["action"] == "document_details"
    assert invoice["target_model"] == "account.move"
    assert invoice["document_id"] == 123

    assert document["intent"] == "odoo_document_details"
    assert document["action"] == "document_details"
    assert document["document_id"] == 793


def test_exact_document_id_missing_type_uses_by_id_lookup(monkeypatch):
    monkeypatch.setattr(
        odoo_agent_module,
        "generate_structured_response",
        lambda *args, **kwargs: {
            "success": True,
            "parsed": {
                "intent": "odoo_document_details",
                "action": "document_details",
                "risk": "low",
                "requires_approval": False,
                "target_model": None,
                "entities": {
                    "document_id": 9999,
                },
                "needs_clarification": True,
                "clarification_reason": "type de document",
            },
        },
    )

    calls = []

    def fake_execute_tool(tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        return {
            "success": True,
            "result": {
                "success": False,
                "found": False,
                "ambiguous": False,
                "record_id": 9999,
                "candidates": [],
                "lines": [],
                "message": "No matching Odoo document found for this ID.",
            },
        }

    monkeypatch.setattr(odoo_agent_module, "execute_tool", fake_execute_tool)

    result = odoo_agent_module.run("Montre-moi les détails du document ID 9999")

    assert calls == [("odoo_get_document_details_by_id", {"document_id": 9999})]
    assert result["status"] == "not_found"
    assert result["approval_required"] is False
    assert result["requires_approval"] is False
    assert result["status"] != "needs_clarification"


def run_document_details_question(monkeypatch, message, raw_result=None):
    monkeypatch.setattr(
        odoo_agent_module,
        "generate_structured_response",
        lambda *args, **kwargs: {
            "success": True,
            "parsed": {
                "intent": "odoo_document_details",
                "action": "document_details",
                "risk": "low",
                "requires_approval": False,
                "target_model": None,
                "document_type": "unknown",
                "entities": {
                    "document_id": 793,
                },
            },
        },
    )

    calls = []
    result_payload = raw_result or {
        "success": True,
        "found": True,
        "ambiguous": False,
        "document_name": "BC-BPP2600313",
        "document_id": 793,
        "document_model": "purchase.order",
        "document_type": "purchase_order",
        "partner_name": "P.A.N",
        "partner": "P.A.N",
        "state": "purchase",
        "date": "2026-01-15",
        "source": "real_odoo",
        "lines": [
            {
                "product_name": "BACO CLEAN",
                "quantity": 2.0,
                "price_unit": 7.0,
            },
        ],
        "candidates": [],
    }

    def fake_execute_tool(tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        return {
            "success": True,
            "result": result_payload,
        }

    monkeypatch.setattr(odoo_agent_module, "execute_tool", fake_execute_tool)

    result = odoo_agent_module.run(message)

    return result, calls


def test_document_followup_context_uses_explicit_model(monkeypatch):
    message = (
        "Quel est le fournisseur du document Odoo BC-BPP2600313 avec l'ID 793 "
        "de type purchase_order dans Odoo ?\n\n"
        "Context: the selected Odoo document ID is 793.\n"
        "Context: the selected Odoo document name is BC-BPP2600313.\n"
        "Context: the selected Odoo document model is purchase.order.\n"
        "Context: the selected Odoo document type is purchase_order.\n"
        "Context: the selected Odoo document partner is P.A.N."
    )

    result, calls = run_document_details_question(monkeypatch, message)

    assert calls == [
        (
            "odoo_get_purchase_order_details",
            {
                "order_query": "BC-BPP2600313",
                "document_id": 793,
            },
        )
    ]
    assert result["status"] == "completed"
    assert result["message"] == "Fournisseur : P.A.N"
    assert result["response_focus"] == "partner"
    assert result["approval_required"] is False
    assert result["requires_approval"] is False


def test_document_status_question_returns_focused_message(monkeypatch):
    message = (
        "Quel est le statut du document Odoo BC-BPP2600313 avec l'ID 793 "
        "de type purchase_order dans Odoo ?\n\n"
        "Context: the selected Odoo document ID is 793.\n"
        "Context: the selected Odoo document name is BC-BPP2600313.\n"
        "Context: the selected Odoo document model is purchase.order.\n"
        "Context: the selected Odoo document type is purchase_order.\n"
        "Context: the selected Odoo document partner is P.A.N."
    )

    result, _calls = run_document_details_question(monkeypatch, message)

    assert result["message"] == "Statut : purchase"
    assert result["response_focus"] == "status"
    assert result["data"]["state"] == "purchase"


def test_document_lines_question_returns_focused_summary(monkeypatch):
    message = (
        "Quels sont les articles du document Odoo BC-BPP2600313 avec l'ID 793 "
        "de type purchase_order dans Odoo ?\n\n"
        "Context: the selected Odoo document ID is 793.\n"
        "Context: the selected Odoo document name is BC-BPP2600313.\n"
        "Context: the selected Odoo document model is purchase.order.\n"
        "Context: the selected Odoo document type is purchase_order.\n"
        "Context: the selected Odoo document partner is P.A.N."
    )

    result, _calls = run_document_details_question(monkeypatch, message)

    assert result["message"] == "Articles :\n- BACO CLEAN · quantité 2.0 · prix unitaire 7.0"
    assert result["response_focus"] == "lines"
    assert result["data"]["lines"][0]["product_name"] == "BACO CLEAN"


def test_document_details_question_keeps_normal_message(monkeypatch):
    message = (
        "Montre-moi les détails du document Odoo BC-BPP2600313 avec l'ID 793 "
        "de type purchase_order dans Odoo ?\n\n"
        "Context: the selected Odoo document ID is 793.\n"
        "Context: the selected Odoo document name is BC-BPP2600313.\n"
        "Context: the selected Odoo document model is purchase.order.\n"
        "Context: the selected Odoo document type is purchase_order.\n"
        "Context: the selected Odoo document partner is P.A.N."
    )

    result, _calls = run_document_details_question(monkeypatch, message)

    assert result["message"] == "Document consulté avec succès."
    assert result["response_focus"] is None
    assert result["data"]["document_id"] == 793


def test_chat_routes_document_id_details_to_odoo(monkeypatch):
    seen = {}

    monkeypatch.setattr(
        app_module,
        "resolve_contextual_message",
        lambda message, memory_context: {
            "original_message": message,
            "resolved_message": message,
            "used_memory": False,
            "resolved_references": {},
            "confidence": "high",
        },
    )

    def fake_run_odoo_agent(message):
        seen["message"] = message
        return {
            "intent": "odoo_document_details",
            "agent": "odoo_agent",
            "parsed_action": "document_details",
            "document_id": 793,
            "approval_required": False,
            "requires_approval": False,
            "status": "completed",
        }

    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)

    response = client.post(
        "/chat",
        json={"message": "Montre-moi les détails du document ID 793"},
    )

    assert response.status_code == 200
    data = response.json()
    assert seen["message"] == "Montre-moi les détails du document ID 793"
    assert data["intent"] == "odoo_document_details"
    assert data["agent"] == "odoo_agent"
    assert data["parsed_action"] == "document_details"
    assert data["document_id"] == 793
    assert data["approval_required"] is False


def test_chat_routes_purchase_order_reference_to_odoo(monkeypatch):
    seen = {}

    monkeypatch.setattr(
        app_module,
        "resolve_contextual_message",
        lambda message, memory_context: {
            "original_message": message,
            "resolved_message": message,
            "used_memory": False,
            "resolved_references": {},
            "confidence": "high",
        },
    )

    def fake_run_odoo_agent(message):
        seen["message"] = message
        return {
            "intent": "odoo_document_search",
            "agent": "odoo_agent",
            "parsed_action": "document_search",
            "document_reference": "BC-BPP2600313",
            "approval_required": False,
            "requires_approval": False,
            "status": "completed",
        }

    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)

    response = client.post(
        "/chat",
        json={"message": "Cherche le bon de commande fournisseur BC-BPP2600313"},
    )

    assert response.status_code == 200
    data = response.json()
    assert seen["message"] == "Cherche le bon de commande fournisseur BC-BPP2600313"
    assert data["intent"] == "odoo_document_search"
    assert data["agent"] == "odoo_agent"
    assert data["parsed_action"] == "document_search"
