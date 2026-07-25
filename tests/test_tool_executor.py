from orchestrator.tool_executor import execute_tool


def test_execute_odoo_check_stock_tool():
    result = execute_tool(
        "odoo_check_stock",
        product_name="Laptop"
    )

    assert result["success"] is True
    assert result["tool_name"] == "odoo_check_stock"
    assert result["metadata"]["system"] == "odoo"
    assert "result" in result


def test_execute_odoo_search_product_tool():
    result = execute_tool(
        "odoo_search_product",
        product_name="Laptop"
    )

    assert result["success"] is True
    assert result["tool_name"] == "odoo_search_product"


def test_execute_odoo_update_product_price_tool(monkeypatch):
    def fake_update_product_price(product_name, new_price):
        return {
            "success": True,
            "source": "real_odoo",
            "action": "change_price",
            "product": product_name,
            "requested_price": new_price,
            "new_price": new_price,
            "executed": True,
            "verified": True,
            "found": True,
        }

    monkeypatch.setattr(
        "orchestrator.tool_executor.odoo.update_product_price",
        fake_update_product_price,
    )

    result = execute_tool(
        "odoo_update_product_price",
        product_name="BACO CLEAN",
        new_price=25.0,
    )

    assert result["success"] is True
    assert result["tool_name"] == "odoo_update_product_price"
    assert result["metadata"]["requires_approval"] is True
    assert result["result"]["executed"] is True
    assert result["result"]["verified"] is True


def test_execute_odoo_list_analytic_boolean_fields(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.tool_executor.odoo.get_analytic_boolean_fields",
        lambda: {
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
    )

    result = execute_tool("odoo_list_analytic_boolean_fields")

    assert result["success"] is True
    assert result["tool_name"] == "odoo_list_analytic_boolean_fields"
    assert result["metadata"]["requires_approval"] is False
    assert result["result"]["fields"][0]["name"] == "x_dotation"


def test_execute_odoo_resolve_analytic_account(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.tool_executor.odoo.resolve_analytic_account",
        lambda record_query: {
            "success": True,
            "model": "account.analytic.account",
            "record_query": record_query,
            "record_id": 5935,
            "found": True,
            "ambiguous": False,
        },
    )

    result = execute_tool(
        "odoo_resolve_analytic_account",
        record_query="11SOCM0001",
    )

    assert result["success"] is True
    assert result["tool_name"] == "odoo_resolve_analytic_account"
    assert result["metadata"]["requires_approval"] is False
    assert result["result"]["record_id"] == 5935


def test_execute_odoo_list_customer_invoices(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.tool_executor.odoo.list_customer_invoices",
        lambda filters=None, limit=10: {
            "success": True,
            "model": "account.move",
            "found": True,
            "records": [{"reference": "INV/2026/005"}],
            "domain_used": filters or [],
        },
    )

    result = execute_tool(
        "odoo_list_customer_invoices",
        filters=[{"field": "move_type", "operator": "=", "value": "out_invoice"}],
    )

    assert result["success"] is True
    assert result["tool_name"] == "odoo_list_customer_invoices"
    assert result["metadata"]["capability"] == "odoo.customer_invoice_list"
    assert result["metadata"]["requires_approval"] is False
    assert result["result"]["records"][0]["reference"] == "INV/2026/005"


def test_execute_odoo_count_records_uses_dynamic_read(monkeypatch):
    captured = {}

    def fake_dynamic_read(read_plan):
        captured["read_plan"] = read_plan
        return {"success": True, "model": "account.move", "record_count": 4}

    monkeypatch.setattr("orchestrator.tool_executor.odoo.dynamic_read", fake_dynamic_read)

    result = execute_tool(
        "odoo_count_records",
        read_plan={
            "operation": "list",
            "business_object": "customer_invoices",
            "model_hint": "account.move",
        },
    )

    assert result["success"] is True
    assert result["tool_name"] == "odoo_count_records"
    assert result["metadata"]["capability"] == "odoo.generic_read_count"
    assert captured["read_plan"]["operation"] == "count"
    assert captured["read_plan"]["model_hint"] == "account.move"


def test_execute_odoo_search_analytic_account(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.tool_executor.odoo.search_analytic_accounts",
        lambda record_query, limit=6: {
            "success": True,
            "model": "account.analytic.account",
            "record_query": record_query,
            "found": True,
            "records": [{"id": 5935, "reference": "11SOCM0001"}],
        },
    )

    result = execute_tool(
        "odoo_search_analytic_account",
        record_query="11SOCM0001",
    )

    assert result["success"] is True
    assert result["tool_name"] == "odoo_search_analytic_account"
    assert result["metadata"]["capability"] == "odoo.analytic_account_search"
    assert result["metadata"]["requires_approval"] is False
    assert result["result"]["records"][0]["reference"] == "11SOCM0001"


def test_execute_odoo_get_analytic_account_details(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.tool_executor.odoo.get_analytic_account_details",
        lambda record_query="", record_id=None: {
            "success": True,
            "model": "account.analytic.account",
            "record_query": record_query,
            "found": True,
            "record": {"id": record_id or 5935, "reference": "11SOCM0001"},
        },
    )

    result = execute_tool(
        "odoo_get_analytic_account_details",
        record_query="11SOCM0001",
    )

    assert result["success"] is True
    assert result["tool_name"] == "odoo_get_analytic_account_details"
    assert result["metadata"]["capability"] == "odoo.analytic_account_details"
    assert result["metadata"]["requires_approval"] is False
    assert result["result"]["record"]["reference"] == "11SOCM0001"


def test_execute_odoo_update_analytic_boolean_field(monkeypatch):
    def fake_update(record_query, field_name, new_value, record_id=None):
        return {
            "success": True,
            "model": "account.analytic.account",
            "action": "toggle_boolean_field",
            "record_query": record_query,
            "record_id": record_id,
            "field_name": field_name,
            "requested_value": new_value,
            "new_value": new_value,
            "executed": True,
            "verified": True,
        }

    monkeypatch.setattr(
        "orchestrator.tool_executor.odoo.update_analytic_boolean_field",
        fake_update,
    )

    result = execute_tool(
        "odoo_update_analytic_boolean_field",
        record_query="ABDOU LIGHT & SOUNDS",
        record_id=9,
        field_name="x_dotation",
        new_value=True,
    )

    assert result["success"] is True
    assert result["tool_name"] == "odoo_update_analytic_boolean_field"
    assert result["metadata"]["requires_approval"] is True
    assert result["result"]["record_id"] == 9
    assert result["result"]["verified"] is True


def test_execute_odoo_update_sale_order_line(monkeypatch):
    def fake_update(order_query, product_query, field, new_value):
        return {
            "success": True,
            "model": "sale.order",
            "document": order_query,
            "product": product_query,
            "field": field,
            "requested_value": new_value,
            "new_value": new_value,
            "executed": True,
            "verified": True,
        }

    monkeypatch.setattr(
        "orchestrator.tool_executor.odoo.update_sale_order_line",
        fake_update,
    )

    result = execute_tool(
        "odoo_update_sale_order_line",
        order_query="S00045",
        product_query="BACO CLEAN",
        field="price_unit",
        new_value=7,
    )

    assert result["success"] is True
    assert result["tool_name"] == "odoo_update_sale_order_line"
    assert result["metadata"]["requires_approval"] is True
    assert result["result"]["verified"] is True


def test_execute_odoo_update_document_partner(monkeypatch):
    def fake_update(model_name, document_query, partner_query):
        return {
            "success": True,
            "model": model_name,
            "document": document_query,
            "field": "partner_id",
            "new_value": partner_query,
            "executed": True,
            "verified": True,
        }

    monkeypatch.setattr(
        "orchestrator.tool_executor.odoo.update_document_partner",
        fake_update,
    )

    result = execute_tool(
        "odoo_update_document_partner",
        model_name="sale.order",
        document_query="S00045",
        partner_query="ABDOU LIGHT & SOUNDS",
    )

    assert result["success"] is True
    assert result["tool_name"] == "odoo_update_document_partner"
    assert result["result"]["new_value"] == "ABDOU LIGHT & SOUNDS"


def test_execute_unknown_tool_fails_cleanly():
    result = execute_tool("unknown_tool")

    assert result["success"] is False
    assert result["tool_name"] == "unknown_tool"
    assert "Unknown tool" in result["error"]
