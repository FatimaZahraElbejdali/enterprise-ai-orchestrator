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
    "odoo_inventory_summary": {
        "description": "Read broad inventory product counts and stock totals from Odoo.",
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
    "odoo_update_product_price": {
        "description": "Update product sale price in Odoo.",
        "system": "odoo",
        "risk_level": "medium",
        "requires_approval": True,
    },
    "odoo_resolve_product_for_write": {
        "description": "Resolve one product.template before an approved write.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_list_analytic_boolean_fields": {
        "description": "List boolean fields on Odoo analytic accounts.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_update_analytic_boolean_field": {
        "description": "Update a boolean field on an Odoo analytic account.",
        "system": "odoo",
        "risk_level": "medium",
        "requires_approval": True,
    },
    "odoo_search_sale_order": {
        "description": "Search for a sale order or quotation in Odoo.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_search_purchase_order": {
        "description": "Search for a purchase order in Odoo.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_search_invoice": {
        "description": "Search for an invoice in Odoo.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_search_delivery_order": {
        "description": "Search for a delivery order in Odoo.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_get_sale_order_details": {
        "description": "Read sale order details and lines from Odoo.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_get_purchase_order_details": {
        "description": "Read purchase order details and lines from Odoo.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_get_invoice_details": {
        "description": "Read invoice details and lines from Odoo.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_get_delivery_order_details": {
        "description": "Read delivery order details and lines from Odoo.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_get_document_details_by_id": {
        "description": "Read Odoo business document details and lines by exact numeric ID.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_update_sale_order_line": {
        "description": "Update a sale order line after approval.",
        "system": "odoo",
        "risk_level": "high",
        "requires_approval": True,
    },
    "odoo_update_purchase_order_line": {
        "description": "Update a purchase order line after approval.",
        "system": "odoo",
        "risk_level": "high",
        "requires_approval": True,
    },
    "odoo_update_invoice_line": {
        "description": "Update an invoice line after approval.",
        "system": "odoo",
        "risk_level": "high",
        "requires_approval": True,
    },
    "odoo_update_delivery_quantity": {
        "description": "Update a delivery order quantity after approval.",
        "system": "odoo",
        "risk_level": "high",
        "requires_approval": True,
    },
    "odoo_update_document_partner": {
        "description": "Update a document partner after approval.",
        "system": "odoo",
        "risk_level": "high",
        "requires_approval": True,
    },
    "odoo_update_document_date": {
        "description": "Update a document date after approval.",
        "system": "odoo",
        "risk_level": "high",
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
    "check_ram_usage": {
        "description": "Read safe demo RAM usage for the orchestrator server.",
        "system": "server",
        "risk_level": "low",
        "requires_approval": False,
    },
    "check_cpu_usage": {
        "description": "Read safe demo CPU usage for the orchestrator server.",
        "system": "server",
        "risk_level": "low",
        "requires_approval": False,
    },
    "check_disk_usage": {
        "description": "Read safe demo disk usage for the orchestrator server.",
        "system": "server",
        "risk_level": "low",
        "requires_approval": False,
    },
    "check_server_status": {
        "description": "Read safe demo status and uptime for the orchestrator server.",
        "system": "server",
        "risk_level": "low",
        "requires_approval": False,
    },
    "check_service_status": {
        "description": "Read safe demo backend/frontend service status.",
        "system": "server",
        "risk_level": "low",
        "requires_approval": False,
    },
    "server_diagnostic_summary": {
        "description": "Read safe demo CPU, RAM, disk, uptime, and service summary.",
        "system": "server",
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
