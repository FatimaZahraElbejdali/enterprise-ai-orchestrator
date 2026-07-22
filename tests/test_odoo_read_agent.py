import json

from agents import odoo_read_agent
from integrations.odoo_connector import OdooConnector, DYNAMIC_READ_MAX_LIMIT


class FakeReadAgentModels:
    def __init__(self, catalog=None, fields=None, records=None, groups=None):
        self.catalog = catalog or []
        self.fields = fields or {}
        self.records = records or {}
        self.groups = groups or {}
        self.calls = []

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        kwargs = kwargs or {}
        self.calls.append((model, method, args, kwargs))

        if model == "ir.model" and method == "search_read":
            return self.catalog

        if method == "fields_get":
            return self.fields.get(model, {})

        if method == "search_read":
            limit = kwargs.get("limit") or len(self.records.get(model, []))
            return self.records.get(model, [])[:limit]

        if method == "search_count":
            return len(self.records.get(model, []))

        if method == "read_group":
            return self.groups.get(model, [])

        if method == "read":
            ids = set(args[0]) if args else set()
            return [
                record
                for record in self.records.get(model, [])
                if record.get("id") in ids
            ]

        raise AssertionError(f"Unexpected RPC call: {model}.{method}")


def connector_for(fake_models):
    connector = OdooConnector()
    connector.mock_mode = False
    connector.uid = 1
    connector.database = "test-db"
    connector.auth_secret = "secret"
    connector._models = lambda: fake_models
    return connector


def safe_catalog():
    return [
        {"model": "x.service.order", "name": "Service Order"},
        {"model": "res.users", "name": "Users"},
    ]


def safe_fields():
    return {
        "x.service.order": {
            "name": {"string": "Name", "type": "char"},
            "state": {
                "string": "Status",
                "type": "selection",
                "selection": [("open", "Open"), ("closed", "Closed")],
            },
            "password": {"string": "Password", "type": "char"},
        },
        "res.users": {
            "name": {"string": "Name", "type": "char"},
        },
    }


def test_read_tool_validation_rejects_unknown_tool():
    result = odoo_read_agent.execute_odoo_read_tool("odoo_unlink_records", {})

    assert result["status"] == "denied"
    assert result["validation_allowed"] is False


def test_read_tool_validation_rejects_unknown_and_denied_models():
    connector = connector_for(FakeReadAgentModels(catalog=safe_catalog(), fields=safe_fields()))

    unknown = odoo_read_agent.execute_odoo_read_tool(
        "odoo_describe_model",
        {"model": "x.unknown"},
        connector=connector,
    )
    denied = odoo_read_agent.execute_odoo_read_tool(
        "odoo_describe_model",
        {"model": "res.users"},
        connector=connector,
    )

    assert unknown["status"] == "denied"
    assert "unknown_model" in unknown["message"]
    assert denied["status"] == "denied"
    assert "denied_model" in denied["message"]


def test_read_tool_validation_rejects_unsafe_field_and_invalid_domain_field():
    connector = connector_for(FakeReadAgentModels(catalog=safe_catalog(), fields=safe_fields()))

    unsafe_field = odoo_read_agent.execute_odoo_read_tool(
        "odoo_search_records",
        {
            "model": "x.service.order",
            "domain": [],
            "fields": ["password"],
            "limit": 5,
            "order": None,
        },
        connector=connector,
    )
    invalid_domain = odoo_read_agent.execute_odoo_read_tool(
        "odoo_count_records",
        {
            "model": "x.service.order",
            "domain": [{"field": "password", "operator": "=", "value": "x"}],
        },
        connector=connector,
    )

    assert unsafe_field["status"] == "denied"
    assert unsafe_field["validation_allowed"] is False
    assert invalid_domain["status"] == "denied"
    assert invalid_domain["validation_allowed"] is False


def test_aggregate_records_validates_grouping_and_returns_normalized_counts():
    connector = connector_for(FakeReadAgentModels(
        catalog=[{"model": "x.purchase.doc", "name": "Purchase Document"}],
        fields={
            "x.purchase.doc": {
                "name": {"string": "Reference", "type": "char"},
                "partner_id": {
                    "string": "Supplier",
                    "type": "many2one",
                    "relation": "res.partner",
                    "store": True,
                },
                "password": {"string": "Password", "type": "char"},
            },
        },
        groups={
            "x.purchase.doc": [
                {"partner_id": [10, "Supplier A"], "__count": 8},
                {"partner_id": [20, "Supplier B"], "__count": 5},
                {"partner_id": [30, "Supplier C"], "__count": 2},
            ],
        },
    ))

    result = odoo_read_agent.execute_odoo_read_tool(
        "odoo_aggregate_records",
        {
            "model": "x.purchase.doc",
            "domain": [],
            "group_by": ["partner_id"],
            "aggregates": [{"operation": "count", "field": "id", "alias": "record_count"}],
            "order_by": [{"field": "record_count", "direction": "desc"}],
            "limit": 10,
        },
        connector=connector,
    )

    read_group_call = [
        call
        for call in connector._models().calls
        if call[0] == "x.purchase.doc" and call[1] == "read_group"
    ][0]

    assert read_group_call[2] == [[], ["partner_id"], ["partner_id"]]
    assert result["status"] == "completed"
    assert result["tool"] == "odoo.aggregate_records"
    assert result["validation_allowed"] is True
    assert result["group_by"] == ["partner_id"]
    assert result["group_count"] == 3
    assert result["groups"] == [
        {
            "group": {
                "field": "partner_id",
                "label": "Supplier",
                "type": "many2one",
                "relation": "res.partner",
                "value": {"id": 10, "display_name": "Supplier A"},
            },
            "metrics": {"record_count": 8},
        },
        {
            "group": {
                "field": "partner_id",
                "label": "Supplier",
                "type": "many2one",
                "relation": "res.partner",
                "value": {"id": 20, "display_name": "Supplier B"},
            },
            "metrics": {"record_count": 5},
        },
        {
            "group": {
                "field": "partner_id",
                "label": "Supplier",
                "type": "many2one",
                "relation": "res.partner",
                "value": {"id": 30, "display_name": "Supplier C"},
            },
            "metrics": {"record_count": 2},
        },
    ]


def test_aggregate_records_blocks_sensitive_models_and_fields():
    connector = connector_for(FakeReadAgentModels(
        catalog=safe_catalog(),
        fields=safe_fields(),
    ))

    denied_model = odoo_read_agent.execute_odoo_read_tool(
        "odoo_aggregate_records",
        {
            "model": "res.users",
            "domain": [],
            "group_by": ["name"],
            "aggregates": [{"operation": "count", "field": "id", "alias": "record_count"}],
            "order_by": [{"field": "record_count", "direction": "desc"}],
            "limit": 10,
        },
        connector=connector,
    )
    denied_field = odoo_read_agent.execute_odoo_read_tool(
        "odoo_aggregate_records",
        {
            "model": "x.service.order",
            "domain": [],
            "group_by": ["password"],
            "aggregates": [{"operation": "count", "field": "id", "alias": "record_count"}],
            "order_by": [{"field": "record_count", "direction": "desc"}],
            "limit": 10,
        },
        connector=connector,
    )

    assert denied_model["status"] == "denied"
    assert denied_model["validation_allowed"] is False
    assert denied_field["status"] == "denied"
    assert denied_field["validation_allowed"] is False


def test_read_tool_validation_bounds_excessive_limit():
    records = {
        "x.service.order": [
            {"id": index, "name": f"SO-{index}"}
            for index in range(1, 31)
        ]
    }
    fake = FakeReadAgentModels(catalog=safe_catalog(), fields=safe_fields(), records=records)
    connector = connector_for(fake)

    result = odoo_read_agent.execute_odoo_read_tool(
        "odoo_search_records",
        {
            "model": "x.service.order",
            "domain": [],
            "fields": ["name"],
            "limit": 999,
            "order": None,
        },
        connector=connector,
    )
    search_call = [
        call
        for call in fake.calls
        if call[0] == "x.service.order" and call[1] == "search_read"
    ][0]

    assert search_call[3]["limit"] == DYNAMIC_READ_MAX_LIMIT + 1
    assert result["record_count"] == DYNAMIC_READ_MAX_LIMIT
    assert result["truncated"] is True


def test_write_like_and_arbitrary_rpc_tools_are_unavailable():
    write = odoo_read_agent.execute_odoo_read_tool("odoo_update_field", {})
    rpc = odoo_read_agent.execute_odoo_read_tool("execute_kw", {})

    assert write["status"] == "denied"
    assert rpc["status"] == "denied"


def response_with_tool(response_id, call_id, name, arguments):
    return {
        "id": response_id,
        "output": [
            {
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": json.dumps(arguments),
            }
        ],
    }


def test_multi_step_count_loop_uses_validated_tools(monkeypatch):
    responses = iter([
        response_with_tool("r1", "c1", "odoo_search_models", {"query": "service contracts"}),
        response_with_tool("r2", "c2", "odoo_describe_model", {"model": "x.service.order"}),
        response_with_tool(
            "r3",
            "c3",
            "odoo_count_records",
            {
                "model": "x.service.order",
                "domain": [{"field": "state", "operator": "=", "value": "Open"}],
            },
        ),
        {"id": "r4", "output_text": "Il y a 7 contrats de service ouverts dans Odoo."},
    ])

    def fake_create_response(**kwargs):
        return next(responses), {"provider": "openai", "model": "gpt-test", "success": True, "error": None}

    class FakeConnector:
        def agent_search_models(self, query):
            return {
                "status": "completed",
                "tool": "odoo.search_models",
                "models": [{"model": "x.service.order", "label": "Service Order", "score": 40}],
            }

        def agent_describe_model(self, model):
            return {
                "status": "completed",
                "tool": "odoo.describe_model",
                "model": model,
                "fields": [{"name": "state", "type": "selection"}],
            }

        def agent_count_records(self, model_name, domain):
            assert model_name == "x.service.order"
            assert domain == [{"field": "state", "operator": "=", "value": "Open"}]
            return {
                "status": "completed",
                "tool": "odoo.count_records",
                "model": model_name,
                "domain": [["state", "=", "open"]],
                "record_count": 7,
            }

    monkeypatch.setattr(odoo_read_agent, "_create_openai_response", fake_create_response)

    result = odoo_read_agent.run_odoo_read_agent(
        "Combien de contrats de service sont ouverts ?",
        read_plan={"operation": "count", "business_object": "service contracts"},
        connector=FakeConnector(),
    )

    assert result["status"] == "completed"
    assert result["message"] == "Il y a 7 contrats de service ouverts dans Odoo."
    assert [item["tool"] for item in result["tool_sequence"]] == [
        "odoo.search_models",
        "odoo.describe_model",
        "odoo.count_records",
    ]
    assert all(item["validation_allowed"] for item in result["tool_sequence"])
    assert result["record_count"] == 7


def test_multi_step_list_loop_passes_sanitized_records(monkeypatch):
    captured_outputs = []
    responses = iter([
        response_with_tool("r1", "c1", "odoo_search_models", {"query": "service orders"}),
        response_with_tool("r2", "c2", "odoo_describe_model", {"model": "x.service.order"}),
        response_with_tool(
            "r3",
            "c3",
            "odoo_search_records",
            {
                "model": "x.service.order",
                "domain": [],
                "fields": ["name", "state"],
                "limit": 10,
                "order": "name asc",
            },
        ),
        {"id": "r4", "output_text": "Voici les commandes de service trouvées : SO-001."},
    ])

    def fake_create_response(**kwargs):
        for item in kwargs.get("input_items") or []:
            if item.get("type") == "function_call_output":
                captured_outputs.append(json.loads(item["output"]))

        return next(responses), {"provider": "openai", "model": "gpt-test", "success": True, "error": None}

    class FakeConnector:
        def agent_search_models(self, query):
            return {"status": "completed", "tool": "odoo.search_models", "models": [{"model": "x.service.order"}]}

        def agent_describe_model(self, model):
            return {"status": "completed", "tool": "odoo.describe_model", "model": model, "fields": []}

        def agent_search_records(self, model_name, domain, fields, limit, order):
            return {
                "status": "completed",
                "tool": "odoo.search_records",
                "model": model_name,
                "domain": domain,
                "fields": fields,
                "record_count": 1,
                "records": [{"id": 1, "name": "SO-001", "state": "open"}],
                "truncated": False,
            }

    monkeypatch.setattr(odoo_read_agent, "_create_openai_response", fake_create_response)

    result = odoo_read_agent.run_odoo_read_agent(
        "Liste les commandes de service",
        read_plan={"operation": "list", "business_object": "service orders"},
        connector=FakeConnector(),
    )

    assert result["status"] == "completed"
    assert result["message"] == "Voici les commandes de service trouvées : SO-001."
    assert captured_outputs[-1]["records"] == [{"id": 1, "name": "SO-001", "state": "open"}]


def test_supplier_ranking_uses_aggregate_records(monkeypatch):
    captured_outputs = []
    responses = iter([
        response_with_tool("r1", "c1", "odoo_describe_model", {"model": "x.purchase.doc"}),
        response_with_tool(
            "r2",
            "c2",
            "odoo_aggregate_records",
            {
                "model": "x.purchase.doc",
                "domain": [],
                "group_by": ["partner_id"],
                "aggregates": [{"operation": "count", "field": "id", "alias": "record_count"}],
                "order_by": [{"field": "record_count", "direction": "desc"}],
                "limit": 10,
            },
        ),
        {"id": "r3", "output_text": "Classement exact : Supplier A (8), Supplier B (5), Supplier C (2)."},
    ])

    def fake_create_response(**kwargs):
        for item in kwargs.get("input_items") or []:
            if item.get("type") == "function_call_output":
                captured_outputs.append(json.loads(item["output"]))

        return next(responses), {"provider": "openai", "model": "gpt-test", "success": True, "error": None}

    class FakeConnector:
        def agent_describe_model(self, model):
            return {
                "status": "completed",
                "tool": "odoo.describe_model",
                "model": model,
                "label": "Purchase Document",
                "fields": [
                    {
                        "name": "partner_id",
                        "label": "Supplier",
                        "type": "many2one",
                        "relation": "res.partner",
                    },
                ],
            }

        def agent_aggregate_records(self, model_name, domain, group_by, aggregates, order_by, limit):
            assert model_name == "x.purchase.doc"
            assert group_by == ["partner_id"]
            return {
                "status": "completed",
                "tool": "odoo.aggregate_records",
                "model": model_name,
                "domain": [],
                "group_by": group_by,
                "group_count": 3,
                "groups": [
                    {"group": {"field": "partner_id", "value": {"id": 1, "display_name": "Supplier A"}}, "metrics": {"record_count": 8}},
                    {"group": {"field": "partner_id", "value": {"id": 2, "display_name": "Supplier B"}}, "metrics": {"record_count": 5}},
                    {"group": {"field": "partner_id", "value": {"id": 3, "display_name": "Supplier C"}}, "metrics": {"record_count": 2}},
                ],
            }

    monkeypatch.setattr(odoo_read_agent, "_create_openai_response", fake_create_response)

    result = odoo_read_agent.run_odoo_read_agent(
        "Quels fournisseurs apparaissent le plus ?",
        read_plan={"operation": "aggregate count", "business_object": "purchase documents", "model_hint": "x.purchase.doc"},
        connector=FakeConnector(),
    )

    assert result["status"] == "completed"
    assert result["message"] == "Classement exact : Supplier A (8), Supplier B (5), Supplier C (2)."
    assert result["business_scope_status"] == "proven"
    assert [item["tool"] for item in result["tool_sequence"]] == [
        "odoo.describe_model",
        "odoo.aggregate_records",
    ]
    assert captured_outputs[-1]["groups"][0]["metrics"]["record_count"] == 8
    assert captured_outputs[-1]["business_scope_status"] == "proven"


def test_unproven_business_scope_does_not_label_broad_records_as_narrow_population(monkeypatch):
    responses = iter([
        response_with_tool("r1", "c1", "odoo_describe_model", {"model": "x.document"}),
        response_with_tool(
            "r2",
            "c2",
            "odoo_search_records",
            {
                "model": "x.document",
                "domain": [{"field": "state", "operator": "=", "value": "Draft"}],
                "fields": ["name", "state"],
                "limit": 5,
                "order": None,
            },
        ),
        {"id": "r3", "output_text": "Voici les abonnements en brouillon : DOC-001."},
    ])

    def fake_create_response(**kwargs):
        return next(responses), {"provider": "openai", "model": "gpt-test", "success": True, "error": None}

    class FakeConnector:
        def agent_describe_model(self, model):
            return {
                "status": "completed",
                "tool": "odoo.describe_model",
                "model": model,
                "label": "Document",
                "fields": [
                    {
                        "name": "state",
                        "label": "Status",
                        "type": "selection",
                        "selection": [["draft", "Draft"], ["done", "Done"]],
                    },
                    {"name": "name", "label": "Name", "type": "char"},
                ],
            }

        def agent_search_records(self, model_name, domain, fields, limit, order):
            return {
                "status": "completed",
                "tool": "odoo.search_records",
                "model": model_name,
                "domain": [["state", "=", "draft"]],
                "fields": fields,
                "record_count": 1,
                "records": [{"id": 1, "name": "DOC-001", "state": "draft"}],
            }

    monkeypatch.setattr(odoo_read_agent, "_create_openai_response", fake_create_response)

    result = odoo_read_agent.run_odoo_read_agent(
        "Cite-moi quelques abonnements en brouillon",
        read_plan={"operation": "list", "business_object": "subscriptions"},
        connector=FakeConnector(),
    )

    assert result["status"] == "needs_clarification"
    assert result["business_scope_status"] == "unresolved"
    assert "DOC-001" not in result["message"]
    assert "abonnements en brouillon" not in result["message"].lower()


def test_proven_business_scope_allows_requested_population_label(monkeypatch):
    responses = iter([
        response_with_tool("r1", "c1", "odoo_describe_model", {"model": "x.document"}),
        response_with_tool(
            "r2",
            "c2",
            "odoo_search_records",
            {
                "model": "x.document",
                "domain": [
                    {"field": "subscription_scope", "operator": "=", "value": True},
                    {"field": "state", "operator": "=", "value": "Draft"},
                ],
                "fields": ["name", "state", "subscription_scope"],
                "limit": 5,
                "order": None,
            },
        ),
        {"id": "r3", "output_text": "Voici les subscriptions en brouillon : DOC-001."},
    ])

    def fake_create_response(**kwargs):
        return next(responses), {"provider": "openai", "model": "gpt-test", "success": True, "error": None}

    class FakeConnector:
        def agent_describe_model(self, model):
            return {
                "status": "completed",
                "tool": "odoo.describe_model",
                "model": model,
                "label": "Document",
                "fields": [
                    {"name": "subscription_scope", "label": "Subscription Scope", "type": "boolean"},
                    {"name": "state", "label": "Status", "type": "selection"},
                    {"name": "name", "label": "Name", "type": "char"},
                ],
            }

        def agent_search_records(self, model_name, domain, fields, limit, order):
            return {
                "status": "completed",
                "tool": "odoo.search_records",
                "model": model_name,
                "domain": [["subscription_scope", "=", True], ["state", "=", "draft"]],
                "fields": fields,
                "record_count": 1,
                "records": [{"id": 1, "name": "DOC-001", "state": "draft", "subscription_scope": True}],
            }

    monkeypatch.setattr(odoo_read_agent, "_create_openai_response", fake_create_response)

    result = odoo_read_agent.run_odoo_read_agent(
        "Cite-moi quelques subscriptions en brouillon",
        read_plan={"operation": "list", "business_object": "subscriptions"},
        connector=FakeConnector(),
    )

    assert result["status"] == "completed"
    assert result["business_scope_status"] == "proven"
    assert result["message"] == "Voici les subscriptions en brouillon : DOC-001."


def test_candidate_models_continue_to_schema_inspection_and_read(monkeypatch):
    responses = iter([
        response_with_tool("r1", "c1", "odoo_search_models", {"query": "service activity"}),
        response_with_tool("r2", "c2", "odoo_describe_model", {"model": "x.service.order"}),
        response_with_tool(
            "r3",
            "c3",
            "odoo_search_records",
            {
                "model": "x.service.order",
                "domain": [{"field": "state", "operator": "=", "value": "Open"}],
                "fields": ["name", "state"],
                "limit": 5,
                "order": None,
            },
        ),
        {"id": "r4", "output_text": "Voici les activités de service ouvertes : SO-001."},
    ])

    def fake_create_response(**kwargs):
        return next(responses), {"provider": "openai", "model": "gpt-test", "success": True, "error": None}

    class FakeConnector:
        def agent_search_models(self, query):
            return {
                "status": "completed",
                "tool": "odoo.search_models",
                "models": [
                    {"model": "x.service.order", "label": "Service Order", "score": 22},
                    {"model": "x.service.ticket", "label": "Service Ticket", "score": 18},
                ],
            }

        def agent_describe_model(self, model):
            assert model == "x.service.order"
            return {
                "status": "completed",
                "tool": "odoo.describe_model",
                "model": model,
                "fields": [
                    {
                        "name": "state",
                        "type": "selection",
                        "selection": [["open", "Open"], ["closed", "Closed"]],
                    }
                ],
            }

        def agent_search_records(self, model_name, domain, fields, limit, order):
            assert model_name == "x.service.order"
            assert domain == [{"field": "state", "operator": "=", "value": "Open"}]
            return {
                "status": "completed",
                "tool": "odoo.search_records",
                "model": model_name,
                "domain": [["state", "=", "open"]],
                "fields": fields,
                "record_count": 1,
                "records": [{"id": 1, "name": "SO-001", "state": "open"}],
                "truncated": False,
            }

    monkeypatch.setattr(odoo_read_agent, "_create_openai_response", fake_create_response)

    result = odoo_read_agent.run_odoo_read_agent(
        "Montre les activités de service ouvertes",
        read_plan={"operation": "list", "business_object": "service activity"},
        connector=FakeConnector(),
    )

    assert result["status"] == "completed"
    assert "Souhaitez-vous" not in result["message"]
    assert "préciser" not in result["message"].lower()
    assert [item["tool"] for item in result["tool_sequence"]] == [
        "odoo.search_models",
        "odoo.describe_model",
        "odoo.search_records",
    ]
    assert all(item["validation_allowed"] for item in result["tool_sequence"])


def test_last_allowed_tool_result_gets_final_answer_without_extra_tool(monkeypatch):
    responses = iter([
        response_with_tool("r1", "c1", "odoo_search_models", {"query": "service activity"}),
        response_with_tool("r2", "c2", "odoo_describe_model", {"model": "x.service.order"}),
        {
            "id": "r3",
            "output_text": "Voici la réponse finale avec les métadonnées déjà consultées.",
        },
    ])

    def fake_create_response(**kwargs):
        return next(responses), {"provider": "openai", "model": "gpt-test", "success": True, "error": None}

    class FakeConnector:
        def agent_search_models(self, query):
            return {"status": "completed", "tool": "odoo.search_models", "models": [{"model": "x.service.order"}]}

        def agent_describe_model(self, model):
            return {"status": "completed", "tool": "odoo.describe_model", "model": model, "fields": []}

    monkeypatch.setattr(odoo_read_agent, "_create_openai_response", fake_create_response)

    result = odoo_read_agent.run_odoo_read_agent(
        "Montre les activités de service",
        read_plan={"operation": "list", "business_object": "service activity"},
        connector=FakeConnector(),
        max_tool_calls=2,
    )

    assert result["status"] == "completed"
    assert result["stop_reason"] == "final_answer_after_tool_limit"
    assert result["message"] == "Voici la réponse finale avec les métadonnées déjà consultées."
    assert len(result["tool_sequence"]) == 2


def test_safe_validation_denial_can_be_used_to_continue_with_available_model(monkeypatch):
    responses = iter([
        response_with_tool("r1", "c1", "odoo_describe_model", {"model": "x.missing.model"}),
        response_with_tool("r2", "c2", "odoo_describe_model", {"model": "x.service.order"}),
        response_with_tool(
            "r3",
            "c3",
            "odoo_search_records",
            {
                "model": "x.service.order",
                "domain": [],
                "fields": ["name"],
                "limit": 5,
                "order": None,
            },
        ),
        {"id": "r4", "output_text": "Voici les enregistrements disponibles : SO-001."},
    ])
    observed_tool_outputs = []

    def fake_create_response(**kwargs):
        for item in kwargs.get("input_items") or []:
            if item.get("type") == "function_call_output":
                observed_tool_outputs.append(json.loads(item["output"]))

        return next(responses), {"provider": "openai", "model": "gpt-test", "success": True, "error": None}

    class FakeConnector:
        def agent_describe_model(self, model):
            if model == "x.missing.model":
                return {
                    "status": "denied",
                    "tool": "odoo.describe_model",
                    "model": model,
                    "message": "unknown_model",
                }

            return {
                "status": "completed",
                "tool": "odoo.describe_model",
                "model": model,
                "fields": [{"name": "name", "type": "char"}],
            }

        def agent_search_records(self, model_name, domain, fields, limit, order):
            return {
                "status": "completed",
                "tool": "odoo.search_records",
                "model": model_name,
                "record_count": 1,
                "records": [{"id": 1, "name": "SO-001"}],
            }

    monkeypatch.setattr(odoo_read_agent, "_create_openai_response", fake_create_response)

    result = odoo_read_agent.run_odoo_read_agent(
        "Montre les activités de service",
        read_plan={"operation": "list", "business_object": "service activity"},
        connector=FakeConnector(),
    )

    assert result["status"] == "completed"
    assert result["message"] == "Voici les enregistrements disponibles : SO-001."
    assert [item["status"] for item in result["tool_sequence"]] == [
        "denied",
        "completed",
        "completed",
    ]
    assert observed_tool_outputs[0]["message"] == "unknown_model"


def test_internal_permission_question_is_not_returned_before_safe_read(monkeypatch):
    responses = iter([
        response_with_tool("r1", "c1", "odoo_search_models", {"query": "service activity"}),
        response_with_tool("r2", "c2", "odoo_describe_model", {"model": "x.service.order"}),
        {
            "id": "r3",
            "output_text": "Souhaitez-vous que je vous affiche les commandes de service ouvertes ?",
        },
        response_with_tool(
            "r4",
            "c4",
            "odoo_search_records",
            {
                "model": "x.service.order",
                "domain": [{"field": "state", "operator": "=", "value": "Open"}],
                "fields": ["name"],
                "limit": 5,
                "order": None,
            },
        ),
        {"id": "r5", "output_text": "Voici les commandes de service ouvertes : SO-001."},
    ])
    nudges = []

    def fake_create_response(**kwargs):
        for item in kwargs.get("input_items") or []:
            if item.get("role") == "user" and "Ne demande pas cette permission" in item.get("content", ""):
                nudges.append(item["content"])

        return next(responses), {"provider": "openai", "model": "gpt-test", "success": True, "error": None}

    class FakeConnector:
        def agent_search_models(self, query):
            return {"status": "completed", "tool": "odoo.search_models", "models": [{"model": "x.service.order"}]}

        def agent_describe_model(self, model):
            return {"status": "completed", "tool": "odoo.describe_model", "model": model, "fields": []}

        def agent_search_records(self, model_name, domain, fields, limit, order):
            return {
                "status": "completed",
                "tool": "odoo.search_records",
                "model": model_name,
                "record_count": 1,
                "records": [{"id": 1, "name": "SO-001"}],
            }

    monkeypatch.setattr(odoo_read_agent, "_create_openai_response", fake_create_response)

    result = odoo_read_agent.run_odoo_read_agent(
        "Montre les activités de service ouvertes",
        read_plan={"operation": "list", "business_object": "service activity"},
        connector=FakeConnector(),
    )

    assert result["status"] == "completed"
    assert result["message"] == "Voici les commandes de service ouvertes : SO-001."
    assert "Souhaitez-vous" not in result["message"]
    assert nudges
    assert [item["tool"] for item in result["tool_sequence"]] == [
        "odoo.search_models",
        "odoo.describe_model",
        "odoo.search_records",
    ]


def test_ambiguous_model_flow_asks_for_clarification(monkeypatch):
    responses = iter([
        response_with_tool("r1", "c1", "odoo_search_models", {"query": "records"}),
        {"id": "r2", "output_text": "Je ne peux pas identifier le bon type d’enregistrement Odoo. Pouvez-vous préciser ?"},
    ])

    def fake_create_response(**kwargs):
        return next(responses), {"provider": "openai", "model": "gpt-test", "success": True, "error": None}

    class FakeConnector:
        def agent_search_models(self, query):
            return {
                "status": "completed",
                "tool": "odoo.search_models",
                "models": [
                    {"model": "x.service.order", "label": "Service Order", "score": 20},
                    {"model": "x.service.ticket", "label": "Service Ticket", "score": 20},
                ],
            }

    monkeypatch.setattr(odoo_read_agent, "_create_openai_response", fake_create_response)

    result = odoo_read_agent.run_odoo_read_agent(
        "Montre les enregistrements",
        read_plan={"operation": "list", "business_object": "records"},
        connector=FakeConnector(),
    )

    assert result["status"] == "completed"
    assert "préciser" in result["message"]
    assert [item["tool"] for item in result["tool_sequence"]] == ["odoo.search_models"]


def test_read_agent_does_not_expose_write_tools():
    tool_names = {tool["name"] for tool in odoo_read_agent.ODOO_READ_AGENT_TOOLS}

    assert "odoo_update_field" not in tool_names
    assert "odoo_create_record" not in tool_names
    assert "odoo_delete_record" not in tool_names
