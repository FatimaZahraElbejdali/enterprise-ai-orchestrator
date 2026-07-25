from orchestrator.tool_registry import (
    SAFE_ODOO_READ_MODELS,
    get_tool_metadata,
    list_capabilities,
    tool_requires_approval,
    get_tool_risk_level,
)


def test_known_tool_metadata_exists():
    tool = get_tool_metadata("odoo_check_stock")

    assert tool is not None
    assert tool["system"] == "odoo"
    assert tool["risk_level"] == "low"


def test_low_risk_tool_does_not_require_approval():
    assert tool_requires_approval("odoo_check_stock") is False


def test_medium_risk_tool_requires_approval():
    assert tool_requires_approval("odoo_create_purchase_request") is True


def test_price_update_tool_requires_approval():
    tool = get_tool_metadata("odoo_update_product_price")

    assert tool is not None
    assert tool["system"] == "odoo"
    assert tool["risk_level"] == "medium"
    assert tool_requires_approval("odoo_update_product_price") is True


def test_analytic_boolean_update_tool_requires_approval():
    tool = get_tool_metadata("odoo_update_analytic_boolean_field")

    assert tool is not None
    assert tool["system"] == "odoo"
    assert tool["risk_level"] == "medium"
    assert tool_requires_approval("odoo_update_analytic_boolean_field") is True


def test_analytic_boolean_field_list_is_low_risk():
    tool = get_tool_metadata("odoo_list_analytic_boolean_fields")

    assert tool is not None
    assert tool["system"] == "odoo"
    assert tool["risk_level"] == "low"
    assert tool_requires_approval("odoo_list_analytic_boolean_fields") is False


def test_high_risk_tool_requires_approval():
    assert tool_requires_approval("odoo_create_purchase_order") is True


def test_document_read_tools_are_low_risk():
    for tool_name in [
        "odoo_search_sale_order",
        "odoo_search_purchase_order",
        "odoo_search_invoice",
        "odoo_search_delivery_order",
        "odoo_get_sale_order_details",
        "odoo_get_purchase_order_details",
        "odoo_get_invoice_details",
        "odoo_get_delivery_order_details",
    ]:
        tool = get_tool_metadata(tool_name)

        assert tool is not None
        assert tool["system"] == "odoo"
        assert tool["risk_level"] == "low"
        assert tool_requires_approval(tool_name) is False


def test_document_write_tools_are_high_risk_and_require_approval():
    for tool_name in [
        "odoo_update_sale_order_line",
        "odoo_update_purchase_order_line",
        "odoo_update_invoice_line",
        "odoo_update_delivery_quantity",
        "odoo_update_document_partner",
        "odoo_update_document_date",
    ]:
        tool = get_tool_metadata(tool_name)

        assert tool is not None
        assert tool["system"] == "odoo"
        assert tool["risk_level"] == "high"
        assert tool_requires_approval(tool_name) is True


def test_unknown_tool_defaults_to_high_risk():
    assert get_tool_risk_level("unknown_tool") == "high"
    assert tool_requires_approval("unknown_tool") is True


def test_tool_metadata_includes_structured_capability_fields():
    tool = get_tool_metadata("odoo_search_records")

    assert tool["capability"] == "odoo.generic_read_search"
    assert tool["domain"] == "odoo"
    assert tool["permission_category"] == "odoo_document_read"
    assert tool["io_mode"] == "read"
    assert tool["read_write"] == "read"
    assert tool["required_parameters"] == ["model_name", "keyword"]
    assert tool["executor"] == "odoo_search_records"
    assert tool["allowed_models"] == sorted(SAFE_ODOO_READ_MODELS)

    count_tool = get_tool_metadata("odoo_count_records")
    group_tool = get_tool_metadata("odoo_group_by")

    assert count_tool["capability"] == "odoo.generic_read_count"
    assert count_tool["permission_category"] == "odoo_read"
    assert count_tool["io_mode"] == "read"
    assert group_tool["capability"] == "odoo.generic_read_group_by"
    assert group_tool["permission_category"] == "odoo_read"
    assert group_tool["io_mode"] == "read"


def test_agent_capabilities_are_registered_without_fake_tools():
    capabilities = {item["capability"]: item for item in list_capabilities()}

    assert capabilities["knowledge.general_answer"]["executor"] == "agents.knowledge_agent.run"
    assert capabilities["support.troubleshooting"]["executor"] == "agents.support_agent.run"
