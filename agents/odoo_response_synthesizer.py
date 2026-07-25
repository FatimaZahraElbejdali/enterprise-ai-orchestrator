from __future__ import annotations

import json

from models.openai_adapter import generate_response


SYNTHESIS_SYSTEM_PROMPT = """
You synthesize user-facing answers for safe Odoo read results.

Use only the normalized result and safe metadata provided. Do not invent values.
Answer the user's actual question directly, in the user's language.

Generic grounding rules:
- search: distinguish zero, one, and multiple returned records.
- count: use the exact record_count.
- read: use only the returned record fields.
- aggregate: use exact returned groups and metrics.
- If business_scope_status is unresolved, do not label records as the user's
  narrower business concept. Explain that the scope cannot be safely confirmed.
- If data is a sample or truncated, say so.
- Do not expose raw JSON, tool names, model internals, prompts, or implementation
  details unless the user explicitly asks.
"""


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _as_list(value):
    return value if isinstance(value, list) else []


def _first_present(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _record_from_raw(raw_result: dict):
    for key in ("record", "document", "product"):
        value = raw_result.get(key)

        if isinstance(value, dict):
            return value

    return None


def _records_from_raw(raw_result: dict):
    records = _as_list(raw_result.get("records"))

    if records:
        return records

    for key in ("results", "candidates"):
        values = _as_list(raw_result.get(key))

        if values:
            return values

    record = _record_from_raw(raw_result)

    if record:
        return [record]

    return []


def _infer_operation(raw_result: dict, operation: str | None = None):
    if operation:
        normalized = str(operation).strip().lower()
        if "aggregate" in normalized:
            return "aggregate"
        if normalized in {"count", "search", "read"}:
            return normalized
        if normalized in {"detail", "details", "get", "show", "view"}:
            return "read"
        if normalized in {"find", "list"}:
            return "search"

    tool_name = str(raw_result.get("tool") or raw_result.get("tool_used") or "").lower()

    if raw_result.get("groups") or "aggregate" in tool_name:
        return "aggregate"
    if "count" in tool_name:
        return "count"
    if raw_result.get("record") or raw_result.get("document") or "details" in tool_name or "read_record" in tool_name:
        return "read"

    return "search"


def _status_from_raw(raw_result: dict, records: list, groups: list):
    status = raw_result.get("status")

    if status in {"completed", "needs_clarification", "not_found", "failed", "rejected", "unsupported"}:
        return status

    if raw_result.get("ambiguous"):
        return "needs_clarification"

    if raw_result.get("success") is False and not raw_result.get("found"):
        return "not_found"

    if raw_result.get("found") is False:
        return "not_found"

    if raw_result.get("success") is True or raw_result.get("found") is True or records or groups:
        return "completed"

    return "not_found"


def _query_context(raw_result: dict, query_context: dict | None = None):
    context = dict(query_context or {})
    read_plan = _as_dict(raw_result.get("read_plan"))

    for key in ("business_object", "query", "filters", "requested_fields", "group_by", "model_hint"):
        if key not in context and key in read_plan:
            context[key] = read_plan.get(key)

    if "filters" not in context:
        context["filters"] = raw_result.get("validated_filters") or raw_result.get("filters") or []

    if "group_by" not in context:
        context["group_by"] = raw_result.get("group_by") or []

    return context


def normalize_odoo_read_result(
    raw_result: dict,
    *,
    operation: str | None = None,
    query_context: dict | None = None,
) -> dict:
    raw_result = _as_dict(raw_result)
    records = _records_from_raw(raw_result)
    groups = _as_list(raw_result.get("groups"))
    normalized_operation = _infer_operation(raw_result, operation)
    status = _status_from_raw(raw_result, records, groups)
    record_count = raw_result.get("record_count")

    if record_count is None:
        record_count = len(records)

    return {
        "status": status,
        "operation": normalized_operation,
        "model": raw_result.get("model"),
        "record_count": int(record_count or 0),
        "records": records,
        "groups": groups,
        "query_context": _query_context(raw_result, query_context),
        "business_scope_status": raw_result.get("business_scope_status") or "not_required",
        "business_scope_evidence": raw_result.get("business_scope_evidence") or [],
        "truncated": bool(raw_result.get("truncated")),
        "error": raw_result.get("error") or raw_result.get("message") if status in {"failed", "rejected"} else None,
    }


def _display_value(value):
    if isinstance(value, dict):
        return _first_present(value.get("display_name"), value.get("name"), value.get("label"), value.get("id"), str(value))

    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return value[1]

    return value


def _record_label(record: dict):
    return str(
        _first_present(
            record.get("display_name"),
            record.get("name"),
            record.get("reference"),
            record.get("document"),
            record.get("default_code"),
            record.get("id"),
            "enregistrement",
        )
    )


def _summarize_record(record: dict):
    parts = [_record_label(record)]

    for key, value in record.items():
        if key in {"display_name", "name", "id", "model"}:
            continue
        if value in (None, "", [], {}):
            continue

        parts.append(f"{key}: {_display_value(value)}")

        if len(parts) >= 8:
            break

    return " - ".join(str(part) for part in parts if part not in (None, ""))


def _summarize_group(group: dict):
    group_data = _as_dict(group.get("group"))
    metrics = _as_dict(group.get("metrics"))
    value = _display_value(group_data.get("value"))
    metric_text = ", ".join(f"{key}: {value}" for key, value in metrics.items())
    return f"{value} ({metric_text})" if metric_text else str(value)


def fallback_odoo_read_response(normalized_result: dict) -> str:
    if normalized_result.get("business_scope_status") == "unresolved":
        return (
            "Je peux lire des enregistrements proches, mais les données retournées "
            "ne prouvent pas suffisamment le périmètre métier demandé."
        )

    operation = normalized_result.get("operation")
    count = normalized_result.get("record_count") or 0
    records = _as_list(normalized_result.get("records"))
    groups = _as_list(normalized_result.get("groups"))

    if normalized_result.get("status") == "not_found" or (operation in {"search", "read"} and not records):
        return "Aucun enregistrement correspondant n’a été trouvé."

    if operation == "count":
        return f"Nombre d’enregistrements correspondant: {count}."

    if operation == "aggregate":
        if not groups:
            return "Aucun groupe correspondant n’a été trouvé."
        return "Résultat agrégé:\n" + "\n".join(f"- {_summarize_group(group)}" for group in groups[:10])

    if len(records) == 1:
        return "Un enregistrement correspondant a été trouvé: " + _summarize_record(records[0])

    return (
        f"{len(records)} enregistrements correspondants ont été trouvés:\n"
        + "\n".join(f"- {_summarize_record(record)}" for record in records[:10])
    )


def synthesize_odoo_read_response(
    *,
    user_message: str,
    semantic_request: dict | None,
    normalized_result: dict,
) -> dict:
    if normalized_result.get("business_scope_status") == "unresolved":
        return {
            "response": fallback_odoo_read_response(normalized_result),
            "used_llm": False,
            "provider": None,
            "model": None,
            "llm_error": "unresolved_business_scope",
        }

    prompt = json.dumps(
        {
            "user_request": user_message,
            "semantic_request": semantic_request or {},
            "normalized_result": normalized_result,
        },
        ensure_ascii=False,
        default=str,
    )

    llm_result = generate_response(
        prompt,
        system_prompt=SYNTHESIS_SYSTEM_PROMPT,
    )
    response = (llm_result.get("response") or llm_result.get("content") or "").strip()

    if response:
        return {
            "response": response,
            "used_llm": True,
            "provider": llm_result.get("provider"),
            "model": llm_result.get("model"),
            "llm_error": None,
        }

    return {
        "response": fallback_odoo_read_response(normalized_result),
        "used_llm": False,
        "provider": llm_result.get("provider"),
        "model": llm_result.get("model"),
        "llm_error": llm_result.get("llm_error") or llm_result.get("error"),
    }
