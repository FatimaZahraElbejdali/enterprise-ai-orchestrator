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


def test_change_price_request_creates_approval_without_execution(monkeypatch, tmp_path):
    approvals_file = tmp_path / "approvals.json"
    monkeypatch.setattr("orchestrator.approval_store.APPROVALS_FILE", approvals_file)
    monkeypatch.setattr(
        "agents.odoo_agent.parse_odoo_action_with_openai",
        lambda message: parsed_price_action(),
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Odoo write should not execute from chat")

    monkeypatch.setattr("agents.odoo_agent.execute_tool", fail_if_called)
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
