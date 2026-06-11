from orchestrator.tool_registry import (
    get_tool_metadata,
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


def test_high_risk_tool_requires_approval():
    assert tool_requires_approval("odoo_create_purchase_order") is True


def test_unknown_tool_defaults_to_high_risk():
    assert get_tool_risk_level("unknown_tool") == "high"
    assert tool_requires_approval("unknown_tool") is True