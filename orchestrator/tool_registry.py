SAFE_ODOO_READ_MODELS = {
    "product.product",
    "product.template",
    "res.partner",
    "sale.order",
    "purchase.order",
    "account.move",
    "stock.picking",
}


CAPABILITY_OVERRIDES = {
    "odoo_check_stock": {
        "capability": "odoo.product_stock",
        "permission_category": "odoo_product_read",
        "io_mode": "read",
        "required_parameters": ["product_name"],
    },
    "odoo_search_product": {
        "capability": "odoo.product_search",
        "permission_category": "odoo_product_read",
        "io_mode": "read",
        "required_parameters": ["product_name"],
    },
    "odoo_inventory_summary": {
        "capability": "odoo.inventory_summary",
        "permission_category": "odoo_product_read",
        "io_mode": "read",
        "required_parameters": [],
    },
    "odoo_search_customer": {
        "capability": "odoo.partner_search",
        "permission_category": "odoo_document_read",
        "io_mode": "read",
        "required_parameters": ["customer_name"],
    },
    "odoo_search_records": {
        "capability": "odoo.generic_read_search",
        "permission_category": "odoo_document_read",
        "io_mode": "read",
        "required_parameters": ["model_name", "keyword"],
        "allowed_models": sorted(SAFE_ODOO_READ_MODELS),
    },
    "odoo_get_record_details": {
        "capability": "odoo.generic_read_details",
        "permission_category": "odoo_document_read",
        "io_mode": "read",
        "required_parameters": ["model_name"],
        "allowed_models": sorted(SAFE_ODOO_READ_MODELS),
    },
    "odoo_prepare_update_field": {
        "capability": "odoo.generic_write_prepare",
        "permission_category": "odoo_write",
        "io_mode": "write_prepare",
        "required_parameters": ["model_name", "field_name", "new_value"],
    },
    "odoo_update_field": {
        "capability": "odoo.generic_write_execute",
        "permission_category": "odoo_write",
        "io_mode": "write",
        "required_parameters": ["model_name", "record_id", "field_name", "new_value"],
    },
    "odoo_update_product_price": {
        "capability": "odoo.product_price_update",
        "permission_category": "odoo_write",
        "io_mode": "write",
        "required_parameters": ["product_name", "new_price"],
    },
    "odoo_resolve_product_for_write": {
        "capability": "odoo.product_write_resolve",
        "permission_category": "odoo_write",
        "io_mode": "write_prepare",
        "required_parameters": ["product_name"],
    },
    "odoo_list_analytic_boolean_fields": {
        "capability": "odoo.analytic_boolean_field_list",
        "permission_category": "odoo_write",
        "io_mode": "write_prepare",
        "required_parameters": [],
    },
    "odoo_update_analytic_boolean_field": {
        "capability": "odoo.analytic_boolean_update",
        "permission_category": "odoo_write",
        "io_mode": "write",
        "required_parameters": ["record_query", "field_name", "new_value"],
    },
    "odoo_search_sale_order": {
        "capability": "odoo.document_search",
        "permission_category": "odoo_document_read",
        "io_mode": "read",
        "required_parameters": ["query"],
        "allowed_models": ["sale.order"],
    },
    "odoo_search_purchase_order": {
        "capability": "odoo.document_search",
        "permission_category": "odoo_document_read",
        "io_mode": "read",
        "required_parameters": ["query"],
        "allowed_models": ["purchase.order"],
    },
    "odoo_search_invoice": {
        "capability": "odoo.document_search",
        "permission_category": "odoo_document_read",
        "io_mode": "read",
        "required_parameters": ["query"],
        "allowed_models": ["account.move"],
    },
    "odoo_search_delivery_order": {
        "capability": "odoo.document_search",
        "permission_category": "odoo_document_read",
        "io_mode": "read",
        "required_parameters": ["query"],
        "allowed_models": ["stock.picking"],
    },
    "odoo_get_sale_order_details": {
        "capability": "odoo.document_details",
        "permission_category": "odoo_document_read",
        "io_mode": "read",
        "required_parameters": ["order_query"],
        "allowed_models": ["sale.order"],
    },
    "odoo_get_purchase_order_details": {
        "capability": "odoo.document_details",
        "permission_category": "odoo_document_read",
        "io_mode": "read",
        "required_parameters": ["order_query"],
        "allowed_models": ["purchase.order"],
    },
    "odoo_get_invoice_details": {
        "capability": "odoo.document_details",
        "permission_category": "odoo_document_read",
        "io_mode": "read",
        "required_parameters": ["invoice_query"],
        "allowed_models": ["account.move"],
    },
    "odoo_get_delivery_order_details": {
        "capability": "odoo.document_details",
        "permission_category": "odoo_document_read",
        "io_mode": "read",
        "required_parameters": ["picking_query"],
        "allowed_models": ["stock.picking"],
    },
    "odoo_get_document_details_by_id": {
        "capability": "odoo.document_details_by_id",
        "permission_category": "odoo_document_read",
        "io_mode": "read",
        "required_parameters": ["document_id"],
        "allowed_models": ["sale.order", "purchase.order", "account.move", "stock.picking"],
    },
    "odoo_update_sale_order_line": {
        "capability": "odoo.document_line_update",
        "permission_category": "odoo_write",
        "io_mode": "write",
        "required_parameters": ["order_query", "product_query", "field", "new_value"],
        "allowed_models": ["sale.order"],
    },
    "odoo_update_purchase_order_line": {
        "capability": "odoo.document_line_update",
        "permission_category": "odoo_write",
        "io_mode": "write",
        "required_parameters": ["order_query", "product_query", "field", "new_value"],
        "allowed_models": ["purchase.order"],
    },
    "odoo_update_invoice_line": {
        "capability": "odoo.document_line_update",
        "permission_category": "odoo_write",
        "io_mode": "write",
        "required_parameters": ["invoice_query", "product_query", "field", "new_value"],
        "allowed_models": ["account.move"],
    },
    "odoo_update_delivery_quantity": {
        "capability": "odoo.document_line_update",
        "permission_category": "odoo_write",
        "io_mode": "write",
        "required_parameters": ["picking_query", "product_query", "new_quantity"],
        "allowed_models": ["stock.picking"],
    },
    "odoo_update_document_partner": {
        "capability": "odoo.document_partner_update",
        "permission_category": "odoo_write",
        "io_mode": "write",
        "required_parameters": ["model_name", "partner_query"],
    },
    "odoo_update_document_date": {
        "capability": "odoo.document_date_update",
        "permission_category": "odoo_write",
        "io_mode": "write",
        "required_parameters": ["model_name", "date_field", "new_date"],
    },
    "odoo_test_connection": {
        "capability": "odoo.connection_status",
        "permission_category": "odoo_product_read",
        "io_mode": "read",
        "required_parameters": [],
    },
    "check_ram_usage": {
        "capability": "server.ram_usage",
        "permission_category": "server_diagnostics",
        "io_mode": "read",
        "required_parameters": [],
    },
    "check_cpu_usage": {
        "capability": "server.cpu_usage",
        "permission_category": "server_diagnostics",
        "io_mode": "read",
        "required_parameters": [],
    },
    "check_disk_usage": {
        "capability": "server.disk_usage",
        "permission_category": "server_diagnostics",
        "io_mode": "read",
        "required_parameters": [],
    },
    "check_server_status": {
        "capability": "server.uptime",
        "permission_category": "server_diagnostics",
        "io_mode": "read",
        "required_parameters": [],
    },
    "check_service_status": {
        "capability": "server.local_health",
        "permission_category": "server_diagnostics",
        "io_mode": "read",
        "required_parameters": [],
    },
    "server_diagnostic_summary": {
        "capability": "server.local_health",
        "permission_category": "server_diagnostics",
        "io_mode": "read",
        "required_parameters": [],
    },
}


AGENT_CAPABILITIES = {
    "knowledge.general_answer": {
        "name": "knowledge.general_answer",
        "capability": "knowledge.general_answer",
        "description": "Answer general or project-context questions without backend execution.",
        "domain": "knowledge",
        "system": "knowledge",
        "permission_category": "chat_access",
        "risk_level": "low",
        "requires_approval": False,
        "io_mode": "read",
        "read_write": "read",
        "required_parameters": ["message"],
        "executor": "agents.knowledge_agent.run",
    },
    "support.troubleshooting": {
        "name": "support.troubleshooting",
        "capability": "support.troubleshooting",
        "description": "Return safe helpdesk troubleshooting guidance without executing system actions.",
        "domain": "support",
        "system": "support",
        "permission_category": "support_access",
        "risk_level": "low",
        "requires_approval": False,
        "io_mode": "read",
        "read_write": "read",
        "required_parameters": ["message"],
        "executor": "agents.support_agent.run",
    },
}


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
    "odoo_search_records": {
        "description": "Safely search allowlisted Odoo records by keyword.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_get_record_details": {
        "description": "Safely read business details for one allowlisted Odoo record.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_prepare_update_field": {
        "description": "Resolve one allowlisted Odoo record and field before creating approval.",
        "system": "odoo",
        "risk_level": "low",
        "requires_approval": False,
    },
    "odoo_update_field": {
        "description": "Update an allowlisted Odoo field after approval.",
        "system": "odoo",
        "risk_level": "high",
        "requires_approval": True,
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
    tool = TOOLS.get(tool_name)

    if not tool:
        return None

    metadata = {
        **tool,
        "name": tool_name,
        "domain": tool.get("system", "general"),
        "permission_category": (
            "odoo_write"
            if tool.get("system") == "odoo" and tool.get("requires_approval")
            else "server_diagnostics"
            if tool.get("system") == "server"
            else "odoo_product_read"
            if tool.get("system") == "odoo"
            else "chat_access"
        ),
        "io_mode": "write" if tool.get("requires_approval") else "read",
        "required_parameters": [],
        "executor": tool_name,
    }
    metadata.update(CAPABILITY_OVERRIDES.get(tool_name, {}))
    metadata.setdefault("capability", tool_name)
    metadata["read_write"] = "write" if metadata["io_mode"].startswith("write") else "read"

    return metadata


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


def list_capabilities() -> list[dict]:
    tool_capabilities = [
        get_tool_metadata(tool_name)
        for tool_name in sorted(TOOLS)
        if get_tool_metadata(tool_name) is not None
    ]
    return sorted(
        tool_capabilities + list(AGENT_CAPABILITIES.values()),
        key=lambda capability: capability["name"],
    )
