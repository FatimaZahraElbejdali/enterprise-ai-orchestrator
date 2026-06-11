TOOLS = {
    "odoo_check_stock": {
        "description": "Check product stock quantity in Odoo.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_search_product": {
        "description": "Search for a product in Odoo.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_search_customer": {
        "description": "Search for a customer in Odoo.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_create_purchase_request": {
        "description": "Create a purchase request in Odoo.",
        "system": "odoo",
        "risk_level": "medium",
        "requires_approval": True,
    },
    "odoo_create_purchase_order": {
        "description": "Create a purchase order in Odoo.",
        "system": "odoo",
        "risk_level": "high",
        "requires_approval": True,
    },
    "odoo_test_connection": {
        "description": "Test Odoo connection status.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
}


def get_tool_metadata(tool_name: str):
    return TOOLS.get(tool_name)


def tool_requires_approval(tool_name: str) -> bool:
    tool = get_tool_metadata(tool_name)

    if not tool:
        return True

    return tool["requires_approval"]


def get_tool_risk_level(tool_name: str) -> str:
    tool = get_tool_metadata(tool_name)

    if not tool:
        return "high"

    return tool["risk_level"]