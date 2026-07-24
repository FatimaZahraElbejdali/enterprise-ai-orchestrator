from fastapi.testclient import TestClient

from agents.odoo_agent import run as run_odoo_agent
from app import app
from orchestrator.approval_store import create_approval, get_approvals
from tests.auth_helpers import auth_headers


def parsed_price_action(record_query="BACO CLEAN", new_value=25.0):
    return {
        "intent": "odoo",
        "action": "change_price",
        "risk": "medium",
        "requires_approval": True,
        "target_model": "product.template",
        "record_query": record_query,
        "field_label": "Prix de vente",
        "field_name": "list_price",
        "new_value": new_value,
        "confidence": 0.9,
        "parser_source": "test",
        "parser_error": None,
    }


def parsed_stock_action(record_query="BACO CLEAN"):
    return {
        "intent": "odoo",
        "action": "check_stock",
        "risk": "low",
        "requires_approval": False,
        "target_model": "product.template",
        "record_query": record_query,
        "field_label": None,
        "field_name": None,
        "new_value": None,
        "confidence": 0.9,
        "parser_source": "test",
        "parser_error": None,
    }


def parsed_inventory_product_search_action(record_query="nettoyage"):
    return {
        "intent": "odoo",
        "action": "inventory_product_search",
        "business_action": "inventory_product_search",
        "risk": "low",
        "requires_approval": False,
        "target_model": "product.template",
        "record_query": record_query,
        "field_label": None,
        "field_name": None,
        "new_value": None,
        "confidence": 0.9,
        "parser_source": "test",
        "parser_error": None,
    }


def parsed_generic_partner_search_action(record_query="Atlas"):
    return {
        "intent": "odoo",
        "action": "odoo_search_records",
        "business_action": "odoo_search_records",
        "risk": "low",
        "requires_approval": False,
        "target_model": "res.partner",
        "model": "res.partner",
        "record_query": record_query,
        "record_id": None,
        "field_label": None,
        "field_name": None,
        "new_value": None,
        "confidence": 0.9,
        "parser_source": "test",
        "parser_error": None,
    }


def parsed_generic_update_action(
    *,
    model="res.partner",
    record_query="Atlas",
    record_id=None,
    field_name="phone",
    new_value="0600000000",
):
    return {
        "intent": "odoo",
        "action": "odoo_update_field_request",
        "business_action": "odoo_update_field_request",
        "risk": "high",
        "requires_approval": True,
        "target_model": model,
        "model": model,
        "record_query": record_query,
        "record_id": record_id,
        "field_label": field_name,
        "field_name": field_name,
        "new_value": new_value,
        "confidence": 0.9,
        "parser_source": "test",
        "parser_error": None,
    }


def parsed_purchase_expected_arrival_action():
    return {
        "intent": "odoo",
        "action": "update_document_date",
        "risk": "high",
        "requires_approval": True,
        "target_model": "purchase.order",
        "record_query": None,
        "document_query": "BC-BPP2600313",
        "product_query": None,
        "field_label": "Arrivée prévue",
        "field_name": "date_planned",
        "new_value": "2026-06-15",
        "document_type": "purchase_order",
        "document_reference": "BC-BPP2600313",
        "document_id": None,
        "partner_name": None,
        "line_product": None,
        "field": "expected_arrival_date",
        "technical_field": "date_planned",
        "language": "en",
        "needs_clarification": False,
        "clarification_reason": None,
        "confidence": 0.9,
        "parser_source": "test",
        "parser_error": None,
    }


def parsed_purchase_expected_arrival_with_supplier():
    action = parsed_purchase_expected_arrival_action()
    action["partner_name"] = "P.A.N"
    return action


def resolved_product_for_write(name="BACO CLEAN"):
    return {
        "success": True,
        "result": {
            "success": True,
            "found": True,
            "ambiguous": False,
            "product_id": 101,
            "product": {
                "id": 101,
                "name": name,
                "default_code": "PDSBACCLN0001",
                "list_price": 9.0,
                "qty_available": 59.0,
                "virtual_available": 14054.0,
                "sale_ok": True,
                "active": True,
                "uom_id": "Unité(s)",
            },
            "candidates": [
                {
                    "id": 101,
                    "name": name,
                    "default_code": "PDSBACCLN0001",
                    "list_price": 9.0,
                    "qty_available": 59.0,
                    "virtual_available": 14054.0,
                    "sale_ok": True,
                    "active": True,
                    "uom_id": "Unité(s)",
                }
            ],
        },
    }


def test_change_price_request_creates_approval_without_execution(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: parsed_price_action(),
    )

    def fake_execute_tool(tool_name, **kwargs):
        assert tool_name == "odoo_resolve_product_for_write"
        assert kwargs["product_name"] == "BACO CLEAN"
        return resolved_product_for_write()

    monkeypatch.setattr("agents.odoo_agent.execute_tool", fake_execute_tool)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent("Change price of BACO CLEAN to 25 DH")
    approval = get_approvals()[0]

    assert result["status"] == "pending_approval"
    assert result["requires_approval"] is True
    assert result["data"]["executed"] is False
    assert approval["action"] == "change_price"
    assert approval["source_system"] == "odoo"
    assert approval["entity_name"] == "BACO CLEAN"
    assert approval["requested_change"] == "25 DH"
    assert approval["metadata"]["tool_name"] == "odoo_update_product_price"
    assert approval["metadata"]["product_name"] == "BACO CLEAN"
    assert approval["metadata"]["new_price"] == 25.0
    assert approval["executed"] is False


def test_ambiguous_change_price_blocks_approval(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: parsed_price_action(record_query="BACODOR", new_value=7.0),
    )

    def fake_execute_tool(tool_name, **kwargs):
        assert tool_name == "odoo_resolve_product_for_write"
        return {
            "success": True,
            "result": {
                "success": False,
                "found": True,
                "ambiguous": True,
                "message": "Produit ambigu — aucune modification exécutée.",
                "candidates": [
                    {
                        "id": 10,
                        "name": "BACODOR",
                        "default_code": "BACODOR-A",
                        "list_price": 1.0,
                        "qty_available": 44.0,
                    },
                    {
                        "id": 11,
                        "name": "BACODOR",
                        "default_code": "BACODOR-B",
                        "list_price": 0.0,
                        "qty_available": 0.0,
                    },
                ],
            },
        }

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Approval should not be created for ambiguous product")

    monkeypatch.setattr("agents.odoo_agent.execute_tool", fake_execute_tool)
    monkeypatch.setattr("agents.odoo_agent.create_approval", fail_if_called)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent("Modifier le prix de BACODOR à 7 DH")

    assert result["status"] == "ambiguous"
    assert result["approval_required"] is False
    assert result["requires_approval"] is False
    assert result["candidates"][0]["id"] == 10
    assert get_approvals() == []


def test_approve_change_price_executes_tool_and_stores_result(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)

    approval = create_approval(
        user_message="Change price of BACO CLEAN to 25 DH",
        intent="odoo",
        selected_agent="odoo_agent",
        selected_model="policy_engine",
        action="change_price",
        risk="medium",
        source_system="odoo",
        entity_name="BACO CLEAN",
        requested_change="25 DH",
        metadata={
            "tool_name": "odoo_update_product_price",
            "product_name": "BACO CLEAN",
            "new_price": 25.0,
            "executed": False,
        },
    )

    def fake_execute_tool(tool_name, **kwargs):
        assert tool_name == "odoo_update_product_price"
        assert kwargs == {
            "product_name": "BACO CLEAN",
            "new_price": 25.0,
        }

        return {
            "success": True,
            "tool_name": tool_name,
            "result": {
                "success": True,
                "source": "real_odoo",
                "action": "change_price",
                "product": "BACO CLEAN",
                "product_id": 7,
                "old_price": 20.0,
                "new_price": 25.0,
                "executed": True,
                "verified": True,
                "found": True,
                "message": "Product price updated in Odoo.",
            },
        }

    monkeypatch.setattr("app.execute_tool", fake_execute_tool)
    monkeypatch.setattr("app.log_request", lambda data: None)

    client = TestClient(app)
    response = client.post(
        f"/approvals/{approval['id']}/approve",
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["executed"] is True
    assert data["execution_result"]["old_price"] == 20.0
    assert data["execution_result"]["new_price"] == 25.0
    assert data["execution_result"]["verified"] is True


def test_approve_change_price_does_not_mark_executed_when_verification_fails(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)

    approval = create_approval(
        user_message="Change price of BACO CLEAN to 25 DH",
        intent="odoo",
        selected_agent="odoo_agent",
        selected_model="policy_engine",
        action="change_price",
        risk="medium",
        source_system="odoo",
        entity_name="BACO CLEAN",
        requested_change="25 DH",
        metadata={
            "tool_name": "odoo_update_product_price",
            "product_name": "BACO CLEAN",
            "new_price": 25.0,
            "executed": False,
        },
    )

    monkeypatch.setattr(
        "app.execute_tool",
        lambda *args, **kwargs: {
            "success": True,
            "result": {
                "success": False,
                "source": "real_odoo",
                "model": "product.template",
                "action": "change_price",
                "product": "BACO CLEAN",
                "product_id": 7,
                "old_price": 20.0,
                "requested_price": 25.0,
                "new_price": 20.0,
                "executed": False,
                "verified": False,
                "found": True,
                "message": "Read-back verification failed.",
            },
        },
    )
    monkeypatch.setattr("app.log_request", lambda data: None)

    client = TestClient(app)
    response = client.post(
        f"/approvals/{approval['id']}/approve",
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["executed"] is False
    assert data["execution_status"] == "failed"
    assert data["execution_result"]["verified"] is False


def test_approve_change_price_stores_ambiguous_candidates_as_failed(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)

    approval = create_approval(
        user_message="Change price of BACODOR to 7 DH",
        intent="odoo",
        selected_agent="odoo_agent",
        selected_model="policy_engine",
        action="change_price",
        risk="medium",
        source_system="odoo",
        entity_name="BACODOR",
        requested_change="7 DH",
        metadata={
            "tool_name": "odoo_update_product_price",
            "product_name": "BACODOR",
            "new_price": 7.0,
            "executed": False,
        },
    )

    monkeypatch.setattr(
        "app.execute_tool",
        lambda *args, **kwargs: {
            "success": True,
            "result": {
                "success": False,
                "source": "real_odoo",
                "model": "product.template",
                "action": "change_price",
                "product": "BACODOR",
                "product_id": None,
                "old_price": None,
                "requested_price": 7.0,
                "new_price": None,
                "executed": False,
                "verified": False,
                "found": True,
                "ambiguous": True,
                "message": "Produit ambigu — aucune modification exécutée.",
                "candidates": [
                    {
                        "id": 11,
                        "name": "BACODOR",
                        "default_code": "BACODOR-A",
                        "list_price": 1.0,
                        "qty_available": 44,
                        "virtual_available": 5284,
                        "sale_ok": True,
                        "active": True,
                        "uom_id": "Unité(s)",
                    }
                ],
            },
        },
    )
    monkeypatch.setattr("app.log_request", lambda data: None)

    client = TestClient(app)
    response = client.post(
        f"/approvals/{approval['id']}/approve",
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["executed"] is False
    assert data["execution_status"] == "failed"
    assert data["execution_result"]["ambiguous"] is True
    assert data["execution_result"]["candidates"][0]["id"] == 11


def test_approve_document_line_executes_whitelisted_tool(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)

    approval = create_approval(
        user_message="Change price of BACO CLEAN in invoice INV/2026/001 to 7 DH",
        intent="odoo",
        selected_agent="odoo_agent",
        selected_model="policy_engine",
        action="update_document_line",
        risk="high",
        source_system="odoo",
        entity_name="INV/2026/001",
        requested_change=7.0,
        metadata={
            "tool_name": "odoo_update_invoice_line",
            "target_model": "account.move",
            "document_query": "INV/2026/001",
            "product_query": "BACO CLEAN",
            "field_name": "price_unit",
            "new_value": 7.0,
            "executed": False,
        },
    )

    def fake_execute_tool(tool_name, **kwargs):
        assert tool_name == "odoo_update_invoice_line"
        assert kwargs == {
            "invoice_query": "INV/2026/001",
            "product_query": "BACO CLEAN",
            "field": "price_unit",
            "new_value": 7.0,
        }

        return {
            "success": True,
            "tool_name": tool_name,
            "result": {
                "success": True,
                "verified": True,
                "executed": True,
                "model": "account.move",
                "record_id": 90,
                "document": "INV/2026/001",
                "line_id": 15,
                "field": "price_unit",
                "old_value": 3.0,
                "requested_value": 7.0,
                "new_value": 7.0,
                "message": "Document line updated and verified in Odoo.",
                "candidates": [],
            },
        }

    monkeypatch.setattr("app.execute_tool", fake_execute_tool)
    monkeypatch.setattr("app.log_request", lambda data: None)

    client = TestClient(app)
    response = client.post(
        f"/approvals/{approval['id']}/approve",
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["executed"] is True
    assert data["execution_status"] == "completed"
    assert data["execution_result"]["document"] == "INV/2026/001"
    assert data["execution_result"]["line_id"] == 15
    assert data["execution_result"]["verified"] is True


def test_purchase_expected_arrival_chat_creates_approval_without_execution(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: parsed_purchase_expected_arrival_action(),
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Odoo write should not execute from chat")

    monkeypatch.setattr("agents.odoo_agent.execute_tool", fail_if_called)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent(
        "Change the expected arrival date of purchase order BC-BPP2600313 to 2026-06-15"
    )
    approval = get_approvals()[0]

    assert result["status"] == "pending_approval"
    assert result["requires_approval"] is True
    assert result["data"]["executed"] is False
    assert approval["action"] == "update_document_date"
    assert approval["entity_name"] == "BC-BPP2600313"
    assert approval["requested_change"] == "2026-06-15"
    assert approval["metadata"]["tool_name"] == "odoo_update_document_date"
    assert approval["metadata"]["target_model"] == "purchase.order"
    assert approval["metadata"]["document_query"] == "BC-BPP2600313"
    assert approval["metadata"]["field_name"] == "date_planned"
    assert approval["metadata"]["technical_field"] == "date_planned"
    assert approval["metadata"]["field"] == "expected_arrival_date"
    assert approval["metadata"]["new_value"] == "2026-06-15"
    assert approval["executed"] is False


def test_purchase_expected_arrival_with_supplier_metadata(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: parsed_purchase_expected_arrival_with_supplier(),
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Odoo write should not execute from chat")

    monkeypatch.setattr("agents.odoo_agent.execute_tool", fail_if_called)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent(
        "Change the expected arrival date of purchase order BC-BPP2600313 for supplier P.A.N to 2026-06-15"
    )
    approval = get_approvals()[0]

    assert result["status"] == "pending_approval"
    assert approval["metadata"]["document_type_key"] == "purchase_order"
    assert approval["metadata"]["document_reference"] == "BC-BPP2600313"
    assert approval["metadata"]["document_id"] is None
    assert approval["metadata"]["partner_name"] == "P.A.N"
    assert approval["metadata"]["field"] == "expected_arrival_date"
    assert approval["metadata"]["technical_field"] == "date_planned"
    assert approval["metadata"]["new_value"] == "2026-06-15"
    assert approval["executed"] is False


def test_missing_document_new_value_returns_clarification_without_approval(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: {
            **parsed_purchase_expected_arrival_action(),
            "new_value": None,
            "needs_clarification": True,
            "clarification_reason": "nouvelle valeur",
        },
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Approval should not be created for incomplete request")

    monkeypatch.setattr("agents.odoo_agent.create_approval", fail_if_called)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent(
        "Change the expected arrival date of purchase order BC-BPP2600313"
    )

    assert result["status"] == "needs_clarification"
    assert result["approval_required"] is False
    assert get_approvals() == []


def test_unsupported_document_action_returns_safe_response(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: {
            "intent": "odoo_document_action",
            "action": "unknown",
            "risk": "low",
            "requires_approval": False,
            "target_model": None,
            "record_query": None,
            "document_query": None,
            "product_query": None,
            "field_label": None,
            "field_name": None,
            "new_value": None,
            "document_type": "unknown",
            "document_reference": None,
            "document_id": None,
            "partner_name": None,
            "line_product": None,
            "field": "unknown",
            "technical_field": None,
            "language": "en",
            "needs_clarification": False,
            "clarification_reason": "Unsupported Odoo document action.",
            "confidence": 0.2,
            "parser_source": "test",
            "parser_error": None,
        },
    )

    result = run_odoo_agent("Archive purchase order BC-BPP2600313")

    assert result["status"] == "unsupported"
    assert result["approval_required"] is False
    assert result["data"]["executed"] is False
    assert get_approvals() == []


def test_approve_purchase_expected_arrival_executes_and_verifies(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)

    approval = create_approval(
        user_message="Change the expected arrival date of purchase order BC-BPP2600313 to 2026-06-15",
        intent="odoo",
        selected_agent="odoo_agent",
        selected_model="policy_engine",
        action="update_document_date",
        risk="high",
        source_system="odoo",
        entity_name="BC-BPP2600313",
        requested_change="2026-06-15",
        metadata={
            "tool_name": "odoo_update_document_date",
            "target_model": "purchase.order",
            "document_query": "BC-BPP2600313",
            "field_name": "date_planned",
            "date_field": "date_planned",
            "new_value": "2026-06-15",
            "new_date": "2026-06-15",
            "executed": False,
        },
    )

    def fake_execute_tool(tool_name, **kwargs):
        assert tool_name == "odoo_update_document_date"
        assert kwargs == {
            "model_name": "purchase.order",
            "document_query": "BC-BPP2600313",
            "date_field": "date_planned",
            "new_date": "2026-06-15",
        }

        return {
            "success": True,
            "tool_name": tool_name,
            "result": {
                "success": True,
                "verified": True,
                "executed": True,
                "model": "purchase.order",
                "record_id": 700,
                "document": "BC-BPP2600313",
                "line_ids": [701, 702],
                "field": "date_planned",
                "old_value": [
                    {"line_id": 701, "date_planned": "2026-06-10"},
                    {"line_id": 702, "date_planned": "2026-06-10"},
                ],
                "requested_value": "2026-06-15",
                "new_value": [
                    {"line_id": 701, "date_planned": "2026-06-15"},
                    {"line_id": 702, "date_planned": "2026-06-15"},
                ],
                "message": "Purchase order expected arrival date updated and verified in Odoo.",
                "candidates": [],
            },
        }

    monkeypatch.setattr("app.execute_tool", fake_execute_tool)
    monkeypatch.setattr("app.log_request", lambda data: None)

    client = TestClient(app)
    response = client.post(
        f"/approvals/{approval['id']}/approve",
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["executed"] is True
    assert data["execution_status"] == "completed"
    assert data["execution_result"]["field"] == "date_planned"
    assert data["execution_result"]["verified"] is True


def test_approve_purchase_expected_arrival_passes_supplier_to_executor(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)

    approval = create_approval(
        user_message="Change the expected arrival date of purchase order BC-BPP2600313 for supplier P.A.N to 2026-06-15",
        intent="odoo",
        selected_agent="odoo_agent",
        selected_model="policy_engine",
        action="update_document_date",
        risk="high",
        source_system="odoo",
        entity_name="BC-BPP2600313",
        requested_change="2026-06-15",
        metadata={
            "tool_name": "odoo_update_document_date",
            "target_model": "purchase.order",
            "document_type_key": "purchase_order",
            "document_reference": "BC-BPP2600313",
            "document_query": "BC-BPP2600313",
            "document_id": None,
            "partner_name": "P.A.N",
            "field": "expected_arrival_date",
            "technical_field": "date_planned",
            "field_name": "date_planned",
            "date_field": "date_planned",
            "new_value": "2026-06-15",
            "new_date": "2026-06-15",
            "executed": False,
        },
    )

    def fake_execute_tool(tool_name, **kwargs):
        assert tool_name == "odoo_update_document_date"
        assert kwargs == {
            "model_name": "purchase.order",
            "document_query": "BC-BPP2600313",
            "date_field": "date_planned",
            "new_date": "2026-06-15",
            "partner_name": "P.A.N",
        }

        return {
            "success": True,
            "tool_name": tool_name,
            "result": {
                "success": True,
                "verified": True,
                "executed": True,
                "model": "purchase.order",
                "record_id": 793,
                "document": "BC-BPP2600313",
                "field": "date_planned",
                "requested_value": "2026-06-15",
                "new_value": [{"line_id": 801, "date_planned": "2026-06-15"}],
                "message": "Purchase order expected arrival date updated and verified in Odoo.",
            },
        }

    monkeypatch.setattr("app.execute_tool", fake_execute_tool)
    monkeypatch.setattr("app.log_request", lambda data: None)

    client = TestClient(app)
    response = client.post(
        f"/approvals/{approval['id']}/approve",
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["executed"] is True
    assert data["execution_result"]["record_id"] == 793


def test_reject_change_price_does_not_execute_tool(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)

    approval = create_approval(
        user_message="Change price of BACO CLEAN to 25 DH",
        intent="odoo",
        selected_agent="odoo_agent",
        action="change_price",
        source_system="odoo",
        entity_name="BACO CLEAN",
        requested_change="25 DH",
        metadata={
            "tool_name": "odoo_update_product_price",
            "product_name": "BACO CLEAN",
            "new_price": 25.0,
        },
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Odoo write should not execute when rejected")

    monkeypatch.setattr("app.execute_tool", fail_if_called)
    monkeypatch.setattr("app.log_request", lambda data: None)

    client = TestClient(app)
    response = client.post(
        f"/approvals/{approval['id']}/reject",
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["executed"] is False


def test_check_stock_still_does_not_require_approval(monkeypatch):
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: parsed_stock_action(),
    )
    monkeypatch.setattr(
        "agents.odoo_agent.execute_tool",
        lambda *args, **kwargs: {
            "success": True,
            "result": {
                "source": "real_odoo",
                "product": "BACO CLEAN",
                "product_id": 7,
                "stock_quantity": 12,
                "forecast_quantity": 12,
                "list_price": 25.0,
                "sale_price": 25.0,
                "unit": "Unité(s)",
                "found": True,
            },
        },
    )
    monkeypatch.setattr("agents.odoo_agent.create_approval", lambda *args, **kwargs: None)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent("Check stock for BACO CLEAN")

    assert result["approval_required"] is False
    assert result["requires_approval"] is False
    assert result["tool_used"] == "odoo_check_stock"
    assert result["parser_source"] == "test"
    assert result["parsed_action"] == "check_product_stock"
    assert result["product_name"] == "BACO CLEAN"
    assert result["needs_clarification"] is False


def test_check_stock_connector_error_is_not_reported_as_not_found(monkeypatch):
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: parsed_stock_action(),
    )
    monkeypatch.setattr(
        "agents.odoo_agent.execute_tool",
        lambda *args, **kwargs: {
            "success": True,
            "result": {
                "source": "real_odoo_error",
                "product": kwargs["product_name"],
                "found": False,
                "message": "connection failed",
            },
        },
    )
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent("Check stock for BACO CLEAN")

    assert result["status"] == "failed"
    assert result["approval_required"] is False
    assert result["tool_used"] == "odoo_check_stock"
    assert "indisponible" in result["message"]
    assert "pas été trouvé" not in result["message"]


def test_bank_accounting_search_returns_safe_summary(monkeypatch):
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: {
            "intent": "odoo",
            "action": "bank_accounting_search",
            "business_action": "bank_accounting_search",
            "risk": "low",
            "requires_approval": False,
            "target_model": "account.bank.statement",
            "model": "account.bank.statement",
            "record_query": "TEST BANK",
            "confidence": 0.8,
            "parser_source": "test",
            "parser_error": None,
        },
    )
    monkeypatch.setattr(
        "agents.odoo_agent.execute_tool",
        lambda *args, **kwargs: {
            "success": True,
            "result": {
                "success": True,
                "source": "real_odoo",
                "status": "completed",
                "found": True,
                "selected_model": "account.bank.statement.line",
                "model": "account.bank.statement.line",
                "fields_used": ["id", "name", "date", "journal_id", "amount"],
                "domain_used": [["date", ">=", "2026-06-01"], ["date", "<", "2026-07-01"]],
                "count_returned": 1,
                "record_count": 1,
                "records": [
                    {
                        "id": 42,
                        "model": "account.bank.statement.line",
                        "document": "TEST BANK Juin",
                        "date": "2026-06-12",
                        "journal": "TEST BANK",
                        "amount": 99.0,
                    }
                ],
            },
        },
    )
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent(
        "Donne-moi les informations sur un relevé bancaire de TEST BANK en juin 2026"
    )

    assert result["status"] == "completed"
    assert result["tool_used"] == "odoo_search_bank_accounting"
    assert result["capability"] == "odoo.accounting_bank_read"
    assert result["selected_model_name"] == "account.bank.statement.line"
    assert result["fields_used"] == ["id", "name", "date", "journal_id", "amount"]
    assert result["count_returned"] == 1
    assert "TEST BANK" in result["message"]
    assert "api_key" not in result["message"]
    assert result["approval_required"] is False


def test_supplier_ranking_returns_ranked_supplier_summary(monkeypatch):
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: {
            "intent": "odoo",
            "action": "supplier_ranking",
            "business_action": "supplier_ranking",
            "risk": "low",
            "requires_approval": False,
            "target_model": "purchase.order",
            "model": "purchase.order",
            "field_name": "partner_id",
            "confidence": 0.8,
            "parser_source": "test",
            "parser_error": None,
        },
    )
    monkeypatch.setattr(
        "agents.odoo_agent.execute_tool",
        lambda *args, **kwargs: {
            "success": True,
            "result": {
                "success": True,
                "status": "completed",
                "found": True,
                "selected_model": "purchase.order",
                "aggregation_field": "partner_id",
                "odoo_method": "read_group",
                "domain_used": [],
                "fields_used": ["partner_id"],
                "count_returned": 2,
                "record_count": 2,
                "records": [
                    {"supplier_id": 10, "supplier": "Supplier A", "count": 8},
                    {"supplier_id": 20, "supplier": "Supplier B", "count": 5},
                ],
            },
        },
    )
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent(
        "Quels fournisseurs apparaissent le plus dans les bons de commande ?"
    )

    assert result["status"] == "completed"
    assert result["tool_used"] == "odoo_rank_purchase_order_suppliers"
    assert result["capability"] == "odoo.purchase_supplier_ranking"
    assert result["selected_model_name"] == "purchase.order"
    assert result["aggregation_field"] == "partner_id"
    assert result["odoo_method"] == "read_group"
    assert "Supplier A : 8" in result["message"]
    assert "Introuvable" not in result["message"]


def test_customer_ranking_returns_ranked_customer_summary(monkeypatch):
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: {
            "intent": "odoo",
            "action": "customer_ranking",
            "business_action": "customer_ranking",
            "risk": "low",
            "requires_approval": False,
            "target_model": "sale.order",
            "model": "sale.order",
            "field_name": "partner_id",
            "record_query": None,
            "new_value": None,
            "confidence": 0.9,
            "parser_source": "test",
            "parser_error": None,
        },
    )
    monkeypatch.setattr(
        "agents.odoo_agent.execute_tool",
        lambda *args, **kwargs: {
            "success": True,
            "result": {
                "success": True,
                "status": "completed",
                "found": True,
                "selected_model": "sale.order",
                "aggregation_field": "partner_id",
                "odoo_method": "read_group",
                "domain_used": [],
                "fields_used": ["partner_id"],
                "count_returned": 2,
                "record_count": 2,
                "records": [
                    {"customer_id": 10, "customer": "Client A", "count": 8},
                    {"customer_id": 20, "customer": "Client B", "count": 5},
                ],
            },
        },
    )
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent(
        "Quels clients apparaissent le plus dans les commandes client ?"
    )

    assert result["status"] == "completed"
    assert result["tool_used"] == "odoo_rank_sale_order_customers"
    assert result["capability"] == "odoo.sale_customer_ranking"
    assert result["selected_model_name"] == "sale.order"
    assert result["aggregation_field"] == "partner_id"
    assert result["odoo_method"] == "read_group"
    assert "Client A : 8" in result["message"]


def test_odoo_connection_status_uses_registered_status_tool(monkeypatch):
    captured = {}

    def fake_execute_tool(tool_name, **kwargs):
        captured["tool_name"] = tool_name
        return {
            "success": True,
            "result": {
                "connected": True,
                "mode": "real_odoo",
                "message": "Successfully connected to Odoo.",
            },
        }

    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: {
            "intent": "odoo",
            "action": "odoo_status",
            "business_action": "odoo_status",
            "risk": "low",
            "requires_approval": False,
            "target_model": None,
            "record_query": None,
            "field_label": None,
            "field_name": None,
            "new_value": None,
            "confidence": 0.9,
            "parser_source": "test",
            "parser_error": None,
        },
    )
    monkeypatch.setattr("agents.odoo_agent.execute_tool", fake_execute_tool)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent("Est-ce que Odoo est connecté ?")

    assert captured["tool_name"] == "odoo_test_connection"
    assert result["status"] == "completed"
    assert result["tool_used"] == "odoo_test_connection"
    assert result["capability"] == "odoo.connection_status"
    assert "connecté" in result["message"]


def test_product_details_uses_stock_resolver_with_clean_product_query(monkeypatch):
    captured = {}

    def fake_execute_tool(tool_name, **kwargs):
        captured["call"] = {
            "tool_name": tool_name,
            "kwargs": kwargs,
        }
        return {
            "success": True,
            "result": {
                "success": True,
                "source": "real_odoo",
                "model": "product.product",
                "product": kwargs["product_name"],
                "found": True,
                "internal_reference": "PDSBACCLN0001",
                "stock_quantity": 12,
                "forecast_quantity": 14,
                "sale_price": 4.0,
                "unit": "Unité(s)",
            },
        }

    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: {
            "intent": "odoo",
            "action": "check_stock",
            "business_action": "product_details",
            "risk": "low",
            "requires_approval": False,
            "target_model": "product.template",
            "record_query": "BACO CLEAN",
            "field_label": None,
            "field_name": None,
            "new_value": None,
            "confidence": 0.9,
            "parser_source": "test",
            "parser_error": None,
        },
    )
    monkeypatch.setattr("agents.odoo_agent.execute_tool", fake_execute_tool)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent("Donne-moi les détails du produit BACO CLEAN")

    assert captured["call"]["tool_name"] == "odoo_check_stock"
    assert captured["call"]["kwargs"]["product_name"] == "BACO CLEAN"
    assert result["status"] == "completed"
    assert result["tool_used"] == "odoo_check_stock"
    assert result["data"]["product_name"] == "BACO CLEAN"
    assert result["data"]["internal_reference"] == "PDSBACCLN0001"
    assert result["data"]["available_stock"] == 12
    assert result["data"]["forecast_stock"] == 14
    assert result["data"]["sale_price"] == 4.0


def test_inventory_product_search_calls_odoo_with_extracted_keyword(monkeypatch):
    captured = {}

    def fake_execute_tool(tool_name, **kwargs):
        captured["call"] = {
            "tool_name": tool_name,
            "kwargs": kwargs,
        }
        return {
            "success": True,
            "result": {
                "success": True,
                "source": "real_odoo",
                "model": "product.product",
                "product": kwargs["product_name"],
                "found": True,
                "results": [
                    {
                        "id": 21,
                        "name": "NETTOYAGE SOL",
                        "default_code": "NET-SOL",
                        "qty_available": 18,
                    }
                ],
            },
        }

    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: parsed_inventory_product_search_action(),
    )
    monkeypatch.setattr(
        "agents.odoo_agent.execute_tool",
        fake_execute_tool,
    )
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent(
        "Est-ce que les produits de nettoyage sont intégrés dans l’inventaire Odoo ?"
    )

    assert captured["call"]["tool_name"] == "odoo_search_product"
    assert captured["call"]["kwargs"]["product_name"] == "nettoyage"
    assert result["approval_required"] is False
    assert result["parsed_action"] == "inventory_product_search"
    assert result["tool_used"] == "odoo_search_product"
    assert result["status"] == "completed"
    assert "NETTOYAGE SOL" in result["message"]
    assert "NET-SOL" in result["message"]
    assert "Produits correspondants trouvés" not in result["message"]
    assert result["result"]["results"][0]["default_code"] == "NET-SOL"


def test_product_existence_uses_specialized_search_before_generic_read(monkeypatch):
    captured = {}

    def fake_execute_tool(tool_name, **kwargs):
        captured["call"] = {
            "tool_name": tool_name,
            "kwargs": kwargs,
        }
        return {
            "success": True,
            "result": {
                "success": True,
                "source": "mock_odoo",
                "model": "product.product",
                "product": kwargs["product_name"],
                "found": True,
                "results": [
                    {
                        "id": 99,
                        "name": "TEST PRODUCT",
                        "default_code": "TEST-PROD",
                        "qty_available": 3,
                    }
                ],
            },
        }

    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: parsed_inventory_product_search_action(record_query="TEST PRODUCT"),
    )
    monkeypatch.setattr("agents.odoo_agent.execute_tool", fake_execute_tool)
    monkeypatch.setattr(
        "agents.odoo_agent.run_odoo_read_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("generic Odoo read agent should not handle product existence")
        ),
    )
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent(
        "Vérifie si l'article TEST PRODUCT existe dans le stock Odoo",
        classification={
            "domain": "odoo",
            "target_system": "odoo",
            "selected_agent": "odoo_agent",
            "action": "read_odoo",
            "risk_level": "low",
            "requires_approval": False,
        },
    )

    assert captured["call"]["tool_name"] == "odoo_search_product"
    assert captured["call"]["kwargs"]["product_name"] == "TEST PRODUCT"
    assert result["status"] == "completed"
    assert result["tool_used"] == "odoo_search_product"
    assert result["parsed_action"] == "inventory_product_search"
    assert result["result"]["results"][0]["name"] == "TEST PRODUCT"
    assert "Précision requise" not in result["message"]


def test_inventory_product_search_not_found_returns_clean_message(monkeypatch):
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: parsed_inventory_product_search_action(record_query="xyz"),
    )
    monkeypatch.setattr(
        "agents.odoo_agent.execute_tool",
        lambda *args, **kwargs: {
            "success": True,
            "result": {
                "success": True,
                "source": "real_odoo",
                "model": "product.product",
                "product": kwargs["product_name"],
                "found": False,
                "results": [],
            },
        },
    )
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent("Les produits de type xyz existent-ils dans Odoo ?")

    assert result["status"] == "not_found"
    assert result["approval_required"] is False
    assert result["message"]
    assert result["result"]["product"] == "xyz"
    assert result["result"]["results"] == []
    assert "Aucun produit correspondant trouvé" not in result["message"]
    assert "JSON" not in result["message"]


def test_generic_partner_search_uses_safe_record_search(monkeypatch):
    captured = {}

    def fake_execute_tool(tool_name, **kwargs):
        captured["tool_name"] = tool_name
        captured["kwargs"] = kwargs
        return {
            "success": True,
            "result": {
                "success": True,
                "source": "real_odoo",
                "model": "res.partner",
                "keyword": kwargs["keyword"],
                "found": True,
                "records": [
                    {
                        "id": 31,
                        "model": "res.partner",
                        "name": "Atlas",
                        "type": "client",
                        "phone": "0612345678",
                    }
                ],
            },
        }

    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: parsed_generic_partner_search_action(),
    )
    monkeypatch.setattr("agents.odoo_agent.execute_tool", fake_execute_tool)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent("Rechercher le client Atlas dans Odoo")

    assert captured["tool_name"] == "odoo_search_records"
    assert captured["kwargs"]["model_name"] == "res.partner"
    assert captured["kwargs"]["keyword"] == "Atlas"
    assert result["approval_required"] is False
    assert result["status"] == "completed"
    assert result["result"]["records"][0]["phone"] == "0612345678"


def test_generic_record_search_ambiguous_asks_clarification(monkeypatch):
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: parsed_generic_partner_search_action(),
    )
    monkeypatch.setattr(
        "agents.odoo_agent.execute_tool",
        lambda *args, **kwargs: {
            "success": True,
            "result": {
                "success": False,
                "source": "real_odoo",
                "model": "res.partner",
                "keyword": kwargs["keyword"],
                "found": True,
                "ambiguous": True,
                "candidates": [
                    {"id": 31, "name": "Atlas A"},
                    {"id": 32, "name": "Atlas B"},
                ],
            },
        },
    )
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent("Afficher la fiche du client Atlas")

    assert result["status"] == "needs_clarification"
    assert "Plusieurs enregistrements" in result["message"]
    assert result["approval_required"] is False


def test_allowed_generic_partner_field_update_creates_approval(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: parsed_generic_update_action(),
    )
    monkeypatch.setattr(
        "agents.odoo_agent.execute_tool",
        lambda *args, **kwargs: {
            "success": True,
            "result": {
                "success": True,
                "source": "real_odoo",
                "model": kwargs["model_name"],
                "field_name": kwargs["field_name"],
                "record_id": 31,
                "record_name": "Atlas",
                "old_value": "0612345678",
                "new_value": kwargs["new_value"],
                "found": True,
                "ambiguous": False,
            },
        },
    )
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent("Modifier le téléphone du client Atlas à 0600000000")
    approval = get_approvals()[0]

    assert result["status"] == "pending_approval"
    assert result["approval_required"] is True
    assert approval["action"] == "odoo_update_field_request"
    assert approval["metadata"]["tool_name"] == "odoo_update_field"
    assert approval["metadata"]["target_model"] == "res.partner"
    assert approval["metadata"]["record_id"] == 31
    assert approval["metadata"]["field_name"] == "phone"
    assert approval["metadata"]["old_value"] == "0612345678"
    assert approval["metadata"]["new_value"] == "0600000000"


def test_generic_unsupported_write_field_returns_clean_unsupported(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: parsed_generic_update_action(field_name="comment", new_value="note"),
    )
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent("Modifier la note du client Atlas")

    assert result["status"] == "unsupported"
    assert result["message"] == (
        "Je comprends la modification demandée, mais cette opération n'est pas "
        "encore connectée à un outil Odoo sécurisé."
    )
    assert result["approval_required"] is False
    assert get_approvals() == []


def test_missing_product_price_returns_clarification_without_approval(monkeypatch):
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: {
            **parsed_price_action(record_query="BACO+", new_value=None),
            "needs_clarification": True,
            "clarification_reason": "nouveau prix",
            "language": "fr",
        },
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Approval should not be created without a new price")

    monkeypatch.setattr("agents.odoo_agent.create_approval", fail_if_called)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent("Modifier le prix de BACO+")

    assert result["status"] == "needs_clarification"
    assert result["approval_required"] is False
    assert result["requires_approval"] is False
    assert result["parser_source"] == "test"
    assert result["parsed_action"] == "update_product_price"
    assert result["product_name"] == "BACO+"


def test_chat_routes_french_odoo_document_request_to_odoo_agent(monkeypatch):
    def fake_run_odoo_agent(message):
        assert message == "Montre-moi les détails de la facture FNP/2026/04016"
        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "completed",
            "message": "Document consulté avec succès.",
            "parser_source": "openai",
            "language": "fr",
            "parsed_action": "search_document",
            "document_type": "invoice",
            "document_reference": "FNP/2026/04016",
            "requires_approval": False,
            "approval_required": False,
        }

    monkeypatch.setattr("app.run_odoo_agent", fake_run_odoo_agent)

    client = TestClient(app)
    response = client.post(
        "/chat",
        json={"message": "Montre-moi les détails de la facture FNP/2026/04016"},
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["technical"]["agent"] == "odoo_agent"
    assert data["technical"]["parser_source"] == "openai"
    assert data["technical"]["action"] == "search_document"


def test_toggle_analytic_boolean_creates_approval_without_execution(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: {
            "intent": "odoo",
            "action": "toggle_boolean_field",
            "risk": "medium",
            "requires_approval": True,
            "target_model": "account.analytic.account",
            "record_query": "ABDOU LIGHT & SOUNDS",
            "field_label": "Dotation",
            "field_name": None,
            "new_value": True,
            "confidence": 0.9,
            "parser_source": "test",
            "parser_error": None,
        },
    )

    def fake_execute_tool(tool_name, **kwargs):
        if tool_name == "odoo_list_analytic_boolean_fields":
            return {
                "success": True,
                "result": {
                    "success": True,
                    "model": "account.analytic.account",
                    "fields": [
                        {
                            "name": "x_dotation",
                            "label": "Dotation",
                            "type": "boolean",
                            "readonly": False,
                        },
                    ],
                },
            }

        if tool_name == "odoo_resolve_analytic_account":
            assert kwargs == {"record_query": "ABDOU LIGHT & SOUNDS"}
            return {
                "success": True,
                "result": {
                    "success": True,
                    "model": "account.analytic.account",
                    "record_query": "ABDOU LIGHT & SOUNDS",
                    "record_id": 9,
                    "record": "ABDOU LIGHT & SOUNDS",
                    "record_name": "ABDOU LIGHT & SOUNDS",
                    "found": True,
                    "ambiguous": False,
                    "candidates": [
                        {
                            "record_id": 9,
                            "name": "ABDOU LIGHT & SOUNDS",
                            "display_name": "ABDOU LIGHT & SOUNDS",
                        },
                    ],
                },
            }

        raise AssertionError(f"Unexpected tool: {tool_name}")

    monkeypatch.setattr("agents.odoo_agent.execute_tool", fake_execute_tool)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent("Cocher Dotation pour ABDOU LIGHT & SOUNDS")
    approval = get_approvals()[0]

    assert result["status"] == "pending_approval"
    assert approval["action"] == "toggle_boolean_field"
    assert approval["metadata"]["tool_name"] == "odoo_update_analytic_boolean_field"
    assert approval["metadata"]["model"] == "account.analytic.account"
    assert approval["metadata"]["record_query"] == "ABDOU LIGHT & SOUNDS"
    assert approval["metadata"]["record_id"] == 9
    assert approval["metadata"]["field_label"] == "Dotation"
    assert approval["metadata"]["field_name"] == "x_dotation"
    assert approval["metadata"]["new_value"] is True


def test_pointage_prompt_creates_approval_not_status_response(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)
    monkeypatch.setattr(
        "agents.odoo_agent.generate_structured_response",
        lambda **kwargs: {
            "success": False,
            "parsed": None,
            "error": "provider_unavailable",
        },
    )

    def fake_execute_tool(tool_name, **kwargs):
        if tool_name == "odoo_list_analytic_boolean_fields":
            return {
                "success": True,
                "result": {
                    "success": True,
                    "model": "account.analytic.account",
                    "fields": [
                        {
                            "name": "x_studio_pointage",
                            "label": "Pointage",
                            "type": "boolean",
                            "readonly": False,
                        },
                    ],
                },
            }

        if tool_name == "odoo_resolve_analytic_account":
            assert kwargs == {"record_query": "11IFCX0003"}
            return {
                "success": True,
                "result": {
                    "success": True,
                    "model": "account.analytic.account",
                    "record_query": "11IFCX0003",
                    "record_id": 5935,
                    "record": "11IFCX0003",
                    "record_name": "11IFCX0003",
                    "record_code": "11IFCX0003",
                    "found": True,
                    "ambiguous": False,
                    "candidates": [
                        {
                            "record_id": 5935,
                            "name": "11IFCX0003",
                            "display_name": "11IFCX0003",
                            "code": "11IFCX0003",
                        },
                    ],
                },
            }

        raise AssertionError(f"Unexpected tool: {tool_name}")

    monkeypatch.setattr("agents.odoo_agent.execute_tool", fake_execute_tool)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent(
        "coche pointage pour le compte analytique 11IFCX0003 sur odoo"
    )
    approval = get_approvals()[0]

    assert result["status"] == "pending_approval"
    assert result["parsed_action"] == "toggle_boolean_field"
    assert result["data"]["action"] == "toggle_boolean_field"
    assert result["tool_used"] != "odoo_test_connection"
    assert "Odoo est connecté" not in result["message"]
    assert approval["action"] == "toggle_boolean_field"
    assert approval["metadata"]["model"] == "account.analytic.account"
    assert approval["metadata"]["record_query"] == "11IFCX0003"
    assert approval["metadata"]["record_id"] == 5935
    assert approval["metadata"]["field_name"] == "x_studio_pointage"
    assert approval["metadata"]["new_value"] is True


def test_pointage_reference_resolves_analytic_account_before_approval(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)
    monkeypatch.setattr(
        "agents.odoo_agent.generate_structured_response",
        lambda **kwargs: {
            "success": False,
            "parsed": None,
            "error": "provider_unavailable",
        },
    )
    calls = []

    def fake_execute_tool(tool_name, **kwargs):
        calls.append((tool_name, kwargs))

        if tool_name == "odoo_list_analytic_boolean_fields":
            return {
                "success": True,
                "result": {
                    "success": True,
                    "model": "account.analytic.account",
                    "fields": [
                        {
                            "name": "x_studio_pointage",
                            "label": "Pointage",
                            "type": "boolean",
                            "readonly": False,
                        },
                    ],
                },
            }

        if tool_name == "odoo_resolve_analytic_account":
            assert kwargs == {"record_query": "11SOCM0001"}
            return {
                "success": True,
                "result": {
                    "success": True,
                    "model": "account.analytic.account",
                    "record_query": "11SOCM0001",
                    "record_id": 5935,
                    "record": "11SOCM0001 Services",
                    "record_name": "11SOCM0001 Services",
                    "record_code": "11SOCM0001",
                    "found": True,
                    "ambiguous": False,
                    "candidates": [
                        {
                            "record_id": 5935,
                            "name": "11SOCM0001 Services",
                            "display_name": "11SOCM0001 Services",
                            "code": "11SOCM0001",
                        },
                    ],
                },
            }

        raise AssertionError(f"Unexpected tool: {tool_name}")

    monkeypatch.setattr("agents.odoo_agent.execute_tool", fake_execute_tool)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent(
        "coche pointage pour le compte analytique 11SOCM0001 sur odoo"
    )
    approval = get_approvals()[0]

    assert result["status"] == "pending_approval"
    assert result["data"]["record_id"] == 5935
    assert "record_id" not in result["message"].lower()
    assert approval["metadata"]["record_query"] == "11SOCM0001"
    assert approval["metadata"]["record_id"] == 5935
    assert approval["metadata"]["record_name"] == "11SOCM0001 Services"
    assert approval["metadata"]["field_name"] == "x_studio_pointage"
    assert ("odoo_resolve_analytic_account", {"record_query": "11SOCM0001"}) in calls


def test_pointage_ambiguous_analytic_reference_asks_user_to_choose(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)
    monkeypatch.setattr(
        "agents.odoo_agent.generate_structured_response",
        lambda **kwargs: {
            "success": False,
            "parsed": None,
            "error": "provider_unavailable",
        },
    )

    def fake_execute_tool(tool_name, **kwargs):
        if tool_name == "odoo_list_analytic_boolean_fields":
            return {
                "success": True,
                "result": {
                    "success": True,
                    "model": "account.analytic.account",
                    "fields": [
                        {
                            "name": "x_studio_pointage",
                            "label": "Pointage",
                            "type": "boolean",
                            "readonly": False,
                        },
                    ],
                },
            }

        if tool_name == "odoo_resolve_analytic_account":
            return {
                "success": True,
                "result": {
                    "success": False,
                    "model": "account.analytic.account",
                    "record_query": "11SOCM0001",
                    "record_id": None,
                    "found": True,
                    "ambiguous": True,
                    "candidates": [
                        {"record_id": 5935, "name": "11SOCM0001 A"},
                        {"record_id": 5936, "name": "11SOCM0001 B"},
                    ],
                },
            }

        raise AssertionError(f"Unexpected tool: {tool_name}")

    monkeypatch.setattr("agents.odoo_agent.execute_tool", fake_execute_tool)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent(
        "coche pointage pour le compte analytique 11SOCM0001 sur odoo"
    )

    assert result["status"] in {"ambiguous", "clarification_required"}
    assert result["approval_required"] is False
    assert result["requires_approval"] is False
    assert len(result["data"]["candidates"]) == 2
    assert get_approvals() == []


def test_pointage_missing_analytic_reference_returns_not_found(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)
    monkeypatch.setattr(
        "agents.odoo_agent.generate_structured_response",
        lambda **kwargs: {
            "success": False,
            "parsed": None,
            "error": "provider_unavailable",
        },
    )

    def fake_execute_tool(tool_name, **kwargs):
        if tool_name == "odoo_list_analytic_boolean_fields":
            return {
                "success": True,
                "result": {
                    "success": True,
                    "model": "account.analytic.account",
                    "fields": [
                        {
                            "name": "x_studio_pointage",
                            "label": "Pointage",
                            "type": "boolean",
                            "readonly": False,
                        },
                    ],
                },
            }

        if tool_name == "odoo_resolve_analytic_account":
            return {
                "success": True,
                "result": {
                    "success": False,
                    "model": "account.analytic.account",
                    "record_query": "11SOCM0001",
                    "record_id": None,
                    "found": False,
                    "ambiguous": False,
                    "candidates": [],
                    "message": "No analytic account found in Odoo.",
                },
            }

        raise AssertionError(f"Unexpected tool: {tool_name}")

    monkeypatch.setattr("agents.odoo_agent.execute_tool", fake_execute_tool)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent(
        "coche pointage pour le compte analytique 11SOCM0001 sur odoo"
    )

    assert result["status"] == "not_found"
    assert result["approval_required"] is False
    assert "Aucun compte analytique" in result["message"]
    assert get_approvals() == []


def test_approve_toggle_analytic_boolean_executes_tool(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)

    approval = create_approval(
        user_message="Cocher Dotation pour ABDOU LIGHT & SOUNDS",
        intent="odoo",
        selected_agent="odoo_agent",
        selected_model="policy_engine",
        action="toggle_boolean_field",
        risk="medium",
        source_system="odoo",
        entity_name="ABDOU LIGHT & SOUNDS",
        requested_change="true",
        metadata={
            "tool_name": "odoo_update_analytic_boolean_field",
            "model": "account.analytic.account",
            "record_query": "ABDOU LIGHT & SOUNDS",
            "field_label": "Dotation",
            "field_name": "x_dotation",
            "new_value": True,
            "executed": False,
        },
    )

    def fake_execute_tool(tool_name, **kwargs):
        assert tool_name == "odoo_update_analytic_boolean_field"
        assert kwargs == {
            "record_query": "ABDOU LIGHT & SOUNDS",
            "field_name": "x_dotation",
            "new_value": True,
        }

        return {
            "success": True,
            "tool_name": tool_name,
            "result": {
                "success": True,
                "source": "real_odoo",
                "model": "account.analytic.account",
                "action": "toggle_boolean_field",
                "record_query": "ABDOU LIGHT & SOUNDS",
                "record": "ABDOU LIGHT & SOUNDS",
                "record_id": 9,
                "field_name": "x_dotation",
                "requested_value": True,
                "new_value": True,
                "executed": True,
                "verified": True,
                "found": True,
                "message": "Analytic account boolean field updated and verified in Odoo.",
            },
        }

    monkeypatch.setattr("app.execute_tool", fake_execute_tool)
    monkeypatch.setattr("app.log_request", lambda data: None)

    client = TestClient(app)
    response = client.post(
        f"/approvals/{approval['id']}/approve",
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["executed"] is True
    assert data["execution_result"]["verified"] is True
    assert data["execution_result"]["new_value"] is True


def test_approve_toggle_analytic_boolean_passes_resolved_record_id(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)

    approval = create_approval(
        user_message="Cocher Pointage pour 11SOCM0001",
        intent="odoo",
        selected_agent="odoo_agent",
        selected_model="policy_engine",
        action="toggle_boolean_field",
        risk="medium",
        source_system="odoo",
        entity_name="11SOCM0001 Services",
        requested_change="true",
        metadata={
            "tool_name": "odoo_update_analytic_boolean_field",
            "model": "account.analytic.account",
            "record_query": "11SOCM0001",
            "record_id": 5935,
            "field_label": "Pointage",
            "field_name": "x_studio_pointage",
            "new_value": True,
            "executed": False,
        },
    )

    def fake_execute_tool(tool_name, **kwargs):
        assert tool_name == "odoo_update_analytic_boolean_field"
        assert kwargs == {
            "record_query": "11SOCM0001",
            "record_id": 5935,
            "field_name": "x_studio_pointage",
            "new_value": True,
        }

        return {
            "success": True,
            "tool_name": tool_name,
            "result": {
                "success": True,
                "source": "real_odoo",
                "model": "account.analytic.account",
                "action": "toggle_boolean_field",
                "record_query": "11SOCM0001",
                "record_id": 5935,
                "field_name": "x_studio_pointage",
                "requested_value": True,
                "new_value": True,
                "executed": True,
                "verified": True,
                "found": True,
            },
        }

    monkeypatch.setattr("app.execute_tool", fake_execute_tool)
    monkeypatch.setattr("app.log_request", lambda data: None)

    client = TestClient(app)
    response = client.post(
        f"/approvals/{approval['id']}/approve",
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["executed"] is True
    assert data["execution_result"]["record_id"] == 5935
