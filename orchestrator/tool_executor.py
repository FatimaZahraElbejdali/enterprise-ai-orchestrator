from integrations.odoo_connector import OdooConnector
from orchestrator.tool_registry import get_tool_metadata

odoo = OdooConnector()


def execute_tool(tool_name: str, **kwargs):
    tool = get_tool_metadata(tool_name)

    if not tool:
        return {
            "success": False,
            "tool_name": tool_name,
            "error": f"Unknown tool: {tool_name}",
        }

    if tool_name == "odoo_check_stock":
        result = odoo.check_stock(kwargs.get("product_name", ""))

    elif tool_name == "odoo_search_product":
        result = odoo.search_product(kwargs.get("product_name", ""))

    elif tool_name == "odoo_search_customer":
        result = odoo.search_customer(kwargs.get("customer_name", ""))

    elif tool_name == "odoo_create_purchase_request":
        result = odoo.create_purchase_request(kwargs.get("description", ""))

    elif tool_name == "odoo_create_purchase_order":
        result = odoo.create_purchase_order(kwargs.get("description", ""))

    elif tool_name == "odoo_test_connection":
        result = odoo.test_connection()

    else:
        return {
            "success": False,
            "tool_name": tool_name,
            "error": f"No executor implemented for tool: {tool_name}",
        }

    return {
        "success": True,
        "tool_name": tool_name,
        "metadata": tool,
        "result": result,
    }