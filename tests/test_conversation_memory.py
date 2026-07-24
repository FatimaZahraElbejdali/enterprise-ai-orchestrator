from fastapi.testclient import TestClient

import app as app_module
from agents.odoo_agent import extract_product_name, parse_odoo_action_deterministic
from orchestrator import contextual_resolver
from orchestrator.conversation_memory import ConversationMemory
from tests.auth_helpers import auth_headers


def test_conversation_memory_resolves_product_reference():
    memory = ConversationMemory()
    memory.update_from_result(
        "session-a",
        {
            "intent": "odoo",
            "agent": "odoo_agent",
            "metadata": {
                "product_name": "BACO CLEAN",
                "product_id": 3471,
            },
        },
    )

    resolved = memory.resolve_references("Change its price to 7", "session-a")

    assert resolved["product_name"] == "BACO CLEAN"
    assert resolved["product_id"] == 3471
    assert resolved["reference_type"] == "product"


def test_conversation_memory_resolves_french_product_followups():
    memory = ConversationMemory()
    memory.update_from_result(
        "session-fr",
        {
            "intent": "odoo",
            "agent": "odoo_agent",
            "metadata": {
                "product_name": "BACO CLEAN",
                "product_id": 3471,
            },
        },
    )

    for message in [
        "Montre-moi ses détails",
        "Quel est son stock ?",
        "Quelle est sa référence ?",
    ]:
        resolved = memory.resolve_references(message, "session-fr")
        assert resolved == {
            "product_name": "BACO CLEAN",
            "product_id": 3471,
            "reference_type": "product",
        }


def test_exact_document_result_updates_memory():
    memory = ConversationMemory()

    memory.update_from_result(
        "doc-session",
        {
            "intent": "odoo_document_details",
            "agent": "odoo_agent",
            "status": "completed",
            "data": {
                "success": True,
                "found": True,
                "ambiguous": False,
                "document_name": "BC-BPP2600313",
                "document_id": 793,
                "document_model": "purchase.order",
                "document_type": "purchase_order",
                "partner_name": "P.A.N",
                "source": "real_odoo",
                "candidates": [],
            },
        },
    )

    context = memory.get_safe_context("doc-session")

    assert context["last_agent"] == "odoo"
    assert context["last_intent"] == "odoo_document_details"
    assert context["last_document_name"] == "BC-BPP2600313"
    assert context["last_document_id"] == 793
    assert context["last_document_model"] == "purchase.order"
    assert context["last_document_type"] == "purchase_order"
    assert context["last_partner_name"] == "P.A.N"
    assert "updated_at" in context


def test_ambiguous_document_result_does_not_update_memory():
    memory = ConversationMemory()

    memory.update_from_result(
        "doc-session",
        {
            "intent": "odoo_document_details",
            "agent": "odoo_agent",
            "status": "completed",
            "data": {
                "success": True,
                "found": True,
                "ambiguous": False,
                "document_name": "BC-BPP2600313",
                "document_id": 793,
                "document_model": "purchase.order",
                "document_type": "purchase_order",
                "partner_name": "P.A.N",
                "candidates": [],
            },
        },
    )
    memory.update_from_result(
        "doc-session",
        {
            "intent": "odoo_document_search",
            "agent": "odoo_agent",
            "status": "ambiguous",
            "data": {
                "found": True,
                "ambiguous": True,
                "document_name": "WRONG",
                "document_id": 999,
                "candidates": [
                    {"name": "A", "record_id": 1},
                    {"name": "B", "record_id": 2},
                ],
            },
        },
    )

    context = memory.get_safe_context("doc-session")

    assert context["last_document_name"] == "BC-BPP2600313"
    assert context["last_document_id"] == 793


def test_ambiguous_document_search_stores_recent_candidates_only():
    memory = ConversationMemory()

    memory.update_from_result(
        "doc-session",
        {
            "intent": "odoo_document_search",
            "agent": "odoo_agent",
            "status": "completed",
            "data": {
                "found": True,
                "ambiguous": True,
                "candidates": [
                    {
                        "record_id": 793,
                        "name": "BC-BPP2600313",
                        "model": "purchase.order",
                        "partner": "P.A.N",
                    },
                    {
                        "record_id": 446,
                        "name": "BC-BPP2600313",
                        "model": "purchase.order",
                        "partner": "EQUIPEMENT ET ACCESSOIRES DE SECURITE",
                    },
                ],
            },
        },
    )

    context = memory.get_safe_context("doc-session")

    assert "last_document_id" not in context
    assert context["recent_document_candidates"] == [
        {
            "document_id": 793,
            "document_name": "BC-BPP2600313",
            "document_model": "purchase.order",
            "document_type": "purchase_order",
            "partner_name": "P.A.N",
        },
        {
            "document_id": 446,
            "document_name": "BC-BPP2600313",
            "document_model": "purchase.order",
            "document_type": "purchase_order",
            "partner_name": "EQUIPEMENT ET ACCESSOIRES DE SECURITE",
        },
    ]
    assert memory.resolve_document_candidate("doc-session", 793) == {
        "document_id": 793,
        "document_name": "BC-BPP2600313",
        "document_model": "purchase.order",
        "document_type": "purchase_order",
        "partner_name": "P.A.N",
    }


def test_conversation_memory_resolves_document_reference():
    memory = ConversationMemory()
    memory.update_from_result(
        "doc-session",
        {
            "intent": "odoo_document_details",
            "agent": "odoo_agent",
            "status": "completed",
            "metadata": {
                "document_name": "BC-BPP2600313",
                "document_id": 793,
                "document_model": "purchase.order",
                "document_type": "purchase_order",
                "partner_name": "P.A.N",
                "source": "real_odoo",
            },
        },
    )

    resolved = memory.resolve_references("Quel est son fournisseur ?", "doc-session")

    assert resolved == {
        "document_name": "BC-BPP2600313",
        "document_id": 793,
        "document_model": "purchase.order",
        "document_type": "purchase_order",
        "partner_name": "P.A.N",
        "reference_type": "document",
    }


def test_product_and_document_memory_are_independent():
    memory = ConversationMemory()
    memory.update_from_result(
        "mixed-session",
        {
            "intent": "odoo",
            "agent": "odoo_agent",
            "metadata": {
                "product_name": "BACO CLEAN",
                "product_id": 3471,
            },
        },
    )
    memory.update_from_result(
        "mixed-session",
        {
            "intent": "odoo_document_details",
            "agent": "odoo_agent",
            "status": "completed",
            "metadata": {
                "document_name": "BC-BPP2600313",
                "document_id": 793,
                "document_model": "purchase.order",
                "document_type": "purchase_order",
                "partner_name": "P.A.N",
            },
        },
    )

    context = memory.get_safe_context("mixed-session")
    product = memory.resolve_references("Quel est son stock ?", "mixed-session")
    document = memory.resolve_references("Quel est son statut ?", "mixed-session")

    assert context["last_product_name"] == "BACO CLEAN"
    assert context["last_product_id"] == 3471
    assert context["last_document_name"] == "BC-BPP2600313"
    assert context["last_document_id"] == 793
    assert product["reference_type"] == "product"
    assert product["product_name"] == "BACO CLEAN"
    assert document["reference_type"] == "document"
    assert document["document_id"] == 793


def test_app_clarifies_french_product_followups_for_odoo_routing():
    context = {
        "product_name": "BACO CLEAN",
        "product_id": 3471,
        "reference_type": "product",
    }

    assert (
        app_module.clarify_product_reference_message("Montre-moi ses détails", context)
        == "Montre-moi les détails du produit BACO CLEAN"
    )
    assert (
        app_module.clarify_product_reference_message("Quel est son stock ?", context)
        == "Quel est le stock du produit BACO CLEAN ?"
    )
    assert (
        app_module.clarify_product_reference_message("Quelle est sa référence ?", context)
        == "Quelle est la référence interne du produit BACO CLEAN ?"
    )


def test_chat_enriches_follow_up_product_reference(monkeypatch):
    memory = ConversationMemory()
    seen_messages = []

    def fake_resolve_contextual_message(message, memory_context):
        if "price" in message.lower():
            assert memory_context["last_product_name"] == "BACO CLEAN"
            assert memory_context["last_product_id"] == 3471
            return {
                "original_message": message,
                "resolved_message": "Change the price of product BACO CLEAN to 7 DH in Odoo",
                "used_memory": True,
                "resolved_references": {
                    "reference_type": "product",
                    "product_name": "BACO CLEAN",
                    "product_id": 3471,
                },
                "confidence": "high",
            }

        return {
            "original_message": message,
            "resolved_message": message,
            "used_memory": False,
            "resolved_references": {},
            "confidence": "high",
        }

    def fake_run_odoo_agent(message):
        seen_messages.append(message)

        if "stock" in message.lower():
            return {
                "intent": "odoo",
                "agent": "odoo_agent",
                "product_name": "BACO CLEAN",
                "product_id": 3471,
                "approval_required": False,
                "requires_approval": False,
            }

        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "product_name": "BACO CLEAN",
            "product_id": 3471,
            "approval_required": True,
            "requires_approval": True,
            "status": "pending_approval",
        }

    monkeypatch.setattr(app_module, "conversation_memory", memory)
    monkeypatch.setattr(
        app_module,
        "resolve_contextual_message",
        fake_resolve_contextual_message,
    )
    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)

    client = TestClient(app_module.app)
    headers = auth_headers("odoo.manager@company.local")
    first_response = client.post(
        "/chat",
        json={
            "message": "Vérifier le stock de BACO CLEAN",
            "session_id": "demo-follow-up",
        },
        headers=headers,
    )
    second_response = client.post(
        "/chat",
        json={
            "message": "Change its price to 7",
            "session_id": "demo-follow-up",
        },
        headers=headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert seen_messages[1] == "Change the price of product BACO CLEAN to 7 DH in Odoo"
    assert second_response.json()["requires_approval"] is True


def test_chat_enriches_french_details_followup(monkeypatch):
    memory = ConversationMemory()
    seen_messages = []

    def fake_resolve_contextual_message(message, memory_context):
        if "ses détails" in message.lower():
            assert memory_context["last_product_name"] == "BACO CLEAN"
            return {
                "original_message": message,
                "resolved_message": "Montre-moi les détails du produit BACO CLEAN dans Odoo",
                "used_memory": True,
                "resolved_references": {
                    "reference_type": "product",
                    "product_name": "BACO CLEAN",
                    "product_id": 3471,
                },
                "confidence": "high",
            }

        return {
            "original_message": message,
            "resolved_message": message,
            "used_memory": False,
            "resolved_references": {},
            "confidence": "high",
        }

    def fake_run_odoo_agent(message):
        seen_messages.append(message)

        if "BACO CLEAN" in message:
            return {
                "intent": "odoo",
                "agent": "odoo_agent",
                "product_name": "BACO CLEAN",
                "product_id": 3471,
                "approval_required": False,
                "requires_approval": False,
                "status": "completed",
            }

        return {
            "intent": "general",
            "agent": "general_agent",
        }

    monkeypatch.setattr(app_module, "conversation_memory", memory)
    monkeypatch.setattr(
        app_module,
        "resolve_contextual_message",
        fake_resolve_contextual_message,
    )
    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)

    client = TestClient(app_module.app)
    headers = auth_headers("odoo.manager@company.local")
    first_response = client.post(
        "/chat",
        json={
            "message": "Cherche le produit BACO CLEAN",
            "session_id": "demo-french-follow-up",
        },
        headers=headers,
    )
    second_response = client.post(
        "/chat",
        json={
            "message": "Montre-moi ses détails",
            "session_id": "demo-french-follow-up",
        },
        headers=headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert seen_messages[1] == "Montre-moi les détails du produit BACO CLEAN dans Odoo"


def test_chat_resolves_document_followup_to_odoo(monkeypatch):
    memory = ConversationMemory()
    seen_messages = []

    monkeypatch.setattr(app_module, "conversation_memory", memory)
    monkeypatch.setattr(
        contextual_resolver,
        "generate_structured_response",
        lambda *args, **kwargs: {"success": False, "parsed": None},
    )

    def fake_run_odoo_agent(message):
        seen_messages.append(message)

        if "document ID 793" in message:
            return {
                "intent": "odoo_document_details",
                "agent": "odoo_agent",
                "status": "completed",
                "approval_required": False,
                "requires_approval": False,
                "data": {
                    "success": True,
                    "found": True,
                    "ambiguous": False,
                    "document_name": "BC-BPP2600313",
                    "document_id": 793,
                    "document_model": "purchase.order",
                    "document_type": "purchase_order",
                    "partner_name": "P.A.N",
                    "source": "real_odoo",
                    "candidates": [],
                },
            }

        return {
            "intent": "odoo_document_details",
            "agent": "odoo_agent",
            "status": "completed",
            "approval_required": False,
            "requires_approval": False,
        }

    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)

    client = TestClient(app_module.app)
    headers = auth_headers("odoo.manager@company.local")
    first_response = client.post(
        "/chat",
        json={
            "message": "Montre-moi les détails du document ID 793",
            "session_id": "demo-doc-follow-up",
        },
        headers=headers,
    )
    second_response = client.post(
        "/chat",
        json={
            "message": "Quel est son fournisseur ?",
            "session_id": "demo-doc-follow-up",
        },
        headers=headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert seen_messages[1].startswith(
        "Quel est le fournisseur du document Odoo BC-BPP2600313 "
        "avec l'ID 793 de type purchase_order dans Odoo ?"
    )
    assert "Context: the selected Odoo document ID is 793." in seen_messages[1]
    assert "Context: the selected Odoo document model is purchase.order." in seen_messages[1]
    assert "Context: the selected Odoo document type is purchase_order." in seen_messages[1]


def test_chat_resolves_document_id_from_recent_candidates(monkeypatch):
    memory = ConversationMemory()
    seen_messages = []

    memory.update_from_result(
        "candidate-session",
        {
            "intent": "odoo_document_search",
            "agent": "odoo_agent",
            "status": "completed",
            "data": {
                "found": True,
                "ambiguous": True,
                "candidates": [
                    {
                        "record_id": 793,
                        "name": "BC-BPP2600313",
                        "model": "purchase.order",
                        "partner": "P.A.N",
                    },
                    {
                        "record_id": 446,
                        "name": "BC-BPP2600313",
                        "model": "purchase.order",
                        "partner": "EQUIPEMENT ET ACCESSOIRES DE SECURITE",
                    },
                ],
            },
        },
    )

    monkeypatch.setattr(app_module, "conversation_memory", memory)
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
        seen_messages.append(message)
        return {
            "intent": "odoo_document_details",
            "agent": "odoo_agent",
            "status": "completed",
            "approval_required": False,
            "requires_approval": False,
            "data": {
                "success": True,
                "found": True,
                "ambiguous": False,
                "document_name": "BC-BPP2600313",
                "document_id": 793,
                "document_model": "purchase.order",
                "document_type": "purchase_order",
                "partner_name": "P.A.N",
                "source": "real_odoo",
                "candidates": [],
            },
        }

    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)

    client = TestClient(app_module.app)
    response = client.post(
        "/chat",
        json={
            "message": "Montre-moi les détails du document ID 793",
            "session_id": "candidate-session",
        },
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    assert "Context: the selected Odoo document model is purchase.order." in seen_messages[0]

    context = memory.get_safe_context("candidate-session")
    assert context["last_document_id"] == 793
    assert context["last_document_model"] == "purchase.order"


def test_contextual_resolver_rewrites_product_followups_with_openai(monkeypatch):
    memory_context = {
        "last_agent": "odoo",
        "last_intent": "odoo",
        "last_product_name": "BACO CLEAN",
        "last_product_id": 3471,
    }

    expected = {
        "Montre-moi ses détails": "Montre-moi les détails du produit BACO CLEAN dans Odoo",
        "Quel est son stock ?": "Quel est le stock du produit BACO CLEAN dans Odoo ?",
        "Et sa référence ?": "Quelle est la référence interne du produit BACO CLEAN dans Odoo ?",
        "change its price to 5 DH": "Change the price of product BACO CLEAN to 5 DH in Odoo",
    }

    def fake_generate_structured_response(prompt, schema, system_prompt=None, model=None):
        current_message = __import__("json").loads(prompt)["current_user_message"]
        return {
            "success": True,
            "parsed": {
                "original_message": current_message,
                "resolved_message": expected[current_message],
                "used_memory": True,
                "resolved_references": {
                    "reference_type": "product",
                    "product_name": "BACO CLEAN",
                    "product_id": 3471,
                },
                "confidence": "high",
            },
        }

    monkeypatch.setattr(
        contextual_resolver,
        "generate_structured_response",
        fake_generate_structured_response,
    )

    for message, resolved_message in expected.items():
        result = contextual_resolver.resolve_contextual_message(message, memory_context)
        assert result["resolved_message"] == resolved_message
        assert result["used_memory"] is True
        assert result["confidence"] == "high"


def test_contextual_resolver_does_not_invent_product_without_memory(monkeypatch):
    monkeypatch.setattr(
        contextual_resolver,
        "generate_structured_response",
        lambda *args, **kwargs: {"success": False, "parsed": None},
    )

    result = contextual_resolver.resolve_contextual_message("Montre-moi ses détails", {})

    assert result == {
        "original_message": "Montre-moi ses détails",
        "resolved_message": "Montre-moi ses détails",
        "used_memory": False,
        "resolved_references": {},
        "confidence": "low",
    }


def test_contextual_resolver_rewrites_document_followups_without_openai(monkeypatch):
    monkeypatch.setattr(
        contextual_resolver,
        "generate_structured_response",
        lambda *args, **kwargs: {"success": False, "parsed": None},
    )

    memory_context = {
        "last_agent": "odoo",
        "last_intent": "odoo_document_details",
        "last_document_name": "BC-BPP2600313",
        "last_document_id": 793,
        "last_document_model": "purchase.order",
        "last_document_type": "purchase_order",
        "last_partner_name": "P.A.N",
    }

    expected = {
        "Montre-moi les détails de ce document": "Montre-moi les détails du document Odoo BC-BPP2600313 avec l'ID 793 de type purchase_order",
        "Quel est son fournisseur ?": "Quel est le fournisseur du document Odoo BC-BPP2600313 avec l'ID 793 de type purchase_order dans Odoo ?",
        "Quel est son statut ?": "Quel est le statut du document Odoo BC-BPP2600313 avec l'ID 793 de type purchase_order dans Odoo ?",
        "Résume ce document": "Résume le document Odoo BC-BPP2600313 avec l'ID 793 de type purchase_order dans Odoo",
        "show its details": "Montre-moi les détails du document Odoo BC-BPP2600313 avec l'ID 793 de type purchase_order",
        "what is its status": "Quel est le statut du document Odoo BC-BPP2600313 avec l'ID 793 de type purchase_order dans Odoo ?",
        "who is the supplier?": "Quel est le fournisseur du document Odoo BC-BPP2600313 avec l'ID 793 de type purchase_order dans Odoo ?",
    }

    for message, resolved_message in expected.items():
        result = contextual_resolver.resolve_contextual_message(message, memory_context)

        assert result["resolved_message"] == resolved_message
        assert result["used_memory"] is True
        assert result["resolved_references"]["reference_type"] == "document"
        assert result["resolved_references"]["document_id"] == 793


def test_debug_conversation_endpoint_returns_only_safe_fields(monkeypatch):
    memory = ConversationMemory()
    memory.update_from_result(
        "debug-session",
        {
            "intent": "odoo",
            "agent": "odoo_agent",
            "product_name": "BACO CLEAN",
            "product_id": 3471,
            "database": "hidden",
            "api_key": "hidden",
        },
    )
    monkeypatch.setattr(app_module, "conversation_memory", memory)

    client = TestClient(app_module.app)
    response = client.get("/debug/conversation/debug-session")

    assert response.status_code == 200
    data = response.json()
    assert data["last_agent"] == "odoo"
    assert data["last_intent"] == "odoo"
    assert data["last_product_name"] == "BACO CLEAN"
    assert data["last_product_id"] == 3471
    assert "updated_at" in data
    assert "database" not in data
    assert "api_key" not in data


def test_debug_routes_lists_conversation_debug_route():
    client = TestClient(app_module.app)
    response = client.get("/debug/routes")

    assert response.status_code == 200
    assert "/debug/conversation/{session_id}" in response.json()


def test_different_sessions_do_not_share_product_memory():
    memory = ConversationMemory()
    memory.update_from_result(
        "session-a",
        {
            "intent": "odoo",
            "agent": "odoo_agent",
            "metadata": {
                "product_name": "BACO CLEAN",
                "product_id": 3471,
            },
        },
    )

    assert memory.resolve_references("change its price to 5 DH", "session-b") == {}


def test_missing_or_ambiguous_product_does_not_overwrite_memory():
    memory = ConversationMemory()
    memory.update_from_result(
        "session-a",
        {
            "intent": "odoo",
            "agent": "odoo_agent",
            "metadata": {
                "product_name": "BACO CLEAN",
                "product_id": 3471,
            },
        },
    )
    memory.update_from_result(
        "session-a",
        {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "not_found",
            "data": {
                "found": False,
                "product_name": "MISSING",
                "product_id": 9999,
            },
        },
    )
    memory.update_from_result(
        "session-a",
        {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "ambiguous",
            "data": {
                "ambiguous": True,
                "product_name": "AMBIGUOUS",
                "product_id": 1111,
            },
        },
    )

    context = memory.get_safe_context("session-a")

    assert context["last_product_name"] == "BACO CLEAN"
    assert context["last_product_id"] == 3471


def test_odoo_local_parser_reads_safe_context_line():
    message = "Change its price to 7\n\nContext: the referenced product is BACO CLEAN."

    parsed = parse_odoo_action_deterministic(message)

    assert extract_product_name(message) == "BACO CLEAN"
    assert parsed["action"] == "change_price"
    assert parsed["record_query"] == "BACO CLEAN"
    assert parsed["new_value"] == 7.0
    assert parsed["requires_approval"] is True


def test_odoo_local_parser_uses_document_candidate_context():
    message = (
        "Montre-moi les détails du document ID 793\n\n"
        "Context: the selected Odoo document ID is 793.\n"
        "Context: the selected Odoo document name is BC-BPP2600313.\n"
        "Context: the selected Odoo document model is purchase.order.\n"
        "Context: the selected Odoo document type is purchase_order.\n"
        "Context: the selected Odoo document partner is P.A.N."
    )

    parsed = parse_odoo_action_deterministic(message)

    assert parsed["action"] == "document_details"
    assert parsed["document_id"] == 793
    assert parsed["target_model"] == "purchase.order"
    assert parsed["document_type"] == "purchase_order"
    assert parsed["partner_name"] == "P.A.N"
    assert parsed["requires_approval"] is False


def _odoo_pending_read_classification():
    return {
        "intent": "odoo_generic_read",
        "request_type": "enterprise_action",
        "domain": "odoo",
        "target_system": "odoo",
        "selected_agent": "odoo_agent",
        "agent": "odoo_agent",
        "capability": "odoo.generic_read",
        "execution_mode": "tool",
        "action": "read_odoo",
        "risk_level": "low",
        "requires_approval": False,
    }


def _general_knowledge_classification():
    return {
        "intent": "general_information_question",
        "request_type": "general_knowledge",
        "domain": "knowledge",
        "selected_agent": "knowledge_agent",
        "agent": "knowledge_agent",
        "capability": "knowledge.general_answer",
        "execution_mode": "llm_direct",
        "action": "general_answer",
        "risk_level": "low",
        "requires_approval": False,
    }


def _contact_count_result(count=14256):
    return {
        "intent": "odoo",
        "agent": "odoo_agent",
        "selected_agent": "odoo_agent",
        "status": "completed",
        "message": f"Vous avez actuellement {count} contacts dans Odoo.",
        "requires_approval": False,
        "approval_required": False,
        "tool_used": "odoo_generic_read",
        "target_system": "odoo",
        "capability": "odoo.generic_read",
        "odoo_model": "res.partner",
        "record_count": count,
        "result": {
            "model": "res.partner",
            "record_count": count,
            "read_plan": {
                "operation": "count",
                "business_object": "contacts",
                "model_hint": "res.partner",
            },
            "records": [],
        },
    }


def _contact_list_result(limit=3):
    records = [
        {"id": 1, "name": "Contact A", "email": "a@example.test", "phone": "111", "type": "contact"},
        {"id": 2, "name": "Contact B", "email": "b@example.test", "phone": "222", "type": "client"},
        {"id": 3, "name": "Contact C", "email": "", "phone": "", "type": "fournisseur"},
    ][:limit]
    lines = [f"- {record['name']}" for record in records]
    return {
        "intent": "odoo",
        "agent": "odoo_agent",
        "selected_agent": "odoo_agent",
        "status": "completed",
        "message": "Voici 3 contacts dans Odoo :\n" + "\n".join(lines),
        "requires_approval": False,
        "approval_required": False,
        "tool_used": "odoo_generic_read",
        "target_system": "odoo",
        "capability": "odoo.generic_read",
        "odoo_model": "res.partner",
        "selected_model_name": "res.partner",
        "record_count": len(records),
        "fields_used": ["name", "email", "phone", "customer_rank", "supplier_rank", "is_company"],
        "count_returned": len(records),
        "result": {
            "model": "res.partner",
            "record_count": len(records),
            "fields": ["name", "email", "phone", "customer_rank", "supplier_rank", "is_company"],
            "records": records,
            "read_plan": {
                "operation": "list",
                "business_object": "contacts",
                "model_hint": "res.partner",
                "limit": limit,
            },
        },
    }


def test_successful_odoo_count_stores_followup_read_context():
    memory = ConversationMemory()

    memory.update_from_result("contact-memory", _contact_count_result())

    context = memory.get_safe_context("contact-memory")
    assert context["last_agent"] == "odoo"
    assert context["last_model"] == "res.partner"
    assert context["last_business_object"] == "contacts"
    assert context["last_action"] == "count"
    assert context["last_count"] == 14256
    assert "name" in context["last_safe_fields"]

    resolved = memory.resolve_odoo_result_reference("cite moi 3 parmi eux", "contact-memory")
    assert resolved["model"] == "res.partner"
    assert resolved["business_object"] == "contacts"
    assert resolved["limit"] == 3
    assert "email" in resolved["safe_fields"]


def test_contact_count_followup_lists_three_contacts(monkeypatch):
    memory = ConversationMemory()
    seen_classifications = []

    def fake_classify(message, **kwargs):
        if ".env" in message:
            return {
                "intent": "sensitive_secret_request",
                "selected_agent": "security_agent",
                "agent": "security_agent",
                "risk_level": "blocked",
                "risk": "blocked",
                "action": "block_request",
                "requires_approval": False,
            }

        if "combien" in message.lower() and "contacts" in message.lower():
            route = _odoo_pending_read_classification()
            route["parameters"] = {
                "operation": "count",
                "business_object": "contacts",
                "model": "res.partner",
                "model_hint": "res.partner",
            }
            return route

        return _general_knowledge_classification()

    def fake_run_odoo_agent(message, classification=None):
        seen_classifications.append(classification)

        if classification and classification.get("parameters", {}).get("memory_followup"):
            assert classification["parameters"]["model_hint"] == "res.partner"
            assert classification["parameters"]["limit"] == 3
            return _contact_list_result(3)

        return _contact_count_result()

    monkeypatch.setattr(app_module, "conversation_memory", memory)
    monkeypatch.setattr(app_module, "classify_message", fake_classify)
    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    client = TestClient(app_module.app)
    headers = auth_headers("admin@company.local")
    first_response = client.post(
        "/chat",
        json={"message": "combien de contacts on a sur odoo", "session_id": "contact-followup"},
        headers=headers,
    )
    assert first_response.status_code == 200
    assert first_response.json()["status"] == "completed"

    second_response = client.post(
        "/chat",
        json={"message": "cite moi 3 parmi eux", "session_id": "contact-followup"},
        headers=headers,
    )

    assert second_response.status_code == 200
    data = second_response.json()
    assert data["status"] == "completed"
    assert "Contact A" in data["response"]
    assert data["technical"]["memory_context_used"] is True
    assert data["technical"]["resolved_from_previous_model"] == "res.partner"
    assert data["technical"]["resolved_business_object"] == "contacts"
    assert data["technical"]["follow_up_limit"] == 3
    assert data["technical"]["selected_model"] == "res.partner"
    assert "name" in data["technical"]["fields_used"]
    assert seen_classifications[-1]["parameters"]["memory_followup"] is True


def test_contact_keyword_after_stale_clarification_uses_previous_odoo_context(monkeypatch):
    memory = ConversationMemory()
    memory.update_from_result("contact-clarification", _contact_count_result())
    memory.set_pending_clarification(
        "contact-clarification",
        {
            "original_request": "cite moi 3 parmi eux",
            "resolved_request": "cite moi 3 parmi eux",
            "classification": _general_knowledge_classification(),
            "missing_parameters": ["éléments"],
        },
    )

    def fake_classify(message, **kwargs):
        return _general_knowledge_classification()

    def fake_run_odoo_agent(message, classification=None):
        assert classification["parameters"]["memory_followup"] is True
        return _contact_list_result(classification["parameters"]["limit"])

    monkeypatch.setattr(app_module, "conversation_memory", memory)
    monkeypatch.setattr(app_module, "classify_message", fake_classify)
    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    client = TestClient(app_module.app)
    response = client.post(
        "/chat",
        json={"message": "contacts", "session_id": "contact-clarification"},
        headers=auth_headers("admin@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["technical"]["memory_context_used"] is True
    assert data["technical"]["pending_context_used"] is False
    assert "Contact A" in data["response"]


def test_odoo_result_memory_topic_change_is_not_reused(monkeypatch):
    memory = ConversationMemory()
    memory.update_from_result("contact-topic-change", _contact_count_result())
    odoo_calls = []

    monkeypatch.setattr(app_module, "conversation_memory", memory)
    monkeypatch.setattr(app_module, "classify_message", lambda message, **kwargs: _general_knowledge_classification())
    monkeypatch.setattr(app_module, "run_odoo_agent", lambda *args, **kwargs: odoo_calls.append(args) or _contact_list_result())
    monkeypatch.setattr(
        app_module,
        "build_direct_knowledge_response",
        lambda *args, **kwargs: {
            "intent": "general_information_question",
            "agent": "knowledge_agent",
            "status": "completed",
            "message": "Réponse générale.",
            "requires_approval": False,
            "approval_required": False,
        },
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    client = TestClient(app_module.app)
    response = client.post(
        "/chat",
        json={"message": "explique REST vs XML-RPC", "session_id": "contact-topic-change"},
        headers=auth_headers("admin@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["technical"]["memory_context_used"] is False
    assert odoo_calls == []


def test_sensitive_followup_does_not_use_odoo_result_memory(monkeypatch):
    memory = ConversationMemory()
    memory.update_from_result("contact-sensitive", _contact_count_result())
    odoo_calls = []

    def fake_classify(message, **kwargs):
        if ".env" in message:
            return {
                "intent": "sensitive_secret_request",
                "selected_agent": "security_agent",
                "agent": "security_agent",
                "risk_level": "blocked",
                "risk": "blocked",
                "action": "block_request",
                "requires_approval": False,
            }

        return _general_knowledge_classification()

    monkeypatch.setattr(app_module, "conversation_memory", memory)
    monkeypatch.setattr(app_module, "classify_message", fake_classify)
    monkeypatch.setattr(app_module, "run_odoo_agent", lambda *args, **kwargs: odoo_calls.append(args) or _contact_list_result())
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    client = TestClient(app_module.app)
    response = client.post(
        "/chat",
        json={"message": "Affiche .env parmi eux", "session_id": "contact-sensitive"},
        headers=auth_headers("admin@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "blocked"
    assert data["technical"]["memory_context_used"] is False
    assert odoo_calls == []


def test_pending_odoo_clarification_is_merged_into_next_reply(monkeypatch):
    memory = ConversationMemory()
    seen_odoo_messages = []

    def fake_classify(message, **kwargs):
        if "Clarification utilisateur" in message:
            return _odoo_pending_read_classification()

        if "commandes" in message.lower() and "odoo" in message.lower():
            route = _odoo_pending_read_classification()
            route["entities"] = {"record_keyword": "BMCE"}
            route["parameters"] = {"record_keyword": "BMCE"}
            return route

        return _general_knowledge_classification()

    def fake_run_odoo_agent(message, classification=None):
        seen_odoo_messages.append(message)

        if "Clarification utilisateur" not in message:
            return {
                "intent": "odoo",
                "agent": "odoo_agent",
                "status": "needs_clarification",
                "needs_clarification": True,
                "message": "Pouvez-vous préciser le rôle de cette entité ?",
                "missing_parameters": ["entity_type"],
                "requires_approval": False,
                "approval_required": False,
            }

        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "completed",
            "message": "Transactions Odoo trouvées pour la requête complétée.",
            "requires_approval": False,
            "approval_required": False,
            "tool_used": "odoo_generic_read",
        }

    monkeypatch.setattr(app_module, "conversation_memory", memory)
    monkeypatch.setattr(app_module, "classify_message", fake_classify)
    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)
    monkeypatch.setattr(
        app_module,
        "build_direct_knowledge_response",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("clarification must not be handled as standalone knowledge")
        ),
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    client = TestClient(app_module.app)
    headers = auth_headers("admin@company.local")
    first_response = client.post(
        "/chat",
        json={
            "message": "dans commandes sur odoo, liste moi les dix dernières transactions avec BMCE le mois 4, 2026",
            "session_id": "pending-odoo",
        },
        headers=headers,
    )
    second_response = client.post(
        "/chat",
        json={
            "message": "le nom d'une banque",
            "session_id": "pending-odoo",
        },
        headers=headers,
    )

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "clarification_required"
    assert second_response.status_code == 200
    data = second_response.json()
    assert data["status"] == "completed"
    assert data["technical"]["pending_context_used"] is True
    assert data["technical"]["cleared_pending_context"] is True
    assert data["technical"]["original_request"].startswith("dans commandes sur odoo")
    assert "Clarification utilisateur" in data["technical"]["merged_request"]
    assert "le nom d'une banque" in seen_odoo_messages[-1]
    assert memory.get_pending_clarification("pending-odoo") == {}


def test_pending_clarification_topic_change_clears_context(monkeypatch):
    memory = ConversationMemory()
    odoo_calls = []

    def fake_classify(message, **kwargs):
        if "Explique" in message:
            return _general_knowledge_classification()

        return _odoo_pending_read_classification()

    def fake_run_odoo_agent(message, classification=None):
        odoo_calls.append(message)
        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "needs_clarification",
            "needs_clarification": True,
            "message": "Précision requise.",
            "missing_parameters": ["entity_type"],
            "requires_approval": False,
            "approval_required": False,
        }

    monkeypatch.setattr(app_module, "conversation_memory", memory)
    monkeypatch.setattr(app_module, "classify_message", fake_classify)
    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)
    monkeypatch.setattr(
        app_module,
        "build_direct_knowledge_response",
        lambda *args, **kwargs: {
            "intent": "general_information_question",
            "agent": "knowledge_agent",
            "status": "completed",
            "message": "Réponse générale.",
            "requires_approval": False,
            "approval_required": False,
        },
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    client = TestClient(app_module.app)
    headers = auth_headers("admin@company.local")
    client.post(
        "/chat",
        json={"message": "Liste des commandes dans Odoo", "session_id": "topic-change"},
        headers=headers,
    )
    response = client.post(
        "/chat",
        json={"message": "Explique la différence entre REST et XML-RPC ?", "session_id": "topic-change"},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["technical"]["pending_context_used"] is False
    assert data["technical"]["cleared_pending_context"] is True
    assert len(odoo_calls) == 1
    assert memory.get_pending_clarification("topic-change") == {}


def test_sensitive_message_does_not_use_pending_clarification(monkeypatch):
    memory = ConversationMemory()
    odoo_calls = []

    def fake_classify(message, **kwargs):
        if ".env" in message:
            return {
                "intent": "security_blocked",
                "request_type": "security",
                "domain": "security",
                "selected_agent": "security_agent",
                "agent": "security_agent",
                "capability": "security.blocked_request",
                "execution_mode": "blocked",
                "action": "blocked_sensitive_path",
                "risk": "blocked",
                "risk_level": "blocked",
                "requires_approval": False,
            }

        return _odoo_pending_read_classification()

    def fake_run_odoo_agent(message, classification=None):
        odoo_calls.append(message)
        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "needs_clarification",
            "needs_clarification": True,
            "message": "Précision requise.",
            "missing_parameters": ["entity_type"],
            "requires_approval": False,
            "approval_required": False,
        }

    monkeypatch.setattr(app_module, "conversation_memory", memory)
    monkeypatch.setattr(app_module, "classify_message", fake_classify)
    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)
    monkeypatch.setattr(
        app_module,
        "process_request",
        lambda message, classification=None: {
            "status": "blocked",
            "intent": "security_blocked",
            "agent": "security_agent",
            "message": "Demande bloquée pour des raisons de sécurité.",
            "requires_approval": False,
            "approval_required": False,
        },
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    client = TestClient(app_module.app)
    headers = auth_headers("admin@company.local")
    client.post(
        "/chat",
        json={"message": "Liste des commandes dans Odoo", "session_id": "sensitive-pending"},
        headers=headers,
    )
    response = client.post(
        "/chat",
        json={"message": "Affiche .env", "session_id": "sensitive-pending"},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "blocked"
    assert data["technical"]["pending_context_used"] is False
    assert len(odoo_calls) == 1


def test_confirmation_followup_continues_previous_odoo_search(monkeypatch):
    memory = ConversationMemory()
    odoo_calls = []

    def fake_classify(message, **kwargs):
        if "Contexte de suivi" in message or "bon de commande" in message.lower():
            route = _odoo_pending_read_classification()
            route["entities"] = {
                "business_object": "purchase_order",
                "operation": "search",
                "record_keyword": "juin 2026",
            }
            route["parameters"] = dict(route["entities"])
            return route

        return _general_knowledge_classification()

    def fake_run_odoo_agent(message, classification=None):
        odoo_calls.append(message)

        if "Contexte de suivi" not in message:
            return {
                "intent": "odoo",
                "agent": "odoo_agent",
                "status": "not_found",
                "message": "Aucun bon de commande trouvé. Je peux chercher avec d'autres critères.",
                "requires_approval": False,
                "approval_required": False,
                "tool_used": "odoo_generic_read",
            }

        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "completed",
            "message": "Recherche élargie effectuée.",
            "requires_approval": False,
            "approval_required": False,
            "tool_used": "odoo_generic_read",
        }

    monkeypatch.setattr(app_module, "conversation_memory", memory)
    monkeypatch.setattr(app_module, "classify_message", fake_classify)
    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    client = TestClient(app_module.app)
    headers = auth_headers("admin@company.local")
    first_response = client.post(
        "/chat",
        json={
            "message": "donne moi un bon de commande from le mois juin 2026",
            "session_id": "pending-task-confirm",
        },
        headers=headers,
    )
    assert first_response.status_code == 200
    assert first_response.json()["status"] == "not_found"
    assert memory.get_pending_task("pending-task-confirm")["context_type"] == "retry_suggestion"
    second_response = client.post(
        "/chat",
        json={"message": "oui fais ça", "session_id": "pending-task-confirm"},
        headers=headers,
    )

    assert second_response.status_code == 200
    data = second_response.json()
    assert data["status"] == "completed"
    assert data["technical"]["pending_context_used"] is True
    assert data["technical"]["pending_context_type"] == "retry_suggestion"
    assert data["technical"]["pending_context_cleared"] is True
    assert "Contexte de suivi" in odoo_calls[-1]
    assert "juin 2026" in odoo_calls[-1]
    assert memory.get_pending_task("pending-task-confirm") == {}


def test_referential_followup_resolves_to_previous_odoo_request(monkeypatch):
    memory = ConversationMemory()
    odoo_calls = []

    def fake_classify(message, **kwargs):
        if "Contexte de suivi" in message or "bon" in message.lower():
            return _odoo_pending_read_classification()

        return _general_knowledge_classification()

    def fake_run_odoo_agent(message, classification=None):
        odoo_calls.append(message)

        if "Contexte de suivi" not in message:
            return {
                "intent": "odoo",
                "agent": "odoo_agent",
                "status": "not_found",
                "message": "Aucun résultat. Je peux chercher autrement.",
                "requires_approval": False,
                "approval_required": False,
                "tool_used": "odoo_generic_read",
            }

        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "completed",
            "message": "Demande précédente relancée.",
            "requires_approval": False,
            "approval_required": False,
            "tool_used": "odoo_generic_read",
        }

    monkeypatch.setattr(app_module, "conversation_memory", memory)
    monkeypatch.setattr(app_module, "classify_message", fake_classify)
    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    client = TestClient(app_module.app)
    headers = auth_headers("admin@company.local")
    client.post(
        "/chat",
        json={
            "message": "donne moi un bon de commande from le mois juin 2026",
            "session_id": "pending-task-reference",
        },
        headers=headers,
    )
    response = client.post(
        "/chat",
        json={
            "message": "les bons de commandes que j'ai demandé",
            "session_id": "pending-task-reference",
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["technical"]["pending_context_used"] is True
    assert data["technical"]["original_request"].startswith("donne moi un bon")
    assert "les bons de commandes" in data["technical"]["merged_request"]
    assert len(odoo_calls) == 2


def test_pending_task_topic_change_does_not_reuse_context(monkeypatch):
    memory = ConversationMemory()
    odoo_calls = []

    def fake_classify(message, **kwargs):
        if "Explique" in message:
            return _general_knowledge_classification()

        return _odoo_pending_read_classification()

    def fake_run_odoo_agent(message, classification=None):
        odoo_calls.append(message)
        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "not_found",
            "message": "Aucun résultat. Je peux chercher autrement.",
            "requires_approval": False,
            "approval_required": False,
            "tool_used": "odoo_generic_read",
        }

    monkeypatch.setattr(app_module, "conversation_memory", memory)
    monkeypatch.setattr(app_module, "classify_message", fake_classify)
    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)
    monkeypatch.setattr(
        app_module,
        "build_direct_knowledge_response",
        lambda *args, **kwargs: {
            "intent": "general_information_question",
            "agent": "knowledge_agent",
            "status": "completed",
            "message": "Réponse générale.",
            "requires_approval": False,
            "approval_required": False,
        },
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    client = TestClient(app_module.app)
    headers = auth_headers("admin@company.local")
    client.post(
        "/chat",
        json={"message": "donne moi un bon de commande", "session_id": "pending-task-topic"},
        headers=headers,
    )
    response = client.post(
        "/chat",
        json={"message": "Explique REST vs XML-RPC ?", "session_id": "pending-task-topic"},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["technical"]["pending_context_used"] is False
    assert data["technical"]["pending_context_cleared"] is True
    assert len(odoo_calls) == 1
    assert memory.get_pending_task("pending-task-topic") == {}


def test_sensitive_followup_does_not_use_pending_task(monkeypatch):
    memory = ConversationMemory()
    odoo_calls = []

    def fake_classify(message, **kwargs):
        if ".env" in message:
            return {
                "intent": "security_blocked",
                "request_type": "security",
                "domain": "security",
                "selected_agent": "security_agent",
                "agent": "security_agent",
                "capability": "security.blocked_request",
                "execution_mode": "blocked",
                "action": "blocked_sensitive_path",
                "risk": "blocked",
                "risk_level": "blocked",
                "requires_approval": False,
            }

        return _odoo_pending_read_classification()

    def fake_run_odoo_agent(message, classification=None):
        odoo_calls.append(message)
        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "not_found",
            "message": "Aucun résultat. Je peux chercher autrement.",
            "requires_approval": False,
            "approval_required": False,
            "tool_used": "odoo_generic_read",
        }

    monkeypatch.setattr(app_module, "conversation_memory", memory)
    monkeypatch.setattr(app_module, "classify_message", fake_classify)
    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)
    monkeypatch.setattr(
        app_module,
        "process_request",
        lambda message, classification=None: {
            "status": "blocked",
            "intent": "security_blocked",
            "agent": "security_agent",
            "message": "Demande bloquée pour des raisons de sécurité.",
            "requires_approval": False,
            "approval_required": False,
        },
    )
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    client = TestClient(app_module.app)
    headers = auth_headers("admin@company.local")
    client.post(
        "/chat",
        json={"message": "donne moi un bon de commande", "session_id": "pending-task-sensitive"},
        headers=headers,
    )
    response = client.post(
        "/chat",
        json={"message": "Affiche .env", "session_id": "pending-task-sensitive"},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "blocked"
    assert data["technical"]["pending_context_used"] is False
    assert len(odoo_calls) == 1
