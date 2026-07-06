from orchestrator.permission_policy import resolve_route_permission


def test_odoo_product_read_wording_variants_map_to_odoo_read():
    variants = [
        {"selected_agent": "odoo_agent", "action": "check_product_stock", "risk_level": "low"},
        {"selected_agent": "odoo_agent", "action": "read_product_stock", "risk_level": "low"},
        {"selected_agent": "odoo_agent", "intent": "product_stock_check", "risk_level": "low"},
    ]

    for classification in variants:
        decision = resolve_route_permission(classification)
        assert decision.permission_category == "odoo_product_read"
        assert decision.required_permissions == frozenset({
            "view_odoo_products",
            "view_limited_odoo_info",
        })
        assert decision.unsupported is False


def test_odoo_document_read_wording_variants_map_to_document_read():
    variants = [
        {"selected_agent": "odoo_agent", "action": "search_document", "risk_level": "low"},
        {"selected_agent": "odoo_agent", "action": "read_document", "risk_level": "low"},
        {"selected_agent": "odoo_agent", "intent": "odoo_document_details", "risk_level": "low"},
    ]

    for classification in variants:
        decision = resolve_route_permission(classification)
        assert decision.permission_category == "odoo_document_read"
        assert decision.required_permissions == frozenset({
            "view_odoo_documents",
            "view_limited_odoo_info",
        })


def test_odoo_write_wording_variants_map_to_write_and_approval():
    variants = [
        {"selected_agent": "odoo_agent", "action": "update_product_price", "risk_level": "high"},
        {"selected_agent": "odoo_agent", "action": "change_price", "risk_level": "high"},
        {"selected_agent": "odoo_agent", "action": "create_purchase_order", "risk_level": "high"},
        {"selected_agent": "odoo_agent", "action": "delete_document", "risk_level": "high"},
        {"selected_agent": "odoo_agent", "action": "set_price", "risk_level": "high"},
    ]

    for classification in variants:
        decision = resolve_route_permission(classification)
        assert decision.permission_category == "odoo_write"
        assert decision.required_permissions == frozenset({"request_odoo_write"})
        assert decision.requires_approval is True


def test_server_routes_require_server_diagnostics_independent_of_action_wording():
    variants = [
        {"selected_agent": "server_agent", "action": "check_ram_usage", "risk_level": "low"},
        {"selected_agent": "server_agent", "action": "server_diagnostic_summary", "risk_level": "low"},
        {"target_system": "server", "action": "status_check", "risk_level": "low"},
    ]

    for classification in variants:
        decision = resolve_route_permission(classification)
        assert decision.permission_category == "server_diagnostics"
        assert decision.required_permissions == frozenset({"server_diagnostics"})


def test_security_blocked_route_requires_no_role_permission():
    decision = resolve_route_permission({
        "selected_agent": "security_agent",
        "action": "block_request",
        "risk_level": "blocked",
    })

    assert decision.blocked is True
    assert decision.permission_category == "security_blocked"
    assert decision.required_permissions == frozenset()


def test_unknown_specialized_action_is_unsupported():
    decision = resolve_route_permission({
        "selected_agent": "odoo_agent",
        "action": "unknown",
        "risk_level": "low",
    })

    assert decision.unsupported is True
    assert decision.permission_category == "unsupported"
    assert decision.required_permissions == frozenset()
