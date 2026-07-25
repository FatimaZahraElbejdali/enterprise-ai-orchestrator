from datetime import date

from orchestrator.odoo_business_catalog import (
    build_odoo_catalog_read_plan,
    match_business_catalog_entry,
    parse_business_period,
)


def test_customer_invoice_prompt_builds_safe_account_move_plan():
    plan = build_odoo_catalog_read_plan(
        "donne moi les factures clients validées de mois 5 2026"
    )

    assert plan["action"] == "odoo_search_records"
    assert plan["operation"] == "list"
    assert plan["business_object"] == "customer_invoices"
    assert plan["model"] == "account.move"
    assert plan["model_hint"] == "account.move"
    assert {"field": "move_type", "operator": "=", "value": "out_invoice"} in plan["filters"]
    assert {"field": "state", "operator": "=", "value": "posted"} in plan["filters"]
    assert {"field": "invoice_date", "operator": ">=", "value": "2026-05-01"} in plan["filters"]
    assert {"field": "invoice_date", "operator": "<=", "value": "2026-05-31"} in plan["filters"]
    assert plan["requested_fields"] == [
        "name",
        "partner_id",
        "invoice_date",
        "amount_total",
        "state",
        "payment_state",
        "currency_id",
    ]


def test_customer_invoice_equivalent_french_phrases_use_same_catalog_entry():
    prompts = [
        "factures clients validées de mai 2026",
        "factures client validées du mois 5 2026",
        "factures clients postées en mai 2026",
        "liste les factures de vente validées en mai 2026",
        "donne moi les factures clients du mois 5 2026",
    ]

    for prompt in prompts:
        plan = build_odoo_catalog_read_plan(prompt)
        assert plan["business_object"] == "customer_invoices"
        assert plan["model"] == "account.move"
        assert {"field": "move_type", "operator": "=", "value": "out_invoice"} in plan["filters"]


def test_vendor_bill_and_order_catalog_entries_are_distinct():
    vendor_bill = match_business_catalog_entry("liste les factures fournisseurs postées")
    sales_order = match_business_catalog_entry("donne moi les commandes client récentes")
    purchase_order = match_business_catalog_entry("liste les bons de commande fournisseur")

    assert vendor_bill.business_object == "vendor_bills"
    assert vendor_bill.model == "account.move"
    assert sales_order.business_object == "sales_orders"
    assert sales_order.model == "sale.order"
    assert purchase_order.business_object == "purchase_orders"
    assert purchase_order.model == "purchase.order"


def test_catalog_date_parser_supports_common_french_periods():
    assert parse_business_period("mois 5 2026") == {
        "start": "2026-05-01",
        "end": "2026-05-31",
        "period": "month",
    }
    assert parse_business_period("juin 2026") == {
        "start": "2026-06-01",
        "end": "2026-06-30",
        "period": "month",
    }
    assert parse_business_period("ce mois-ci", today=date(2026, 7, 24)) == {
        "start": "2026-07-01",
        "end": "2026-07-31",
        "period": "current_month",
    }
    assert parse_business_period("cette année", today=date(2026, 7, 24)) == {
        "start": "2026-01-01",
        "end": "2026-12-31",
        "period": "current_year",
    }


def test_catalog_count_action_for_contacts():
    plan = build_odoo_catalog_read_plan("combien de contacts on a sur odoo")

    assert plan["action"] == "odoo_count_records"
    assert plan["operation"] == "count"
    assert plan["business_object"] == "contacts"
    assert plan["model"] == "res.partner"


def test_catalog_count_action_for_employees_uses_hr_employee():
    plan = build_odoo_catalog_read_plan("combien d’employés actifs dans Odoo ?")

    assert plan["action"] == "odoo_count_records"
    assert plan["operation"] == "count"
    assert plan["business_object"] == "employees"
    assert plan["model"] == "hr.employee"
    assert plan["model_candidates"] == ["hr.employee", "res.users", "res.partner"]
    assert {"field": "active", "operator": "=", "value": True} in plan["filters"]
    assert plan["requested_fields"] == [
        "name",
        "work_email",
        "department_id",
        "job_title",
        "active",
    ]


def test_company_headcount_question_requests_official_or_odoo_clarification():
    plan = build_odoo_catalog_read_plan(
        "il y a combien de personnes qui travaillent à Jamain Baco ?"
    )

    assert plan["business_object"] == "employees"
    assert plan["needs_clarification"] is True
    assert plan["clarification_reason"] == "official_or_odoo_headcount"
