from fastapi.testclient import TestClient

import agents.odoo_agent as odoo_agent_module
import app as app_module
from app import app
from integrations.odoo_connector import OdooConnector
from orchestrator.odoo_business_catalog import build_odoo_catalog_read_plan
from tests.auth_helpers import auth_headers
from tests.semantic_helpers import make_semantic_request


class FakeDynamicModels:
    def __init__(self, catalog=None, fields=None, records=None):
        self.catalog = catalog or []
        self.fields = fields or {}
        self.records = records or {}
        self.calls = []

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        kwargs = kwargs or {}
        self.calls.append((model, method, args, kwargs))

        if model == "ir.model" and method == "search_read":
            return self.catalog

        if method == "fields_get":
            return self.fields.get(model, {})

        if method == "search_read":
            return self.records.get(model, [])

        if method == "read":
            ids = set(args[0]) if args else set()
            return [
                record
                for record in self.records.get(model, [])
                if record.get("id") in ids
            ]

        if method == "search_count":
            return len(self.records.get(model, []))

        raise AssertionError(f"Unexpected RPC call: {model}.{method}")


def dynamic_connector(fake_models):
    connector = OdooConnector()
    connector.mock_mode = False
    connector.uid = 1
    connector.database = "test-db"
    connector.auth_secret = "test-secret"
    connector._models = lambda: fake_models
    return connector


def subscription_catalog():
    return [
        {"model": "sale.subscription", "name": "Subscription-related business model"},
        {"model": "product.template", "name": "Product"},
    ]


def subscription_fields():
    return {
        "sale.subscription": {
            "name": {"string": "Name", "type": "char"},
            "partner_id": {"string": "Customer", "type": "many2one", "relation": "res.partner"},
            "stage_id": {"string": "Stage", "type": "many2one", "relation": "sale.subscription.stage"},
            "recurring_total": {"string": "Recurring Total", "type": "monetary"},
            "api_key": {"string": "API Key", "type": "char"},
            "password": {"string": "Password", "type": "char"},
        },
        "product.template": {
            "name": {"string": "Name", "type": "char"},
        },
    }


def subscription_records():
    return {
        "sale.subscription": [
            {
                "id": 10,
                "name": "SUB001",
                "partner_id": [7, "Client A"],
                "stage_id": [2, "In Progress"],
                "recurring_total": 99.0,
            }
        ]
    }


def employee_fields():
    return {
        "hr.employee": {
            "name": {"string": "Name", "type": "char"},
            "work_email": {"string": "Work Email", "type": "char"},
            "department_id": {"string": "Department", "type": "many2one"},
            "job_title": {"string": "Job Title", "type": "char"},
            "active": {"string": "Active", "type": "boolean"},
        },
        "res.partner": {
            "name": {"string": "Name", "type": "char"},
            "email": {"string": "Email", "type": "char"},
            "active": {"string": "Active", "type": "boolean"},
        },
    }


def test_model_discovery_chooses_semantic_subscription_candidate():
    connector = dynamic_connector(
        FakeDynamicModels(
            catalog=subscription_catalog(),
            fields=subscription_fields(),
            records=subscription_records(),
        )
    )

    result = connector.discover_dynamic_read_model("subscriptions")

    assert result["status"] == "found"
    assert result["model"] == "sale.subscription"


def test_dynamic_read_employee_count_uses_hr_employee_with_active_domain():
    fake_models = FakeDynamicModels(
        catalog=[{"model": "hr.employee", "name": "Employee"}],
        fields=employee_fields(),
        records={
            "hr.employee": [
                {"id": 1, "name": "Employee A", "active": True},
                {"id": 2, "name": "Employee B", "active": True},
            ]
        },
    )
    connector = dynamic_connector(fake_models)

    result = connector.dynamic_read({
        "operation": "count",
        "business_object": "employees",
        "model_hint": "hr.employee",
        "model_candidates": ["hr.employee", "res.users", "res.partner"],
        "filters": [{"field": "active", "operator": "=", "value": True}],
        "requested_fields": ["name", "work_email", "department_id", "job_title", "active"],
    })

    count_call = next(call for call in fake_models.calls if call[1] == "search_count")

    assert result["success"] is True
    assert result["model"] == "hr.employee"
    assert result["record_count"] == 2
    assert ["active", "=", True] in count_call[2][0]


def test_dynamic_read_employee_count_falls_back_to_contacts_with_clear_label():
    fake_models = FakeDynamicModels(
        catalog=[{"model": "res.partner", "name": "Contact"}],
        fields=employee_fields(),
        records={
            "res.partner": [
                {"id": 1, "name": "Contact A", "active": True},
                {"id": 2, "name": "Contact B", "active": True},
                {"id": 3, "name": "Contact C", "active": True},
            ]
        },
    )
    connector = dynamic_connector(fake_models)

    raw_result = connector.dynamic_read({
        "operation": "count",
        "business_object": "employees",
        "model_hint": "hr.employee",
        "model_candidates": ["hr.employee", "res.users", "res.partner"],
        "filters": [{"field": "active", "operator": "=", "value": True}],
        "requested_fields": ["name", "work_email", "department_id", "job_title", "active"],
    })
    response = odoo_agent_module.build_dynamic_read_response(
        "combien d’employés dans Odoo ?",
        {"business_object": "employees", "operation": "count"},
        raw_result,
    )

    assert raw_result["model"] == "res.partner"
    assert raw_result["record_count"] == 3
    assert "contacts Odoo" in response["message"]
    assert "effectif réel" in response["message"]
    assert "3 contacts" in response["message"]


def test_dynamic_read_employee_count_missing_hr_employee_is_clear_limitation():
    fake_models = FakeDynamicModels(catalog=[], fields={}, records={})
    connector = dynamic_connector(fake_models)

    raw_result = connector.dynamic_read({
        "operation": "count",
        "business_object": "employees",
        "model_hint": "hr.employee",
        "model_candidates": ["hr.employee", "res.users", "res.partner"],
        "filters": [{"field": "active", "operator": "=", "value": True}],
    })
    response = odoo_agent_module.build_dynamic_read_response(
        "combien d’employés dans Odoo ?",
        {"business_object": "employees", "operation": "count"},
        raw_result,
    )

    assert raw_result.get("model") is None
    assert response["status"] == "needs_clarification"
    assert "Je n’ai pas accès au module Employés dans Odoo" in response["message"]
    assert "Action non disponible" not in response["message"]


def test_model_discovery_uses_safe_business_fields_to_resolve_model():
    connector = dynamic_connector(
        FakeDynamicModels(
            catalog=[
                {"model": "sale.order", "name": "Sales Order"},
                {"model": "mailing.subscription", "name": "Mailing List Subscription"},
                {"model": "sale.subscription.plan", "name": "Subscription Plan"},
            ],
            fields={
                "sale.order": {
                    "name": {"string": "Order Reference", "type": "char"},
                    "is_subscription": {"string": "Recurring", "type": "boolean"},
                    "subscription_state": {"string": "Subscription Status", "type": "selection"},
                    "subscription_id": {"string": "Parent Contract", "type": "many2one"},
                    "starred": {"string": "Show Subscription on dashboard", "type": "boolean"},
                    "partner_id": {"string": "Customer", "type": "many2one"},
                },
                "mailing.subscription": {
                    "name": {"string": "Name", "type": "char"},
                },
                "sale.subscription.plan": {
                    "name": {"string": "Name", "type": "char"},
                    "active_subs_count": {"string": "Subscriptions", "type": "integer"},
                },
            },
        )
    )

    result = connector.discover_dynamic_read_model("subscription")

    assert result["status"] == "found"
    assert result["model"] == "sale.order"


def test_model_discovery_reports_no_candidate():
    connector = dynamic_connector(
        FakeDynamicModels(
            catalog=[{"model": "product.template", "name": "Product"}],
            fields={"product.template": {"name": {"string": "Name", "type": "char"}}},
        )
    )

    result = connector.discover_dynamic_read_model("timesheets")

    assert result["status"] == "not_found"
    assert result["model"] is None


def test_model_discovery_reports_ambiguous_candidates():
    connector = dynamic_connector(
        FakeDynamicModels(
            catalog=[
                {"model": "x.contract.customer", "name": "Contract"},
                {"model": "x.contract.vendor", "name": "Contract"},
            ],
            fields={
                "x.contract.customer": {"name": {"string": "Name", "type": "char"}},
                "x.contract.vendor": {"name": {"string": "Name", "type": "char"}},
            },
        )
    )

    result = connector.discover_dynamic_read_model("contract")

    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2


def test_sensitive_and_nonexistent_model_hints_are_rejected():
    connector = dynamic_connector(
        FakeDynamicModels(
            catalog=[
                {"model": "res.users", "name": "Users"},
                {"model": "sale.subscription", "name": "Subscriptions"},
            ],
            fields=subscription_fields(),
        )
    )

    sensitive = connector.discover_dynamic_read_model("users", model_hint="res.users")
    missing = connector.discover_dynamic_read_model("subscriptions", model_hint="sale.subscription.line")

    assert sensitive["status"] == "rejected"
    assert missing["status"] == "rejected"


def test_safe_fields_remove_secret_like_fields():
    connector = dynamic_connector(
        FakeDynamicModels(
            catalog=subscription_catalog(),
            fields=subscription_fields(),
        )
    )

    fields = connector.safe_dynamic_fields("sale.subscription")

    assert "name" in fields
    assert "partner_id" in fields
    assert "api_key" not in fields
    assert "password" not in fields


def test_dynamic_read_list_normalizes_many2one_and_filters_fields():
    connector = dynamic_connector(
        FakeDynamicModels(
            catalog=subscription_catalog(),
            fields=subscription_fields(),
            records=subscription_records(),
        )
    )

    result = connector.dynamic_read({
        "operation": "list",
        "business_object": "subscriptions",
        "limit": 5,
    })

    assert result["success"] is True
    assert result["model"] == "sale.subscription"
    assert result["record_count"] == 1
    assert result["records"][0]["partner_id"] == "Client A"
    assert "api_key" not in result["fields"]
    assert "password" not in result["fields"]


def test_dynamic_read_resolves_selection_display_label_filter_to_technical_value():
    fake = FakeDynamicModels(
        catalog=[{"model": "sale.order", "name": "Sales Order"}],
        fields={
            "sale.order": {
                "name": {"string": "Order Reference", "type": "char"},
                "is_subscription": {"string": "Recurring", "type": "boolean"},
                "subscription_state": {
                    "string": "Subscription Status",
                    "type": "selection",
                    "selection": [
                        ("draft", "Brouillon"),
                        ("sale", "Bon de commande"),
                    ],
                },
            },
        },
        records={"sale.order": []},
    )
    connector = dynamic_connector(fake)

    result = connector.dynamic_read({
        "operation": "list",
        "business_object": "abonnements",
        "model_hint": "sale.order",
        "filters": [
            {
                "field": "subscription_state",
                "operator": "=",
                "value": "Brouillon",
            },
        ],
    })

    search_read = [
        call
        for call in fake.calls
        if call[0] == "sale.order" and call[1] == "search_read"
    ][0]
    domain = search_read[2][0]

    assert ["subscription_state", "=", "draft"] in domain
    assert ["subscription_state", "=", "Brouillon"] not in domain
    assert result["validated_filters"] == [
        {
            "field": "subscription_state",
            "operator": "=",
            "value": "draft",
            "input_value": "Brouillon",
            "field_type": "selection",
            "matched_selection_labels": ["Brouillon"],
        }
    ]
    assert result["search_domain"] == domain


def test_dynamic_read_applies_safe_recent_sort_for_sales_orders():
    fake = FakeDynamicModels(
        catalog=[{"model": "sale.order", "name": "Sales Order"}],
        fields={
            "sale.order": {
                "name": {"string": "Order Reference", "type": "char"},
                "partner_id": {"string": "Customer", "type": "many2one"},
                "date_order": {"string": "Order Date", "type": "datetime"},
                "state": {"string": "Status", "type": "selection"},
                "amount_total": {"string": "Total", "type": "monetary"},
                "currency_id": {"string": "Currency", "type": "many2one"},
            },
        },
        records={
            "sale.order": [
                {
                    "id": 10,
                    "name": "SO001",
                    "partner_id": [7, "Client A"],
                    "date_order": "2026-07-22 10:00:00",
                    "state": "sale",
                    "amount_total": 1000.0,
                    "currency_id": [1, "MAD"],
                },
            ],
        },
    )
    connector = dynamic_connector(fake)

    result = connector.dynamic_read({
        "operation": "list",
        "business_object": "sales_orders",
        "model_hint": "sale.order",
        "requested_fields": ["name", "partner_id", "date_order", "state", "amount_total", "currency_id"],
        "filters": [],
        "sort": [
            {"field": "date_order", "direction": "desc"},
            {"field": "id", "direction": "desc"},
        ],
    })

    search_read = [
        call
        for call in fake.calls
        if call[0] == "sale.order" and call[1] == "search_read"
    ][0]

    assert result["status"] == "completed"
    assert result["search_domain"] == []
    assert result["order"] == "date_order desc, id desc"
    assert search_read[3]["order"] == "date_order desc, id desc"


def test_dynamic_read_counts_customer_invoices_with_safe_domain():
    fake = FakeDynamicModels(
        catalog=[{"model": "account.move", "name": "Journal Entry"}],
        fields={
            "account.move": {
                "name": {"string": "Number", "type": "char"},
                "partner_id": {"string": "Customer", "type": "many2one"},
                "invoice_date": {"string": "Invoice Date", "type": "date"},
                "amount_total": {"string": "Total", "type": "monetary"},
                "state": {"string": "Status", "type": "selection"},
                "payment_state": {"string": "Payment Status", "type": "selection"},
                "move_type": {"string": "Type", "type": "selection"},
                "currency_id": {"string": "Currency", "type": "many2one"},
            },
        },
        records={
            "account.move": [
                {
                    "id": 1,
                    "name": "INV001",
                    "move_type": "out_invoice",
                    "state": "posted",
                    "invoice_date": "2026-05-15",
                }
            ],
        },
    )
    connector = dynamic_connector(fake)

    result = connector.dynamic_read(
        build_odoo_catalog_read_plan(
            "Combien de factures clients validées y a-t-il en mai 2026 ?"
        )
    )
    search_count = [
        call
        for call in fake.calls
        if call[0] == "account.move" and call[1] == "search_count"
    ][0]
    domain = search_count[2][0]

    assert result["status"] == "completed"
    assert result["model"] == "account.move"
    assert result["record_count"] == 1
    assert ["move_type", "=", "out_invoice"] in domain
    assert ["state", "=", "posted"] in domain
    assert ["invoice_date", ">=", "2026-05-01"] in domain
    assert ["invoice_date", "<=", "2026-05-31"] in domain


def test_dynamic_read_sale_order_reference_uses_query_domain():
    fake = FakeDynamicModels(
        catalog=[{"model": "sale.order", "name": "Sales Order"}],
        fields={
            "sale.order": {
                "id": {"string": "ID", "type": "integer"},
                "name": {"string": "Order Reference", "type": "char"},
                "display_name": {"string": "Display Name", "type": "char"},
                "partner_id": {"string": "Customer", "type": "many2one"},
                "date_order": {"string": "Order Date", "type": "datetime"},
                "state": {"string": "Status", "type": "selection"},
                "amount_total": {"string": "Total", "type": "monetary"},
                "currency_id": {"string": "Currency", "type": "many2one"},
            },
        },
        records={
            "sale.order": [
                {
                    "id": 1128,
                    "name": "OL-BPP2601128",
                    "partner_id": [7, "Client Atlas"],
                    "date_order": "2026-07-22 10:00:00",
                    "state": "sale",
                }
            ],
        },
    )
    connector = dynamic_connector(fake)

    result = connector.dynamic_read(
        build_odoo_catalog_read_plan("Recherche la commande client OL-BPP2601128")
    )
    search_read = [
        call
        for call in fake.calls
        if call[0] == "sale.order" and call[1] == "search_read"
    ][0]
    domain = search_read[2][0]

    assert result["status"] == "completed"
    assert result["model"] == "sale.order"
    assert ["name", "ilike", "OL-BPP2601128"] in domain


def test_dynamic_read_ignores_nonexistent_model_hint_and_discovers_safely():
    fake = FakeDynamicModels(
        catalog=[
            {"model": "sale.order", "name": "Sales Order"},
            {"model": "mailing.subscription", "name": "Mailing List Subscription"},
        ],
        fields={
            "sale.order": {
                "name": {"string": "Order Reference", "type": "char"},
                "is_subscription": {"string": "Recurring", "type": "boolean"},
                "subscription_state": {"string": "Subscription Status", "type": "selection"},
                "subscription_id": {"string": "Parent Contract", "type": "many2one"},
            },
            "mailing.subscription": {
                "name": {"string": "Name", "type": "char"},
            },
        },
        records={
            "sale.order": [
                {"id": 12, "name": "SO-SUB-001", "subscription_state": "3_progress"},
            ],
        },
    )
    connector = dynamic_connector(fake)

    result = connector.dynamic_read({
        "operation": "list",
        "business_object": "abonnements",
        "model_hint": "subscription.subscription",
    })

    assert result["success"] is True
    assert result["model"] == "sale.order"
    assert result["records"][0]["name"] == "SO-SUB-001"
    assert ("sale.order", "search_read", [[["is_subscription", "=", True]]], {
        "fields": result["fields"],
        "limit": 10,
        "context": {"active_test": False},
    }) in fake.calls


def test_dynamic_read_search_details_and_count_use_read_only_methods():
    fake = FakeDynamicModels(
        catalog=subscription_catalog(),
        fields=subscription_fields(),
        records=subscription_records(),
    )
    connector = dynamic_connector(fake)

    search = connector.dynamic_read({
        "operation": "search",
        "business_object": "subscriptions",
        "query": "SUB001",
    })
    details = connector.dynamic_read({
        "operation": "details",
        "business_object": "subscriptions",
        "record_id": 10,
    })
    count = connector.dynamic_read({
        "operation": "count",
        "business_object": "subscriptions",
    })

    methods = [method for _, method, _, _ in fake.calls]

    assert search["record_count"] == 1
    assert details["records"][0]["name"] == "SUB001"
    assert count["record_count"] == 1
    assert "search_read" in methods
    assert "read" in methods
    assert "search_count" in methods
    assert not {"write", "create", "unlink"} & set(methods)


def test_dynamic_read_list_and_count_share_business_scope_domain():
    fake = FakeDynamicModels(
        catalog=[{"model": "x.service.order", "name": "Service Order"}],
        fields={
            "x.service.order": {
                "name": {"string": "Name", "type": "char"},
                "is_contract": {"string": "Contract", "type": "boolean"},
                "state": {
                    "string": "Status",
                    "type": "selection",
                    "selection": [
                        ("open", "Open"),
                        ("closed", "Closed"),
                    ],
                },
            },
        },
        records={
            "x.service.order": [
                {"id": 41, "name": "SO-001", "is_contract": True, "state": "open"},
            ],
        },
    )
    connector = dynamic_connector(fake)

    list_result = connector.dynamic_read({
        "operation": "list",
        "business_object": "contract",
        "model_hint": "x.service.order",
        "filters": [{"field": "state", "operator": "=", "value": "Open"}],
    })
    count_result = connector.dynamic_read({
        "operation": "count",
        "business_object": "contract",
        "model_hint": "x.service.order",
        "query": "contract",
        "filters": [{"field": "state", "operator": "=", "value": "Open"}],
    })

    search_read = [
        call
        for call in fake.calls
        if call[0] == "x.service.order" and call[1] == "search_read"
    ][0]
    search_count = [
        call
        for call in fake.calls
        if call[0] == "x.service.order" and call[1] == "search_count"
    ][0]

    expected_domain = [
        ["is_contract", "=", True],
        ["state", "=", "open"],
    ]

    assert list_result["model"] == "x.service.order"
    assert count_result["model"] == "x.service.order"
    assert list_result["search_domain"] == expected_domain
    assert count_result["search_domain"] == expected_domain
    assert search_read[2][0] == expected_domain
    assert search_count[2][0] == expected_domain
    assert list_result["business_scope_domain"] == [["is_contract", "=", True]]
    assert count_result["business_scope_domain"] == [["is_contract", "=", True]]
    assert count_result["query_domain"] == []
    assert count_result["validated_filters"] == list_result["validated_filters"]


def test_dynamic_read_ignores_nonstored_boolean_auto_domain():
    fake = FakeDynamicModels(
        catalog=[{"model": "account.tax", "name": "Tax"}],
        fields={
            "account.tax": {
                "name": {"string": "Name", "type": "char"},
                "display_alternative_taxes_field": {
                    "string": "Alternative Taxes",
                    "type": "boolean",
                    "store": False,
                },
            },
        },
        records={"account.tax": []},
    )
    connector = dynamic_connector(fake)

    result = connector.dynamic_read({
        "operation": "list",
        "business_object": "taxes",
    })

    assert result["model"] == "account.tax"
    search_read = [call for call in fake.calls if call[0] == "account.tax" and call[1] == "search_read"][0]
    assert search_read[2] == [[]]


def test_dynamic_read_rpc_error_returns_clean_failure():
    class FailingReadModels(FakeDynamicModels):
        def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
            if model == "account.tax" and method == "search_read":
                raise RuntimeError("non stored field cannot be searched")
            return super().execute_kw(database, uid, auth_secret, model, method, args, kwargs)

    connector = dynamic_connector(
        FailingReadModels(
            catalog=[{"model": "account.tax", "name": "Tax"}],
            fields={"account.tax": {"name": {"string": "Name", "type": "char"}}},
        )
    )

    result = connector.dynamic_read({
        "operation": "list",
        "business_object": "taxes",
    })

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["model"] == "account.tax"


def generic_read_classification():
    return make_semantic_request(
        request_type="enterprise_action",
        domain="odoo",
        capability="odoo.generic_read",
        action="odoo_generic_read",
        execution_mode="tool",
        entities={"business_object": "subscriptions"},
        parameters={"operation": "list", "business_object": "subscriptions", "limit": 5},
    )


def test_chat_generic_read_requires_odoo_read_permission(monkeypatch):
    called = {"value": False}

    monkeypatch.setattr(app_module, "classify_message", lambda *args, **kwargs: generic_read_classification())
    monkeypatch.setattr(app_module, "log_request", lambda data: None)

    def fake_run_odoo_agent(*args, **kwargs):
        called["value"] = True
        return {"status": "completed", "message": "should not run"}

    monkeypatch.setattr(app_module, "run_odoo_agent", fake_run_odoo_agent)

    response = TestClient(app).post(
        "/chat",
        json={"message": "tu peux aller dans odoo et me citer les abonnements"},
        headers=auth_headers("support@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert data["status"] in {"department_access_denied", "denied"}
    assert called["value"] is False


def test_chat_generic_read_authorized_without_approval(monkeypatch):
    monkeypatch.setattr(app_module, "classify_message", lambda *args, **kwargs: generic_read_classification())
    monkeypatch.setattr(app_module, "log_request", lambda data: None)
    monkeypatch.setattr(
        app_module,
        "run_odoo_agent",
        lambda *args, **kwargs: {
            "intent": "odoo",
            "agent": "odoo_agent",
            "status": "completed",
            "message": "Voici les premiers enregistrements trouvés dans Odoo :\n- SUB001",
            "tool_used": "odoo_read_agent",
            "target_system": "odoo",
            "odoo_model": "sale.subscription",
            "record_count": 1,
            "tool_sequence": [
                {
                    "tool": "odoo.search_records",
                    "model": "sale.subscription",
                    "record_count": 1,
                    "status": "completed",
                    "validation_allowed": True,
                }
            ],
            "requires_approval": False,
            "approval_required": False,
        },
    )

    response = TestClient(app).post(
        "/chat",
        json={"message": "tu peux aller dans odoo et me citer les abonnements"},
        headers=auth_headers("admin@company.local"),
    )

    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "completed"
    assert data["requires_approval"] is False
    assert data["technical"]["capability"] == "odoo.generic_read"
    assert data["technical"]["odoo_model"] == "sale.subscription"
    assert data["technical"]["record_count"] == 1
    assert data["technical"]["final_odoo_model"] == "sale.subscription"
    assert data["technical"]["final_record_count"] == 1
    assert data["technical"]["odoo_tool_steps"] == [
        {
            "tool": "odoo.search_records",
            "model": "sale.subscription",
            "record_count": 1,
            "status": "completed",
            "validation_allowed": True,
        }
    ]


def test_odoo_agent_generic_read_uses_structured_plan_not_product_search(monkeypatch):
    calls = []

    def fake_read_agent(message, read_plan=None, **kwargs):
        calls.append((message, read_plan))
        return {
            "status": "completed",
            "message": "Voici les premiers enregistrements trouvés dans Odoo :\n- SUB001",
            "tool_used": "odoo_read_agent",
            "models_used": ["sale.subscription"],
            "record_count": 1,
            "tool_sequence": [
                {"tool": "odoo.search_records", "model": "sale.subscription", "record_count": 1, "validation_allowed": True},
            ],
            "stop_reason": "final_answer",
            "provider": "openai",
            "model": "gpt-test",
            "llm_success": True,
            "llm_error": None,
        }

    monkeypatch.setattr(odoo_agent_module, "run_odoo_read_agent", fake_read_agent)
    monkeypatch.setattr(odoo_agent_module, "parse_odoo_action_with_openai", lambda message: (_ for _ in ()).throw(AssertionError("old parser should not run")))
    monkeypatch.setattr(odoo_agent_module, "log_request", lambda data: None)

    result = odoo_agent_module.run(
        "tu peux aller dans odoo et me citer les abonnements",
        classification=generic_read_classification(),
    )

    assert result["status"] == "completed"
    assert result["tool_used"] == "odoo_read_agent"
    assert result["odoo_model"] == "sale.subscription"
    assert calls[0][1]["business_object"] == "subscriptions"


def test_agentic_broad_read_helper_does_not_require_predefined_capability():
    classification = {
        "request_type": "enterprise_action",
        "domain": "odoo",
        "target_system": "odoo",
        "selected_agent": "odoo_agent",
        "capability": "odoo.unknown_business_read",
        "parameters": {
            "operation": "describe",
            "business_object": "unknown business area",
        },
        "entities": {"business_object": "unknown business area"},
    }
    parsed_action = {
        "action": "unknown",
        "parser_source": "test",
        "requires_approval": False,
        "new_value": None,
    }

    assert odoo_agent_module.should_use_agentic_broad_read(
        "Show me information about unknown business area in Odoo",
        classification,
        parsed_action,
    ) is True


def test_agentic_broad_document_search_without_exact_target_uses_read_agent(monkeypatch):
    calls = []

    classification = {
        "request_type": "enterprise_action",
        "domain": "odoo",
        "target_system": "odoo",
        "selected_agent": "odoo_agent",
        "capability": "odoo.document_search",
        "parameters": {
            "operation": "list",
            "business_object": "recent business documents",
            "limit": 5,
        },
        "entities": {},
    }

    monkeypatch.setattr(
        odoo_agent_module,
        "parse_odoo_action_with_openai",
        lambda message: {
            "action": "search_document",
            "business_action": "document_search",
            "target_model": "sale.order",
            "document_query": None,
            "document_reference": None,
            "document_id": None,
            "record_query": "recent business documents",
            "requires_approval": False,
            "needs_clarification": False,
            "parser_source": "test",
        },
    )
    monkeypatch.setattr(
        odoo_agent_module,
        "execute_tool",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("broad document reads should not use the specialized document tool")
        ),
    )

    def fake_read_agent(message, read_plan=None, **kwargs):
        calls.append((message, read_plan))
        return {
            "status": "completed",
            "message": "Voici les derniers documents trouvés.",
            "tool_used": "odoo_read_agent",
            "models_used": ["sale.order"],
            "record_count": 2,
            "tool_sequence": [
                {"tool": "odoo.search_records", "model": "sale.order", "record_count": 2, "validation_allowed": True},
            ],
            "provider": "openai",
            "model": "gpt-test",
            "llm_success": True,
        }

    monkeypatch.setattr(odoo_agent_module, "run_odoo_read_agent", fake_read_agent)
    monkeypatch.setattr(odoo_agent_module, "log_request", lambda data: None)

    result = odoo_agent_module.run("Show me the latest business documents in Odoo", classification=classification)

    assert result["status"] == "completed"
    assert result["tool_used"] == "odoo_read_agent"
    assert result["odoo_model"] == "sale.order"
    assert result["record_count"] == 2
    assert calls[0][1]["operation"] == "list"
    assert calls[0][1]["business_object"] == "recent business documents"


def test_agentic_broad_read_helper_preserves_exact_document_search():
    classification = {
        "request_type": "enterprise_action",
        "domain": "odoo",
        "target_system": "odoo",
        "selected_agent": "odoo_agent",
        "capability": "odoo.document_search",
        "parameters": {
            "operation": "search",
            "business_object": "supplier invoice",
            "query": "FNP/2026/04016",
        },
        "entities": {"document_reference": "FNP/2026/04016"},
    }
    parsed_action = {
        "action": "search_document",
        "business_action": "document_search",
        "document_query": "FNP/2026/04016",
        "document_reference": "FNP/2026/04016",
        "document_id": None,
        "requires_approval": False,
        "new_value": None,
    }

    assert odoo_agent_module.should_use_agentic_broad_read(
        "Find supplier invoice FNP/2026/04016 in Odoo",
        classification,
        parsed_action,
    ) is False


def test_agentic_broad_read_helper_rejects_structured_write_semantics():
    classification = {
        "request_type": "enterprise_action",
        "domain": "odoo",
        "target_system": "odoo",
        "selected_agent": "odoo_agent",
        "capability": "odoo.unknown_business_write",
        "parameters": {
            "operation": "update",
            "business_object": "unknown business area",
            "field": "status",
            "new_value": "done",
        },
    }
    parsed_action = {
        "action": "unknown",
        "parser_source": "test",
        "requires_approval": False,
        "new_value": None,
    }

    assert odoo_agent_module.should_use_agentic_broad_read(
        "Update unknown business area in Odoo",
        classification,
        parsed_action,
    ) is False
