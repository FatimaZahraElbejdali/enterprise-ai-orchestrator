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
    assert result["parser_source"] == "fallback"


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


def _mock_purchase_date_parse(monkeypatch, field_name="date_order"):
    monkeypatch.setattr(
        "agents.odoo_agent.generate_structured_response",
        lambda **kwargs: {
            "success": True,
            "parsed": {
                "intent": "odoo",
                "action": "update_document_date",
                "risk": "medium",
                "requires_approval": True,
                "target_model": "purchase.order",
                "record_query": None,
                "document_query": "BC-BPP2600313",
                "product_query": None,
                "field_label": "Date de commande",
                "field_name": field_name,
                "new_value": "2026-06-15",
                "confidence": 0.9,
            },
            "error": None,
        },
    )


def test_english_expected_arrival_date_maps_to_date_planned(monkeypatch):
    _mock_purchase_date_parse(monkeypatch)

    result = odoo_agent.parse_odoo_action_with_openai(
        "Change the expected arrival date of purchase order BC-BPP2600313 to 2026-06-15"
    )

    assert result["action"] == "update_document_date"
    assert result["target_model"] == "purchase.order"
    assert result["document_query"] == "BC-BPP2600313"
    assert result["field_name"] == "date_planned"
    assert result["new_value"] == "2026-06-15"
    assert result["requires_approval"] is True


def test_french_expected_arrival_date_maps_to_date_planned(monkeypatch):
    _mock_purchase_date_parse(monkeypatch)

    result = odoo_agent.parse_odoo_action_with_openai(
        "Modifier la date d’arrivée prévue du bon de commande fournisseur BC-BPP2600313 au 15/06/2026"
    )

    assert result["action"] == "update_document_date"
    assert result["target_model"] == "purchase.order"
    assert result["document_query"] == "BC-BPP2600313"
    assert result["field_name"] == "date_planned"


def _mock_structured_document_parse(monkeypatch, parsed):
    monkeypatch.setattr(
        "agents.odoo_agent.generate_structured_response",
        lambda **kwargs: {
            "success": True,
            "parsed": parsed,
            "error": None,
        },
    )


def test_flexible_english_purchase_date_with_supplier(monkeypatch):
    _mock_structured_document_parse(
        monkeypatch,
        {
            "intent": "odoo_document_action",
            "action": "update_document_date",
            "document_type": "purchase_order",
            "document_reference": "BC-BPP2600313",
            "document_id": None,
            "partner_name": "P.A.N",
            "line_product": None,
            "field": "expected_arrival_date",
            "technical_field": "date_planned",
            "new_value": "2026-06-15",
            "language": "en",
            "needs_clarification": False,
            "clarification_reason": None,
            "risk": "high",
            "requires_approval": True,
            "target_model": None,
            "record_query": None,
            "document_query": None,
            "product_query": None,
            "field_label": None,
            "field_name": None,
            "confidence": 0.95,
        },
    )

    result = odoo_agent.parse_odoo_action_with_openai(
        "Change the expected arrival date of purchase order BC-BPP2600313 for supplier P.A.N to 2026-06-15"
    )

    assert result["intent"] == "odoo_document_action"
    assert result["action"] == "update_document_date"
    assert result["target_model"] == "purchase.order"
    assert result["document_type"] == "purchase_order"
    assert result["document_query"] == "BC-BPP2600313"
    assert result["document_reference"] == "BC-BPP2600313"
    assert result["partner_name"] == "P.A.N"
    assert result["field"] == "expected_arrival_date"
    assert result["technical_field"] == "date_planned"
    assert result["field_name"] == "date_planned"


def test_flexible_french_purchase_date_with_supplier(monkeypatch):
    _mock_structured_document_parse(
        monkeypatch,
        {
            "intent": "odoo_document_action",
            "action": "update_document_date",
            "document_type": "purchase_order",
            "document_reference": "BC-BPP2600313",
            "document_id": None,
            "partner_name": "P.A.N",
            "line_product": None,
            "field": "expected_arrival_date",
            "technical_field": "date_planned",
            "new_value": "2026-06-15",
            "language": "fr",
            "needs_clarification": False,
            "clarification_reason": None,
            "risk": "high",
            "requires_approval": True,
            "target_model": None,
            "record_query": None,
            "document_query": None,
            "product_query": None,
            "field_label": None,
            "field_name": None,
            "confidence": 0.95,
        },
    )

    result = odoo_agent.parse_odoo_action_with_openai(
        "Modifier la date d’arrivée prévue du bon de commande fournisseur BC-BPP2600313 pour le fournisseur P.A.N au 15/06/2026"
    )

    assert result["action"] == "update_document_date"
    assert result["target_model"] == "purchase.order"
    assert result["document_query"] == "BC-BPP2600313"
    assert result["partner_name"] == "P.A.N"
    assert result["field_name"] == "date_planned"


def test_record_id_purchase_date_parse(monkeypatch):
    _mock_structured_document_parse(
        monkeypatch,
        {
            "intent": "odoo_document_action",
            "action": "update_document_date",
            "document_type": "purchase_order",
            "document_reference": None,
            "document_id": 793,
            "partner_name": None,
            "line_product": None,
            "field": "expected_arrival_date",
            "technical_field": "date_planned",
            "new_value": "2026-06-15",
            "language": "en",
            "needs_clarification": False,
            "clarification_reason": None,
            "risk": "high",
            "requires_approval": True,
            "target_model": None,
            "record_query": None,
            "document_query": None,
            "product_query": None,
            "field_label": None,
            "field_name": None,
            "confidence": 0.9,
        },
    )

    result = odoo_agent.parse_odoo_action_with_openai(
        "Change purchase order ID 793 expected arrival date to 2026-06-15"
    )

    assert result["document_id"] == 793
    assert result["document_query"] is None
    assert result["field_name"] == "date_planned"


def test_generic_inventory_summary_parse(monkeypatch):
    _mock_structured_document_parse(
        monkeypatch,
        {
            "intent": "odoo",
            "action": "inventory_summary",
            "language": "fr",
            "requires_approval": False,
            "needs_clarification": False,
            "clarification_reason": None,
            "entities": {
                "product_name": None,
                "document_type": None,
                "document_reference": None,
                "document_id": None,
                "partner_name": None,
                "line_product": None,
                "field": None,
                "new_value": None,
                "filename": None,
                "content": None,
            },
        },
    )

    result = odoo_agent.parse_odoo_action_with_openai(
        "Combien de produits avons-nous en stock ?"
    )

    assert result["action"] == "inventory_summary"
    assert result["business_action"] == "inventory_summary"
    assert result["record_query"] is None
    assert result["requires_approval"] is False


def test_generic_update_product_price_parse(monkeypatch):
    _mock_structured_document_parse(
        monkeypatch,
        {
            "intent": "odoo",
            "action": "update_product_price",
            "language": "fr",
            "requires_approval": True,
            "needs_clarification": False,
            "clarification_reason": None,
            "entities": {
                "product_name": "BACO CLEAN",
                "document_type": None,
                "document_reference": None,
                "document_id": None,
                "partner_name": None,
                "line_product": None,
                "field": "price_unit",
                "new_value": 7,
                "filename": None,
                "content": None,
            },
        },
    )

    result = odoo_agent.parse_odoo_action_with_openai(
        "Modifier le prix de BACO CLEAN à 7 DH"
    )

    assert result["action"] == "change_price"
    assert result["business_action"] == "update_product_price"
    assert result["record_query"] == "BACO CLEAN"
    assert result["new_value"] == 7.0
    assert result["requires_approval"] is True
