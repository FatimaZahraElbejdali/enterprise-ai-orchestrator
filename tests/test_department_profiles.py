import json

import models.openai_adapter as openai_adapter
from orchestrator.department_profiles import (
    CANONICAL_DEPARTMENTS,
    DEPARTMENT_PROFILES,
    get_department_profile,
    get_knowledge_scopes,
    is_capability_allowed_for_department,
    list_department_profiles,
    normalize_department,
)


def test_all_canonical_departments_have_public_profiles():
    public_profiles = list_department_profiles()

    assert {profile["department_id"] for profile in public_profiles} == CANONICAL_DEPARTMENTS
    assert set(DEPARTMENT_PROFILES) == CANONICAL_DEPARTMENTS

    for profile in public_profiles:
        assert profile["display_name"]
        assert profile["description"]
        assert "company_common" in profile["knowledge_scopes"]


def test_unknown_department_uses_restrictive_fallback_profile():
    profile = get_department_profile("unknown-business-unit")

    assert normalize_department("unknown-business-unit") == "unknown"
    assert profile.department_id == "unknown"
    assert profile.allowed_agent_domains == frozenset()
    assert profile.allowed_capability_categories == frozenset()
    assert is_capability_allowed_for_department(
        "unknown-business-unit",
        "server.local_health",
    ) is False


def test_department_scope_examples_are_enforced():
    assert is_capability_allowed_for_department(
        "administration",
        "server.local_health",
    ) is True
    assert is_capability_allowed_for_department(
        "administration",
        "odoo.document_search",
        odoo_model="account.move",
    ) is True
    assert is_capability_allowed_for_department(
        "informatique",
        "server.local_health",
    ) is True
    assert is_capability_allowed_for_department(
        "rh",
        "server.local_health",
    ) is False
    assert is_capability_allowed_for_department(
        "comptabilite_finance",
        "odoo.document_search",
        odoo_model="account.move",
    ) is True
    assert is_capability_allowed_for_department(
        "commerciale",
        "odoo.document_search",
        odoo_model="sale.order",
    ) is True
    assert is_capability_allowed_for_department(
        "nettoyage",
        "odoo.product_stock",
        odoo_model="product.product",
    ) is True
    assert is_capability_allowed_for_department(
        "nettoyage",
        "odoo.document_search",
        odoo_model="account.move",
    ) is False
    assert is_capability_allowed_for_department(
        "securite",
        "odoo.document_search",
        odoo_model="account.move",
    ) is False


def test_department_knowledge_scopes_are_prepared():
    assert get_knowledge_scopes("rh") == ("company_common", "rh")
    assert get_knowledge_scopes("informatique") == ("company_common", "informatique")


def test_department_openai_key_status_falls_back_to_central_key(monkeypatch):
    monkeypatch.setattr(openai_adapter, "OpenAI", object)
    monkeypatch.delenv("OPENAI_API_KEY_RH", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "central-test-key")

    status = openai_adapter.get_openai_status(api_key_env="OPENAI_API_KEY_RH")

    assert status["configured"] is True
    assert status["project_env"] == "OPENAI_API_KEY_RH"
    assert status["uses_central_fallback"] is True
    assert "central-test-key" not in json.dumps(status)


def test_profile_serialization_contains_no_secret_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY_FINANCE", "finance-secret-value")

    serialized = get_department_profile("comptabilite_finance").to_public_dict()
    serialized_json = json.dumps(serialized, ensure_ascii=False)

    assert serialized["llm_project_env"] == "OPENAI_API_KEY_FINANCE"
    assert "finance-secret-value" not in serialized_json
