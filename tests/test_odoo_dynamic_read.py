from fastapi.testclient import TestClient

import agents.odoo_agent as odoo_agent_module
import app as app_module
from app import app
from integrations.odoo_connector import OdooConnector
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
            "tool_used": "odoo_generic_read",
            "target_system": "odoo",
            "odoo_model": "sale.subscription",
            "record_count": 1,
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


def test_odoo_agent_generic_read_uses_structured_plan_not_product_search(monkeypatch):
    calls = []

    def fake_execute_tool(tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        return {
            "success": True,
            "result": {
                "success": True,
                "status": "completed",
                "model": "sale.subscription",
                "display_name": "Subscriptions",
                "record_count": 1,
                "read_plan": kwargs["read_plan"],
                "records": [
                    {"id": 10, "name": "SUB001", "partner_id": "Client A"},
                ],
            },
        }

    monkeypatch.setattr(odoo_agent_module, "execute_tool", fake_execute_tool)
    monkeypatch.setattr(odoo_agent_module, "parse_odoo_action_with_openai", lambda message: (_ for _ in ()).throw(AssertionError("old parser should not run")))
    monkeypatch.setattr(odoo_agent_module, "log_request", lambda data: None)

    result = odoo_agent_module.run(
        "tu peux aller dans odoo et me citer les abonnements",
        classification=generic_read_classification(),
    )

    assert result["status"] == "completed"
    assert result["tool_used"] == "odoo_generic_read"
    assert result["odoo_model"] == "sale.subscription"
    assert calls[0][0] == "odoo_generic_read"
    assert calls[0][1]["read_plan"]["business_object"] == "subscriptions"
