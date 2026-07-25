from integrations.odoo_connector import OdooConnector
from integrations.internal_server_connector import InternalServerConnector
from orchestrator.tool_registry import get_tool_metadata

odoo = OdooConnector()
internal_server = InternalServerConnector()


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

    elif tool_name == "odoo_inventory_summary":
        result = odoo.inventory_summary()

    elif tool_name == "odoo_search_customer":
        result = odoo.search_customer(kwargs.get("customer_name", ""))

    elif tool_name == "odoo_search_records":
        result = odoo.generic_search_records(
            model_name=kwargs.get("model_name", ""),
            keyword=kwargs.get("keyword", ""),
            limit=kwargs.get("limit", 6),
        )

    elif tool_name == "odoo_generic_read":
        result = odoo.dynamic_read(
            read_plan=kwargs.get("read_plan") or {},
        )

    elif tool_name == "odoo_count_records":
        read_plan = dict(kwargs.get("read_plan") or {})
        if read_plan:
            read_plan["operation"] = "count"
            result = odoo.dynamic_read(read_plan=read_plan)
        else:
            result = odoo.agent_count_records(
                model_name=kwargs.get("model_name", ""),
                domain=kwargs.get("domain") or [],
            )

    elif tool_name == "odoo_group_by":
        result = odoo.agent_aggregate_records(
            model_name=kwargs.get("model_name", ""),
            domain=kwargs.get("domain") or [],
            group_by=kwargs.get("group_by") or [],
            aggregates=kwargs.get("aggregates") or [{"field": "id", "operator": "count", "alias": "record_count"}],
            order_by=kwargs.get("order_by") or [{"field": "record_count", "direction": "desc"}],
            limit=kwargs.get("limit", 10),
        )

    elif tool_name == "odoo_get_record_details":
        result = odoo.generic_get_record_details(
            model_name=kwargs.get("model_name", ""),
            record_id=kwargs.get("record_id"),
            keyword=kwargs.get("keyword", ""),
        )

    elif tool_name == "odoo_list_customer_invoices":
        result = odoo.list_customer_invoices(
            filters=kwargs.get("filters") or [],
            limit=kwargs.get("limit", 10),
        )

    elif tool_name == "odoo_search_analytic_account":
        result = odoo.search_analytic_accounts(
            record_query=kwargs.get("record_query", "") or kwargs.get("keyword", ""),
            limit=kwargs.get("limit", 6),
        )

    elif tool_name == "odoo_get_analytic_account_details":
        result = odoo.get_analytic_account_details(
            record_query=kwargs.get("record_query", "") or kwargs.get("keyword", ""),
            record_id=kwargs.get("record_id"),
        )

    elif tool_name == "odoo_search_bank_accounting":
        result = odoo.search_bank_accounting_records(
            keyword=kwargs.get("keyword", ""),
            message=kwargs.get("message", ""),
            limit=kwargs.get("limit", 10),
            candidate_models=kwargs.get("candidate_models"),
        )

    elif tool_name == "odoo_rank_purchase_order_suppliers":
        result = odoo.rank_purchase_order_suppliers(
            limit=kwargs.get("limit", 10),
        )

    elif tool_name == "odoo_rank_sale_order_customers":
        result = odoo.rank_sale_order_customers(
            limit=kwargs.get("limit", 10),
        )

    elif tool_name == "odoo_prepare_update_field":
        result = odoo.prepare_generic_update_field(
            model_name=kwargs.get("model_name", ""),
            field_name=kwargs.get("field_name", ""),
            new_value=kwargs.get("new_value"),
            record_id=kwargs.get("record_id"),
            keyword=kwargs.get("keyword", ""),
        )

    elif tool_name == "odoo_update_field":
        result = odoo.update_generic_field(
            model_name=kwargs.get("model_name", ""),
            record_id=kwargs.get("record_id"),
            field_name=kwargs.get("field_name", ""),
            new_value=kwargs.get("new_value"),
        )

    elif tool_name == "odoo_create_purchase_request":
        result = odoo.create_purchase_request(kwargs.get("description", ""))

    elif tool_name == "odoo_update_product_price":
        result = odoo.update_product_price(
            product_name=kwargs.get("product_name", ""),
            new_price=kwargs.get("new_price"),
        )

    elif tool_name == "odoo_resolve_product_for_write":
        result = odoo.resolve_product_template_for_write(
            kwargs.get("product_name", ""),
        )

    elif tool_name == "odoo_list_analytic_boolean_fields":
        result = odoo.get_analytic_boolean_fields()

    elif tool_name == "odoo_resolve_analytic_account":
        result = odoo.resolve_analytic_account(
            kwargs.get("record_query", ""),
        )

    elif tool_name == "odoo_update_analytic_boolean_field":
        tool_kwargs = {
            "record_query": kwargs.get("record_query", ""),
            "field_name": kwargs.get("field_name", ""),
            "new_value": kwargs.get("new_value") is True,
        }

        if kwargs.get("record_id") is not None:
            tool_kwargs["record_id"] = kwargs.get("record_id")

        result = odoo.update_analytic_boolean_field(**tool_kwargs)

    elif tool_name == "odoo_search_sale_order":
        result = odoo.search_sale_order(kwargs.get("query", ""))

    elif tool_name == "odoo_search_purchase_order":
        result = odoo.search_purchase_order(kwargs.get("query", ""))

    elif tool_name == "odoo_search_invoice":
        result = odoo.search_invoice(kwargs.get("query", ""))

    elif tool_name == "odoo_search_delivery_order":
        result = odoo.search_delivery_order(kwargs.get("query", ""))

    elif tool_name == "odoo_get_sale_order_details":
        result = odoo.get_sale_order_details(
            kwargs.get("order_query", ""),
            document_id=kwargs.get("document_id"),
        )

    elif tool_name == "odoo_get_purchase_order_details":
        result = odoo.get_purchase_order_details(
            kwargs.get("order_query", ""),
            document_id=kwargs.get("document_id"),
        )

    elif tool_name == "odoo_get_invoice_details":
        result = odoo.get_invoice_details(
            kwargs.get("invoice_query", ""),
            document_id=kwargs.get("document_id"),
        )

    elif tool_name == "odoo_get_delivery_order_details":
        result = odoo.get_delivery_order_details(
            kwargs.get("picking_query", ""),
            document_id=kwargs.get("document_id"),
        )

    elif tool_name == "odoo_get_document_details_by_id":
        result = odoo.get_document_details_by_id(kwargs.get("document_id"))

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

    elif tool_name == "check_ram_usage":
        result = internal_server.check_ram_usage()

    elif tool_name == "check_cpu_usage":
        result = internal_server.check_cpu_usage()

    elif tool_name == "check_disk_usage":
        result = internal_server.check_disk_usage()

    elif tool_name == "check_server_status":
        result = internal_server.check_server_status()

    elif tool_name == "check_service_status":
        result = internal_server.check_service_status()

    elif tool_name == "server_diagnostic_summary":
        result = internal_server.server_diagnostic_summary()

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
