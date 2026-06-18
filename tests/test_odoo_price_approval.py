from fastapi.testclient import TestClient

from agents.odoo_agent import run as run_odoo_agent
from app import app
from orchestrator.approval_store import create_approval, get_approvals


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
    response = client.post(f"/approvals/{approval['id']}/approve")

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
    response = client.post(f"/approvals/{approval['id']}/approve")

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
    response = client.post(f"/approvals/{approval['id']}/approve")

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
    response = client.post(f"/approvals/{approval['id']}/approve")

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
    response = client.post(f"/approvals/{approval['id']}/approve")

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
    response = client.post(f"/approvals/{approval['id']}/approve")

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
    response = client.post(f"/approvals/{approval['id']}/reject")

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
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "odoo_agent"
    assert data["parser_source"] == "openai"
    assert data["parsed_action"] == "search_document"
    assert data["document_reference"] == "FNP/2026/04016"


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
        assert tool_name == "odoo_list_analytic_boolean_fields"
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

    monkeypatch.setattr("agents.odoo_agent.execute_tool", fake_execute_tool)
    monkeypatch.setattr("agents.odoo_agent.log_request", lambda data: None)

    result = run_odoo_agent("Cocher Dotation pour ABDOU LIGHT & SOUNDS")
    approval = get_approvals()[0]

    assert result["status"] == "pending_approval"
    assert approval["action"] == "toggle_boolean_field"
    assert approval["metadata"]["tool_name"] == "odoo_update_analytic_boolean_field"
    assert approval["metadata"]["model"] == "account.analytic.account"
    assert approval["metadata"]["record_query"] == "ABDOU LIGHT & SOUNDS"
    assert approval["metadata"]["field_label"] == "Dotation"
    assert approval["metadata"]["field_name"] == "x_dotation"
    assert approval["metadata"]["new_value"] is True


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
    response = client.post(f"/approvals/{approval['id']}/approve")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["executed"] is True
    assert data["execution_result"]["verified"] is True
    assert data["execution_result"]["new_value"] is True
