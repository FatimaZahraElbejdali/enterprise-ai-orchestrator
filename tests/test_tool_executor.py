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


def test_execute_odoo_update_analytic_boolean_field(monkeypatch):
    def fake_update(record_query, field_name, new_value):
        return {
            "success": True,
            "model": "account.analytic.account",
            "action": "toggle_boolean_field",
            "record_query": record_query,
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
        field_name="x_dotation",
        new_value=True,
    )

    assert result["success"] is True
    assert result["tool_name"] == "odoo_update_analytic_boolean_field"
    assert result["metadata"]["requires_approval"] is True
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
