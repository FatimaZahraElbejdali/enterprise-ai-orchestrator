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


def test_execute_unknown_tool_fails_cleanly():
    result = execute_tool("unknown_tool")

    assert result["success"] is False
    assert result["tool_name"] == "unknown_tool"
    assert "Unknown tool" in result["error"]