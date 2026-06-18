from integrations.odoo_connector import OdooConnector
from orchestrator.tool_registry import get_tool_metadata

odoo = OdooConnector()


def _without_none(values: dict):
    return {
        key: value
        for key, value in values.items()
        if value is not None
    }


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

    elif tool_name == "odoo_update_product_price":
        result = odoo.update_product_price(
            product_name=kwargs.get("product_name", ""),
            new_price=kwargs.get("new_price"),
        )

    elif tool_name == "odoo_list_analytic_boolean_fields":
        result = odoo.get_analytic_boolean_fields()

    elif tool_name == "odoo_update_analytic_boolean_field":
        result = odoo.update_analytic_boolean_field(
            record_query=kwargs.get("record_query", ""),
            field_name=kwargs.get("field_name", ""),
            new_value=kwargs.get("new_value") is True,
        )

    elif tool_name == "odoo_search_sale_order":
        result = odoo.search_sale_order(kwargs.get("query", ""))

    elif tool_name == "odoo_search_purchase_order":
        result = odoo.search_purchase_order(kwargs.get("query", ""))

    elif tool_name == "odoo_search_invoice":
        result = odoo.search_invoice(kwargs.get("query", ""))

    elif tool_name == "odoo_search_delivery_order":
        result = odoo.search_delivery_order(kwargs.get("query", ""))

    elif tool_name == "odoo_get_sale_order_details":
        result = odoo.get_sale_order_details(kwargs.get("order_query", ""))

    elif tool_name == "odoo_get_purchase_order_details":
        result = odoo.get_purchase_order_details(kwargs.get("order_query", ""))

    elif tool_name == "odoo_get_invoice_details":
        result = odoo.get_invoice_details(kwargs.get("invoice_query", ""))

    elif tool_name == "odoo_get_delivery_order_details":
        result = odoo.get_delivery_order_details(kwargs.get("picking_query", ""))

    elif tool_name == "odoo_update_sale_order_line":
        result = odoo.update_sale_order_line(**_without_none({
            "order_query": kwargs.get("order_query", ""),
            "product_query": kwargs.get("product_query", ""),
            "field": kwargs.get("field", ""),
            "new_value": kwargs.get("new_value"),
            "document_id": kwargs.get("document_id"),
            "partner_name": kwargs.get("partner_name"),
        }))

    elif tool_name == "odoo_update_purchase_order_line":
        result = odoo.update_purchase_order_line(**_without_none({
            "order_query": kwargs.get("order_query", ""),
            "product_query": kwargs.get("product_query", ""),
            "field": kwargs.get("field", ""),
            "new_value": kwargs.get("new_value"),
            "document_id": kwargs.get("document_id"),
            "partner_name": kwargs.get("partner_name"),
        }))

    elif tool_name == "odoo_update_invoice_line":
        result = odoo.update_invoice_line(**_without_none({
            "invoice_query": kwargs.get("invoice_query", ""),
            "product_query": kwargs.get("product_query", ""),
            "field": kwargs.get("field", ""),
            "new_value": kwargs.get("new_value"),
            "document_id": kwargs.get("document_id"),
            "partner_name": kwargs.get("partner_name"),
        }))

    elif tool_name == "odoo_update_delivery_quantity":
        result = odoo.update_delivery_quantity(**_without_none({
            "picking_query": kwargs.get("picking_query", ""),
            "product_query": kwargs.get("product_query", ""),
            "new_quantity": kwargs.get("new_quantity"),
            "document_id": kwargs.get("document_id"),
            "partner_name": kwargs.get("partner_name"),
        }))

    elif tool_name == "odoo_update_document_partner":
        result = odoo.update_document_partner(**_without_none({
            "model_name": kwargs.get("model_name", ""),
            "document_query": kwargs.get("document_query", ""),
            "partner_query": kwargs.get("partner_query", ""),
            "document_id": kwargs.get("document_id"),
            "current_partner_name": kwargs.get("current_partner_name"),
        }))

    elif tool_name == "odoo_update_document_date":
        result = odoo.update_document_date(**_without_none({
            "model_name": kwargs.get("model_name", ""),
            "document_query": kwargs.get("document_query", ""),
            "date_field": kwargs.get("date_field", ""),
            "new_date": kwargs.get("new_date", ""),
            "document_id": kwargs.get("document_id"),
            "partner_name": kwargs.get("partner_name"),
        }))

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
