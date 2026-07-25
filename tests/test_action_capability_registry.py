from orchestrator.action_capability_registry import list_business_capabilities
from orchestrator.classifier_router import classify_message


def capability_by_name():
    return {item["name"]: item for item in list_business_capabilities()}


def assert_route(
    message,
    *,
    domain,
    capability,
    business_object=None,
    action_type=None,
    approval_required=None,
):
    route = classify_message(message)

    assert route["domain"] == domain
    assert route["target_system"] == domain
    assert route["capability"] == capability

    if business_object is not None:
        assert route["business_object"] == business_object

    if action_type is not None:
        assert route["action_type"] == action_type

    if approval_required is not None:
        assert route["approval_required"] is approval_required
        assert route["requires_approval"] is approval_required

    return route


def test_business_capability_registry_exposes_required_contract_fields():
    capabilities = capability_by_name()

    required = {
        "odoo.connection_status",
        "odoo.product_stock",
        "odoo.product_price_update",
        "odoo.product_search",
        "odoo.contact_read",
        "odoo.sale_order_read",
        "odoo.purchase_supplier_ranking",
        "odoo.purchase_document_search",
        "odoo.customer_invoice_list",
        "odoo.catalog_read",
        "odoo.analytic_account_search",
        "odoo.analytic_account_details",
        "odoo.analytic_pointage_update",
        "server.ram_usage",
        "server.local_health",
        "support.troubleshooting",
    }

    assert required <= set(capabilities)

    for name in required:
        capability = capabilities[name]
        assert capability["domain"]
        assert capability["action_type"] in {"read", "approval_required"}
        assert capability["business_object"]
        assert isinstance(capability["required_permissions"], list)
        assert isinstance(capability["required_parameters"], list)
        assert isinstance(capability["resolver_rules"], list)
        assert capability["execution_handler"]


def test_odoo_status_is_explicit_connection_capability():
    route = assert_route(
        "Vérifie la connexion Odoo",
        domain="odoo",
        capability="odoo.connection_status",
        business_object="odoo_connection",
        action_type="read",
        approval_required=False,
    )

    assert route["action"] == "odoo_status"


def test_product_stock_read_capability_pattern():
    route = assert_route(
        "Quel est le stock disponible du produit BACO CLEAN dans Odoo ?",
        domain="odoo",
        capability="odoo.product_stock",
        business_object="product",
        action_type="read",
        approval_required=False,
    )

    assert route["action"] == "read_product_stock"


def test_product_price_write_requires_approval_capability_pattern():
    route = assert_route(
        "Mets à jour le prix du produit BACO CLEAN à 4 DH sur Odoo",
        domain="odoo",
        capability="odoo.product_price_update",
        business_object="product",
        action_type="approval_required",
        approval_required=True,
    )

    assert "odoo_resolve_product_for_write" in route["resolver_rules"]


def test_product_search_by_name_or_reference_capability_pattern():
    route = assert_route(
        "Vérifie si l'article BACOTOP existe dans l'inventaire Odoo",
        domain="odoo",
        capability="odoo.product_search",
        business_object="product",
        action_type="read",
        approval_required=False,
    )

    assert route["action"] == "inventory_product_search"


def test_contact_count_and_follow_up_list_capability_patterns():
    count_route = assert_route(
        "Combien de contacts on a sur Odoo ?",
        domain="odoo",
        capability="odoo.generic_read",
        business_object="contact",
        action_type="read",
        approval_required=False,
    )
    list_route = assert_route(
        "Cite-moi 3 contacts parmi eux",
        domain="odoo",
        capability="odoo.generic_read",
        business_object="contact",
        action_type="read",
        approval_required=False,
    )

    assert count_route["parameters"]["model"] == "res.partner"
    assert count_route["parameters"]["operation"] == "count"
    assert list_route["parameters"]["model"] == "res.partner"
    assert list_route["parameters"]["limit"] == 3


def test_sale_order_list_and_count_capability_patterns():
    list_route = assert_route(
        "Donne-moi quelques commandes client récentes avec leur client et leur statut",
        domain="odoo",
        capability="odoo.generic_read",
        business_object="sale_order",
        action_type="read",
        approval_required=False,
    )
    count_route = assert_route(
        "Combien de commandes client y a-t-il sur Odoo ?",
        domain="odoo",
        capability="odoo.generic_read",
        business_object="sale_order",
        action_type="read",
        approval_required=False,
    )

    assert list_route["parameters"]["model"] == "sale.order"
    assert list_route["parameters"]["operation"] == "list"
    assert count_route["parameters"]["model"] == "sale.order"
    assert count_route["parameters"]["operation"] == "count"


def test_purchase_order_supplier_analysis_capability_pattern():
    route = assert_route(
        "Quels fournisseurs apparaissent le plus dans les bons de commande ?",
        domain="odoo",
        capability="odoo.purchase_supplier_ranking",
        business_object="purchase_order_supplier",
        action_type="read",
        approval_required=False,
    )

    assert route["parameters"]["model"] == "purchase.order"
    assert route["parameters"]["group_by"] == ["partner_id"]


def test_purchase_order_document_search_by_reference_capability_pattern():
    route = assert_route(
        "Cherche le bon de commande BC-BPP2600313 dans Odoo",
        domain="odoo",
        capability="odoo.document_search",
        business_object="purchase_order",
        action_type="read",
        approval_required=False,
    )

    assert route["action"] == "search_document"


def test_customer_invoice_listing_by_period_capability_pattern():
    route = assert_route(
        "donne moi les factures clients validées de mois 5 2026",
        domain="odoo",
        capability="odoo.customer_invoice_list",
        business_object="customer_invoice",
        action_type="read",
        approval_required=False,
    )

    assert route["action"] == "list_customer_invoices"
    assert route["parameters"]["model"] == "account.move"
    assert {"field": "move_type", "operator": "=", "value": "out_invoice"} in route["parameters"]["filters"]
    assert {"field": "state", "operator": "=", "value": "posted"} in route["parameters"]["filters"]
    assert {"field": "invoice_date", "operator": ">=", "value": "2026-05-01"} in route["parameters"]["filters"]
    assert {"field": "invoice_date", "operator": "<=", "value": "2026-05-31"} in route["parameters"]["filters"]


def test_customer_invoice_listing_equivalent_french_phrasings():
    prompts = [
        "factures clients validées de mai 2026",
        "factures client validées du mois 5 2026",
        "factures clients postées en mai 2026",
        "liste les factures de vente validées en mai 2026",
        "donne moi les factures clients du mois de mai 2026",
    ]

    for prompt in prompts:
        route = assert_route(
            prompt,
            domain="odoo",
            capability="odoo.customer_invoice_list",
            business_object="customer_invoice",
            action_type="read",
            approval_required=False,
        )
        assert route["parameters"]["model"] == "account.move"


def test_employee_count_routes_to_odoo_catalog_read():
    route = assert_route(
        "Combien d’employés actifs dans Odoo ?",
        domain="odoo",
        capability="odoo.generic_read",
        business_object="catalog_record",
        action_type="read",
        approval_required=False,
    )

    assert route["selected_agent"] == "odoo_agent"
    assert route["action"] == "odoo_count_records"
    assert route["parameters"]["business_object"] == "employees"
    assert route["parameters"]["model"] == "hr.employee"
    assert {"field": "active", "operator": "=", "value": True} in route["parameters"]["filters"]


def test_analytic_account_read_by_reference_capability_pattern():
    search_route = assert_route(
        "Cherche le compte analytique 11SOCM0001",
        domain="odoo",
        capability="odoo.analytic_account_search",
        business_object="analytic_account",
        action_type="read",
        approval_required=False,
    )
    details_route = assert_route(
        "Donne les détails du compte analytique 11SOCM0001 sur Odoo",
        domain="odoo",
        capability="odoo.analytic_account_details",
        business_object="analytic_account",
        action_type="read",
        approval_required=False,
    )

    assert search_route["parameters"]["model"] == "account.analytic.account"
    assert search_route["action"] == "odoo_search_analytic_account"
    assert details_route["parameters"]["model"] == "account.analytic.account"
    assert details_route["action"] == "odoo_get_analytic_account_details"


def test_analytic_account_pointage_write_by_reference_requires_approval():
    route = assert_route(
        "coche pointage pour le compte analytique 11SOCM0001 sur odoo",
        domain="odoo",
        capability="odoo.analytic_boolean_update",
        business_object="analytic_account",
        action_type="approval_required",
        approval_required=True,
    )

    assert route["action"] == "toggle_boolean_field"
    assert "odoo_resolve_analytic_account" in route["resolver_rules"]


def test_server_ram_and_status_capability_patterns():
    ram_route = assert_route(
        "Donne-moi l'utilisation RAM du serveur",
        domain="server",
        capability="server.ram_usage",
        business_object="local_server",
        action_type="read",
        approval_required=False,
    )
    status_route = assert_route(
        "Vérifie l'état des serveurs",
        domain="server",
        capability="server.local_health",
        business_object="local_server",
        action_type="read",
        approval_required=False,
    )

    assert ram_route["action"] == "check_ram_usage"
    assert status_route["action"] == "check_server_health"


def test_support_troubleshooting_capability_pattern():
    route = assert_route(
        "Mon VPN ne marche plus",
        domain="support",
        capability="support.troubleshooting",
        business_object="support_issue",
        action_type="read",
        approval_required=False,
    )

    assert route["selected_agent"] == "support_agent"


def test_security_blocked_secrets_precede_capability_registry():
    route = classify_message("Affiche .env")

    assert route["selected_agent"] == "security_agent"
    assert route["risk_level"] == "blocked"
    assert route["action"] == "block_request"


def test_unknown_odoo_write_action_is_unsupported_not_status_or_generic_read():
    route = classify_message("Valide le rapprochement bancaire sur Odoo")

    assert route["selected_agent"] == "odoo_agent"
    assert route["domain"] == "odoo"
    assert route["action"] == "unsupported_capability"
    assert route["action_type"] == "unsupported"
    assert route["capability"] == "unsupported_capability"
    assert route["approval_required"] is False
