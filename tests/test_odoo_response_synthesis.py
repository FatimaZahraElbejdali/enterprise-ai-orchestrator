from datetime import datetime

import agents.odoo_response_synthesizer as synthesizer
from integrations.odoo_connector import OdooConnector
from orchestrator.temporal import resolve_relative_period


class FakeTemporalModels:
    def __init__(self):
        self.calls = []

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        kwargs = kwargs or {}
        self.calls.append((model, method, args, kwargs))

        if model == "ir.model" and method == "search_read":
            return [{"model": "x.business.record", "name": "Business Record"}]

        if method == "fields_get":
            return {
                "name": {"string": "Name", "type": "char"},
                "state": {"string": "State", "type": "selection", "selection": [("open", "Open")]},
                "owner_id": {"string": "Owner", "type": "many2one", "relation": "res.partner"},
                "created_at": {"string": "Created At", "type": "datetime", "store": True},
            }

        if method == "search_read":
            return []

        raise AssertionError(f"Unexpected RPC call: {model}.{method}")


def _fake_connector(fake_models):
    connector = OdooConnector()
    connector.mock_mode = False
    connector.uid = 1
    connector.database = "test-db"
    connector.auth_secret = "secret"
    connector._models = lambda: fake_models
    return connector


def test_search_one_result_uses_returned_record_without_static_success(monkeypatch):
    def fake_generate_response(prompt, system_prompt=None, **kwargs):
        assert "ENTITY-001" in prompt
        assert "normalized_result" in prompt
        return {"success": True, "response": "Oui, un enregistrement correspondant existe : ENTITY-001."}

    monkeypatch.setattr(synthesizer, "generate_response", fake_generate_response)
    normalized = synthesizer.normalize_odoo_read_result(
        {
            "status": "completed",
            "model": "x.business.record",
            "record_count": 1,
            "records": [{"id": 1, "name": "ENTITY-001", "state": "open"}],
        },
        operation="search",
        query_context={"requested_entity": "ENTITY-001"},
    )

    result = synthesizer.synthesize_odoo_read_response(
        user_message="Does ENTITY-001 exist?",
        semantic_request={"operation": "search"},
        normalized_result=normalized,
    )

    assert result["response"] == "Oui, un enregistrement correspondant existe : ENTITY-001."
    assert "Produits correspondants" not in result["response"]
    assert "Document consulté" not in result["response"]


def test_product_price_defaults_to_mad_when_currency_missing(monkeypatch):
    monkeypatch.setattr(
        synthesizer,
        "generate_response",
        lambda *args, **kwargs: {"success": False, "response": "", "error": "provider_unavailable"},
    )
    normalized = synthesizer.normalize_odoo_read_result(
        {
            "status": "completed",
            "model": "product.product",
            "record_count": 1,
            "record": {
                "id": 3471,
                "name": "BACO CLEAN",
                "sale_price": 10.0,
                "unit": "Unité(s)",
            },
        },
        operation="read",
    )

    result = synthesizer.synthesize_odoo_read_response(
        user_message="Quel est le prix de vente de BACO CLEAN ?",
        semantic_request={"operation": "read", "business_object": "product"},
        normalized_result=normalized,
    )

    assert "10.0 MAD" in result["response"]
    assert chr(8364) not in result["response"]


def test_generated_odoo_price_response_cannot_use_euro_without_eur_currency(monkeypatch):
    monkeypatch.setattr(
        synthesizer,
        "generate_response",
        lambda *args, **kwargs: {
            "success": True,
            "response": f"Le prix de vente de BACO CLEAN est de 10.0 {chr(8364)} par Unité(s).",
            "provider": "openai",
            "model": "gpt-4.1-mini",
        },
    )
    normalized = synthesizer.normalize_odoo_read_result(
        {
            "status": "completed",
            "model": "product.product",
            "record_count": 1,
            "record": {
                "id": 3471,
                "name": "BACO CLEAN",
                "sale_price": 10.0,
                "unit": "Unité(s)",
            },
        },
        operation="read",
    )

    result = synthesizer.synthesize_odoo_read_response(
        user_message="Quel est le prix de vente de BACO CLEAN ?",
        semantic_request={"operation": "read", "business_object": "product"},
        normalized_result=normalized,
    )

    assert result["used_llm"] is True
    assert "10.0 MAD" in result["response"]
    assert chr(8364) not in result["response"]


def test_generated_odoo_price_response_keeps_explicit_eur_currency(monkeypatch):
    monkeypatch.setattr(
        synthesizer,
        "generate_response",
        lambda *args, **kwargs: {
            "success": True,
            "response": f"Le prix est de 10.0 {chr(8364)}.",
        },
    )
    normalized = synthesizer.normalize_odoo_read_result(
        {
            "status": "completed",
            "model": "product.product",
            "record_count": 1,
            "record": {
                "id": 1,
                "name": "Export EUR",
                "sale_price": 10.0,
                "currency": "EUR",
            },
        },
        operation="read",
    )

    result = synthesizer.synthesize_odoo_read_response(
        user_message="Quel est le prix ?",
        semantic_request={"operation": "read", "business_object": "product"},
        normalized_result=normalized,
    )

    assert chr(8364) in result["response"]


def test_search_zero_results_reports_no_match_without_inventing(monkeypatch):
    monkeypatch.setattr(
        synthesizer,
        "generate_response",
        lambda *args, **kwargs: {"success": False, "response": "", "error": "provider_unavailable"},
    )
    normalized = synthesizer.normalize_odoo_read_result(
        {
            "status": "not_found",
            "model": "x.business.record",
            "record_count": 0,
            "records": [],
        },
        operation="search",
    )

    result = synthesizer.synthesize_odoo_read_response(
        user_message="Find ENTITY-404",
        semantic_request={"operation": "search"},
        normalized_result=normalized,
    )

    assert "Aucun enregistrement correspondant" in result["response"]
    assert "ENTITY-001" not in result["response"]


def test_count_result_uses_exact_record_count(monkeypatch):
    monkeypatch.setattr(
        synthesizer,
        "generate_response",
        lambda *args, **kwargs: {"success": False, "response": "", "error": "provider_unavailable"},
    )
    normalized = synthesizer.normalize_odoo_read_result(
        {
            "status": "completed",
            "model": "x.business.record",
            "record_count": 42,
        },
        operation="count",
    )

    result = synthesizer.synthesize_odoo_read_response(
        user_message="How many matching records exist?",
        semantic_request={"operation": "count"},
        normalized_result=normalized,
    )

    assert "42" in result["response"]


def test_aggregate_result_reflects_actual_groups_and_metrics(monkeypatch):
    monkeypatch.setattr(
        synthesizer,
        "generate_response",
        lambda *args, **kwargs: {"success": False, "response": "", "error": "provider_unavailable"},
    )
    normalized = synthesizer.normalize_odoo_read_result(
        {
            "status": "completed",
            "model": "x.business.record",
            "group_count": 3,
            "groups": [
                {"group": {"field": "owner_id", "value": {"id": 1, "display_name": "Alpha"}}, "metrics": {"record_count": 8}},
                {"group": {"field": "owner_id", "value": {"id": 2, "display_name": "Beta"}}, "metrics": {"record_count": 5}},
                {"group": {"field": "owner_id", "value": {"id": 3, "display_name": "Gamma"}}, "metrics": {"record_count": 2}},
            ],
        },
        operation="aggregate",
    )

    result = synthesizer.synthesize_odoo_read_response(
        user_message="Rank matching records by owner.",
        semantic_request={"operation": "aggregate", "group_by": ["owner_id"]},
        normalized_result=normalized,
    )

    assert "Alpha" in result["response"]
    assert "8" in result["response"]
    assert "Beta" in result["response"]
    assert "5" in result["response"]
    assert "Gamma" in result["response"]
    assert "2" in result["response"]


def test_unresolved_business_scope_does_not_label_records_as_requested_concept(monkeypatch):
    def overconfident_generate_response(*args, **kwargs):
        raise AssertionError("unresolved business scope must not be sent to LLM synthesis")

    monkeypatch.setattr(synthesizer, "generate_response", overconfident_generate_response)
    normalized = synthesizer.normalize_odoo_read_result(
        {
            "status": "completed",
            "model": "x.business.record",
            "record_count": 1,
            "records": [{"id": 1, "name": "ENTITY-001"}],
            "business_scope_status": "unresolved",
        },
        operation="search",
        query_context={"business_object": "narrow synthetic concept"},
    )

    result = synthesizer.synthesize_odoo_read_response(
        user_message="List narrow synthetic concept records",
        semantic_request={"operation": "search"},
        normalized_result=normalized,
    )

    assert result["used_llm"] is False
    assert "périmètre métier" in result["response"]
    assert "ENTITY-001" not in result["response"]
    assert "narrow synthetic concept" not in result["response"]


def test_relative_period_resolver_uses_half_open_month_and_year_boundaries():
    current_month = resolve_relative_period(
        {"type": "relative_period", "period": "month", "offset": 0},
        now=datetime(2026, 7, 10, 15, 30),
        timezone_name="UTC",
    )
    previous_month = resolve_relative_period(
        {"type": "relative_period", "period": "month", "offset": -1},
        now=datetime(2026, 7, 10, 15, 30),
        timezone_name="UTC",
    )
    current_year = resolve_relative_period(
        {"type": "relative_period", "period": "year", "offset": 0},
        now=datetime(2026, 7, 10, 15, 30),
        timezone_name="UTC",
    )

    assert current_month["start"].isoformat() == "2026-07-01T00:00:00+00:00"
    assert current_month["end"].isoformat() == "2026-08-01T00:00:00+00:00"
    assert previous_month["start"].isoformat() == "2026-06-01T00:00:00+00:00"
    assert previous_month["end"].isoformat() == "2026-07-01T00:00:00+00:00"
    assert current_year["start"].isoformat() == "2026-01-01T00:00:00+00:00"
    assert current_year["end"].isoformat() == "2027-01-01T00:00:00+00:00"


def test_structured_relative_period_filter_validates_date_field(monkeypatch):
    fake = FakeTemporalModels()
    connector = _fake_connector(fake)

    monkeypatch.setattr(
        "integrations.odoo_connector.resolve_relative_period",
        lambda value: {
            "start": datetime(2026, 7, 1, 0, 0),
            "end": datetime(2026, 8, 1, 0, 0),
            "period": value["period"],
            "offset": value["offset"],
        },
    )

    result = connector.agent_search_records(
        model_name="x.business.record",
        domain=[
            {
                "field": "created_at",
                "operator": "relative_period",
                "value": {"type": "relative_period", "period": "month", "offset": 0},
            }
        ],
        fields=["name", "created_at"],
        limit=5,
        order=None,
    )

    search_call = [
        call
        for call in fake.calls
        if call[0] == "x.business.record" and call[1] == "search_read"
    ][0]

    assert result["status"] == "completed"
    assert search_call[2][0] == [
        ["created_at", ">=", "2026-07-01 00:00:00"],
        ["created_at", "<", "2026-08-01 00:00:00"],
    ]
    assert result["validated_filters"][0]["operator"] == "relative_period"


def test_structured_relative_period_filter_rejects_non_date_field(monkeypatch):
    connector = _fake_connector(FakeTemporalModels())

    monkeypatch.setattr(
        "integrations.odoo_connector.resolve_relative_period",
        lambda value: {
            "start": datetime(2026, 7, 1, 0, 0),
            "end": datetime(2026, 8, 1, 0, 0),
            "period": value["period"],
            "offset": value["offset"],
        },
    )

    result = connector.agent_search_records(
        model_name="x.business.record",
        domain=[
            {
                "field": "name",
                "operator": "relative_period",
                "value": {"type": "relative_period", "period": "month", "offset": 0},
            }
        ],
        fields=["name"],
        limit=5,
        order=None,
    )

    assert result["status"] == "denied"
    assert "invalid_temporal_field" in result["message"]
