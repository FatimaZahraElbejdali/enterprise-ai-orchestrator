from agents import odoo_agent


def test_openai_parser_normalizes_price_action(monkeypatch):
    monkeypatch.setattr(
        "agents.odoo_agent.generate_structured_response",
        lambda **kwargs: {
            "success": True,
            "parsed": {
                "intent": "odoo",
                "action": "change_price",
                "risk": "low",
                "requires_approval": False,
                "target_model": "product.template",
                "record_query": "BACOTOP",
                "field_label": "Prix",
                "field_name": "ignored",
                "new_value": 3,
                "confidence": 0.9,
            },
            "error": None,
        },
    )

    result = odoo_agent.parse_odoo_action_with_openai(
        "Change price for BACOTOP to 3 DH"
    )

    assert result["action"] == "change_price"
    assert result["target_model"] == "product.template"
    assert result["record_query"] == "BACOTOP"
    assert result["field_name"] == "list_price"
    assert result["new_value"] == 3.0
    assert result["requires_approval"] is True
    assert result["risk"] == "medium"
    assert result["parser_source"] == "openai"


def test_openai_parser_falls_back_to_deterministic_toggle(monkeypatch):
    monkeypatch.setattr(
        "agents.odoo_agent.generate_structured_response",
        lambda **kwargs: {
            "success": False,
            "parsed": None,
            "error": "invalid_json",
        },
    )

    result = odoo_agent.parse_odoo_action_with_openai(
        "Décocher Pointage pour 21ABLS0008"
    )

    assert result["action"] == "toggle_boolean_field"
    assert result["target_model"] == "account.analytic.account"
    assert result["record_query"] == "21ABLS0008"
    assert result["field_label"] == "Pointage"
    assert result["new_value"] is False
    assert result["requires_approval"] is True
    assert result["parser_source"] == "local_rules"


def test_openai_parser_normalizes_invoice_line_update(monkeypatch):
    monkeypatch.setattr(
        "agents.odoo_agent.generate_structured_response",
        lambda **kwargs: {
            "success": True,
            "parsed": {
                "intent": "odoo",
                "action": "update_document_line",
                "risk": "low",
                "requires_approval": False,
                "target_model": "account.move",
                "record_query": None,
                "document_query": "INV/2026/001",
                "product_query": "BACO CLEAN",
                "field_label": "Prix",
                "field_name": "price_unit",
                "new_value": 7,
                "confidence": 0.91,
            },
            "error": None,
        },
    )

    result = odoo_agent.parse_odoo_action_with_openai(
        "Change the price of product BACO CLEAN in invoice INV/2026/001 to 7 DH"
    )

    assert result["action"] == "update_document_line"
    assert result["target_model"] == "account.move"
    assert result["document_query"] == "INV/2026/001"
    assert result["product_query"] == "BACO CLEAN"
    assert result["field_name"] == "price_unit"
    assert result["new_value"] == 7.0
    assert result["requires_approval"] is True
    assert result["risk"] == "high"


def test_openai_parser_maps_purchase_quantity_field(monkeypatch):
    monkeypatch.setattr(
        "agents.odoo_agent.generate_structured_response",
        lambda **kwargs: {
            "success": True,
            "parsed": {
                "intent": "odoo",
                "action": "update_document_line",
                "risk": "medium",
                "requires_approval": True,
                "target_model": "purchase.order",
                "record_query": None,
                "document_query": "P00015",
                "product_query": "BACO CLEAN",
                "field_label": "Quantité",
                "field_name": "quantity",
                "new_value": 20,
                "confidence": 0.88,
            },
            "error": None,
        },
    )

    result = odoo_agent.parse_odoo_action_with_openai(
        "Change quantity of BACO CLEAN in purchase order P00015 to 20"
    )

    assert result["action"] == "update_document_line"
    assert result["target_model"] == "purchase.order"
    assert result["field_name"] == "product_qty"
    assert result["new_value"] == 20.0
