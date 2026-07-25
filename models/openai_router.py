import os

from models.openai_adapter import generate_structured_response, is_openai_configured
from orchestrator.tool_registry import SAFE_ODOO_READ_MODELS, get_capability_metadata


VALID_AGENTS = {
    "odoo_agent",
    "support_agent",
    "server_agent",
    "security_agent",
    "knowledge_agent",
    "development_agent",
    "general_agent",
}

VALID_TARGET_SYSTEMS = {
    "odoo",
    "support",
    "server",
    "security",
    "knowledge",
    "development",
    "general",
}

VALID_RISK_LEVELS = {"low", "medium", "high", "blocked"}
VALID_CONFIDENCE = {"high", "medium", "low"}
VALID_DOMAINS = {"knowledge", "odoo", "support", "server", "security", "development", "general"}
VALID_REQUEST_TYPES = {
    "enterprise_knowledge",
    "general_knowledge",
    "creative_generation",
    "writing_assistance",
    "troubleshooting",
    "enterprise_action",
    "clarification",
    "conversational",
}

READ_OPERATIONS = {
    "count",
    "describe",
    "detail",
    "details",
    "find",
    "get",
    "inspect",
    "list",
    "read",
    "search",
    "show",
    "summary",
    "view",
}

WRITE_OPERATIONS = {
    "approve",
    "cancel",
    "change",
    "create",
    "delete",
    "modify",
    "remove",
    "set",
    "unlink",
    "update",
    "write",
}

BANK_ACCOUNTING_SIGNAL_TERMS = {
    "accounting transaction",
    "accounting transactions",
    "bank statement",
    "bank statements",
    "bank transaction",
    "bank transactions",
    "ecriture bancaire",
    "ecritures bancaires",
    "écriture bancaire",
    "écritures bancaires",
    "journal bancaire",
    "journaux bancaires",
    "releve bancaire",
    "releves bancaires",
    "relevé bancaire",
    "relevés bancaires",
    "transaction bancaire",
    "transactions bancaires",
}

INTENT_ALIASES = {
    "server_documentation_summary": "summarize_server_documentation",
}

SERVER_DIAGNOSTIC_CAPABILITY_BY_SIGNAL = {
    "backend": "server.local_health",
    "cpu": "server.cpu_usage",
    "diagnostic": "server.local_health",
    "disk": "server.disk_usage",
    "disque": "server.disk_usage",
    "etat": "server.local_health",
    "état": "server.local_health",
    "frontend": "server.local_health",
    "health": "server.local_health",
    "local_health": "server.local_health",
    "memory": "server.ram_usage",
    "memoire": "server.ram_usage",
    "ram": "server.ram_usage",
    "service": "server.local_health",
    "services": "server.local_health",
    "state": "server.local_health",
    "status": "server.local_health",
    "uptime": "server.uptime",
}

SERVER_KNOWLEDGE_OPERATIONS = {
    "documentation",
    "document",
    "explain",
    "explanation",
    "resume",
    "résume",
    "summarize",
}

SERVER_DIAGNOSTIC_OPERATIONS = {
    "check",
    "diagnose",
    "diagnostic",
    "etat",
    "état",
    "health",
    "inspect",
    "monitor",
    "state",
    "status",
    "uptime",
}

DOMAIN_AGENT_MAP = {
    "knowledge": "knowledge_agent",
    "odoo": "odoo_agent",
    "support": "support_agent",
    "server": "server_agent",
    "security": "security_agent",
    "development": "development_agent",
    "general": "general_agent",
}

CAPABILITY_LEGACY_ACTIONS = {
    "knowledge.enterprise_answer": "enterprise_answer",
    "knowledge.general_answer": "answer_question",
    "knowledge.creative_generation": "creative_generation",
    "knowledge.writing_assistance": "writing_assistance",
    "support.troubleshooting": "troubleshoot_issue",
    "server.local_health": "check_server_health",
    "server.cpu_usage": "check_cpu_usage",
    "server.ram_usage": "check_ram_usage",
    "server.disk_usage": "check_disk_usage",
    "server.uptime": "check_server_status",
    "odoo.product_stock": "read_product_stock",
    "odoo.product_search": "product_search",
    "odoo.inventory_summary": "inventory_summary",
    "odoo.partner_search": "odoo_search_records",
    "odoo.accounting_bank_read": "bank_accounting_search",
    "odoo.purchase_supplier_ranking": "supplier_ranking",
    "odoo.sale_customer_ranking": "customer_ranking",
    "odoo.connection_status": "odoo_status",
    "odoo.customer_invoice_list": "list_customer_invoices",
    "odoo.analytic_account_search": "odoo_search_analytic_account",
    "odoo.analytic_account_details": "odoo_get_analytic_account_details",
    "odoo.analytic_boolean_update": "toggle_boolean_field",
    "odoo.generic_read": "odoo_generic_read",
    "odoo.generic_read_search": "odoo_search_records",
    "odoo.generic_read_details": "odoo_get_record_details",
    "odoo.document_search": "search_document",
    "odoo.document_details": "read_document",
    "odoo.document_details_by_id": "read_document",
    "odoo.product_price_update": "update_product_price",
    "odoo.generic_write_prepare": "odoo_update_field_request",
}

CAPABILITY_LEGACY_INTENTS = {
    "knowledge.enterprise_answer": "general_information_question",
    "knowledge.general_answer": "general_information_question",
    "knowledge.creative_generation": "creative_generation",
    "knowledge.writing_assistance": "writing_assistance",
    "support.troubleshooting": "support",
    "server.local_health": "server_health_check",
    "server.cpu_usage": "server_cpu_usage",
    "server.ram_usage": "server_ram_usage",
    "server.disk_usage": "server_disk_usage",
    "server.uptime": "server_status",
    "odoo.product_stock": "product_stock_check",
    "odoo.product_search": "product_search",
    "odoo.inventory_summary": "inventory_summary",
    "odoo.partner_search": "partner_search",
    "odoo.accounting_bank_read": "odoo_bank_accounting_search",
    "odoo.purchase_supplier_ranking": "odoo_purchase_supplier_ranking",
    "odoo.sale_customer_ranking": "odoo_sale_customer_ranking",
    "odoo.connection_status": "odoo_connection_status",
    "odoo.customer_invoice_list": "odoo_customer_invoice_list",
    "odoo.analytic_account_search": "odoo_analytic_account_search",
    "odoo.analytic_account_details": "odoo_analytic_account_details",
    "odoo.analytic_boolean_update": "odoo_write_request",
    "odoo.generic_read": "odoo_generic_read",
    "odoo.generic_read_search": "odoo_record_search",
    "odoo.generic_read_details": "odoo_record_details",
    "odoo.document_search": "odoo_document_search",
    "odoo.document_details": "odoo_document_details",
    "odoo.document_details_by_id": "odoo_document_details",
    "odoo.product_price_update": "product_price_update",
    "odoo.generic_write_prepare": "odoo_field_update_request",
}


OPENAI_ROUTER_PROMPT = """
You are the primary semantic router for an Enterprise AI Orchestrator.

Understand the user's natural-language request and return structured routing
metadata only. Never execute tools, approve actions, bypass policy, or reveal
secrets. The backend validates every capability, permission, risk level,
approval requirement, parameter, and tool call.

Return strict JSON with exactly this shape:
{
  "request_type": "enterprise_knowledge | general_knowledge | creative_generation | writing_assistance | troubleshooting | enterprise_action | clarification | conversational",
  "domain": "knowledge | odoo | support | server | security | development | general",
  "capability": "registered capability name or null",
  "requires_internal_context": false,
  "topic": "short semantic topic or null",
  "entities": {},
  "parameters": {},
  "clarification_needed": false,
  "missing_parameters": [],
  "confidence": "high | medium | low",
  "reason": "short safe explanation"
}

Choose capabilities from the registered backend surface:
- knowledge.enterprise_answer: company/project/internal questions that should use scoped knowledge retrieval.
- knowledge.general_answer: public/general informational questions that need no internal context.
- knowledge.creative_generation: naming, ideation, suggestions, creative alternatives.
- knowledge.writing_assistance: rewriting, summarizing, translating, drafting, tone improvement.
- support.troubleshooting: user IT/helpdesk troubleshooting and access problems.
- server.local_health, server.cpu_usage, server.ram_usage, server.disk_usage, server.uptime: safe configured server diagnostics.
- odoo.product_stock, odoo.product_search, odoo.inventory_summary, odoo.partner_search,
  odoo.accounting_bank_read, odoo.purchase_supplier_ranking, odoo.sale_customer_ranking,
  odoo.connection_status, odoo.customer_invoice_list,
  odoo.analytic_account_search, odoo.analytic_account_details,
  odoo.analytic_boolean_update,
  odoo.generic_read, odoo.generic_read_search, odoo.generic_read_details, odoo.document_search,
  odoo.document_details, odoo.document_details_by_id, odoo.product_price_update,
  odoo.generic_write_prepare: registered safe Odoo capabilities.

Use semantic intent, not exact prompt wording:
- Creative naming request for the application -> request_type creative_generation, domain knowledge, capability knowledge.creative_generation, requires_internal_context false.
- Question about Jamain Baco history/company facts -> enterprise_knowledge, knowledge.enterprise_answer, requires_internal_context true, topic preserved.
- Question such as "qu'est-ce qu'Odoo ?" -> general_knowledge, knowledge.general_answer.
- Odoo login/application access issue -> troubleshooting, support.troubleshooting.
- Odoo business data reads/writes -> enterprise_action with an Odoo capability.
- Bank statements, bank journals, and bank/accounting transaction reads -> odoo.accounting_bank_read.
- Supplier ranking/count questions over purchase orders -> odoo.purchase_supplier_ranking.
- Customer ranking/count questions over sales orders/commandes client -> odoo.sale_customer_ranking.
- Odoo connection/status/availability questions -> odoo.connection_status.
- Broad read-only Odoo business data questions that are not one of the specialized capabilities -> odoo.generic_read.
  Put the business object, optional installed model hint, operation, query, and limit in parameters.
- For time-bounded Odoo reads, put structured constraints in parameters.filters. Relative
  periods must use value {"type":"relative_period","period":"day|week|month|year","offset":0}
  with a safe date/datetime field name when known. Do not convert relative periods to
  fixed calendar dates.
- Missing required parameters -> set clarification_needed true and list missing_parameters.

If no registered capability fits, set capability to null and explain briefly.
Security-sensitive requests may be routed to security, but backend safety
blocking is authoritative.
"""


SEMANTIC_VALUE_SCHEMA = {
    "type": ["string", "number", "boolean", "null"],
}

SEMANTIC_FILTER_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "field": {"type": ["string", "null"]},
            "operator": {"type": ["string", "null"]},
            "value": {
                "anyOf": [
                    SEMANTIC_VALUE_SCHEMA,
                    {
                        "type": "object",
                        "properties": {
                            "type": {"type": ["string", "null"]},
                            "period": {"type": ["string", "null"]},
                            "offset": {"type": ["integer", "null"]},
                        },
                        "required": ["type", "period", "offset"],
                        "additionalProperties": False,
                    },
                ],
            },
        },
        "required": ["field", "operator", "value"],
        "additionalProperties": False,
    },
}

SEMANTIC_ENTITY_PROPERTIES = {
    "product_name": SEMANTIC_VALUE_SCHEMA,
    "document_type": SEMANTIC_VALUE_SCHEMA,
    "document_reference": SEMANTIC_VALUE_SCHEMA,
    "document_id": SEMANTIC_VALUE_SCHEMA,
    "partner_name": SEMANTIC_VALUE_SCHEMA,
    "field": SEMANTIC_VALUE_SCHEMA,
    "new_value": SEMANTIC_VALUE_SCHEMA,
    "target": SEMANTIC_VALUE_SCHEMA,
    "issue_type": SEMANTIC_VALUE_SCHEMA,
    "model": SEMANTIC_VALUE_SCHEMA,
    "record_id": SEMANTIC_VALUE_SCHEMA,
    "record_keyword": SEMANTIC_VALUE_SCHEMA,
    "operation": SEMANTIC_VALUE_SCHEMA,
    "business_object": SEMANTIC_VALUE_SCHEMA,
    "model_hint": SEMANTIC_VALUE_SCHEMA,
    "requested_fields": SEMANTIC_VALUE_SCHEMA,
    "filters": SEMANTIC_FILTER_SCHEMA,
    "limit": SEMANTIC_VALUE_SCHEMA,
    "knowledge_topic": SEMANTIC_VALUE_SCHEMA,
    "server_target": SEMANTIC_VALUE_SCHEMA,
}

SEMANTIC_PARAMETER_PROPERTIES = {
    "product_name": SEMANTIC_VALUE_SCHEMA,
    "document_type": SEMANTIC_VALUE_SCHEMA,
    "document_reference": SEMANTIC_VALUE_SCHEMA,
    "document_id": SEMANTIC_VALUE_SCHEMA,
    "partner_name": SEMANTIC_VALUE_SCHEMA,
    "field": SEMANTIC_VALUE_SCHEMA,
    "new_value": SEMANTIC_VALUE_SCHEMA,
    "new_price": SEMANTIC_VALUE_SCHEMA,
    "target": SEMANTIC_VALUE_SCHEMA,
    "issue_type": SEMANTIC_VALUE_SCHEMA,
    "model": SEMANTIC_VALUE_SCHEMA,
    "model_name": SEMANTIC_VALUE_SCHEMA,
    "record_id": SEMANTIC_VALUE_SCHEMA,
    "record_keyword": SEMANTIC_VALUE_SCHEMA,
    "keyword": SEMANTIC_VALUE_SCHEMA,
    "query": SEMANTIC_VALUE_SCHEMA,
    "operation": SEMANTIC_VALUE_SCHEMA,
    "business_object": SEMANTIC_VALUE_SCHEMA,
    "model_hint": SEMANTIC_VALUE_SCHEMA,
    "requested_fields": SEMANTIC_VALUE_SCHEMA,
    "filters": SEMANTIC_FILTER_SCHEMA,
    "limit": SEMANTIC_VALUE_SCHEMA,
    "knowledge_topic": SEMANTIC_VALUE_SCHEMA,
    "server_target": SEMANTIC_VALUE_SCHEMA,
    "metric": SEMANTIC_VALUE_SCHEMA,
}


OPENAI_ROUTER_SCHEMA = {
    "type": "json_schema",
    "name": "enterprise_semantic_route",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "request_type": {
                "type": "string",
                "enum": sorted(VALID_REQUEST_TYPES),
            },
            "domain": {
                "type": "string",
                "enum": sorted(VALID_DOMAINS),
            },
            "capability": {
                "type": ["string", "null"],
            },
            "requires_internal_context": {"type": "boolean"},
            "topic": {"type": ["string", "null"]},
            "entities": {
                "type": "object",
                "properties": SEMANTIC_ENTITY_PROPERTIES,
                "required": sorted(SEMANTIC_ENTITY_PROPERTIES),
                "additionalProperties": False,
            },
            "parameters": {
                "type": "object",
                "properties": SEMANTIC_PARAMETER_PROPERTIES,
                "required": sorted(SEMANTIC_PARAMETER_PROPERTIES),
                "additionalProperties": False,
            },
            "clarification_needed": {"type": "boolean"},
            "missing_parameters": {
                "type": "array",
                "items": {"type": "string"},
            },
            "confidence": {"type": "string", "enum": sorted(VALID_CONFIDENCE)},
            "reason": {"type": "string"},
        },
        "required": [
            "request_type",
            "domain",
            "capability",
            "requires_internal_context",
            "topic",
            "entities",
            "parameters",
            "clarification_needed",
            "missing_parameters",
            "confidence",
            "reason",
        ],
        "additionalProperties": False,
    },
}


def _router_model() -> str:
    return os.getenv("OPENAI_ROUTER_MODEL") or os.getenv("OPENAI_CLASSIFIER_MODEL") or "gpt-4.1-mini"


def _merge_entities_and_parameters(entities: dict, parameters: dict, topic: str | None):
    merged = {}

    if isinstance(entities, dict):
        merged.update(entities)

    if isinstance(parameters, dict):
        merged.update(parameters)

    if topic:
        merged.setdefault("knowledge_topic", topic)
        merged.setdefault("target", topic)

    return merged


def _is_odoo_read_semantic_route(parsed: dict) -> bool:
    if parsed.get("request_type") != "enterprise_action" or parsed.get("domain") != "odoo":
        return False

    entities = parsed.get("entities") if isinstance(parsed.get("entities"), dict) else {}
    parameters = parsed.get("parameters") if isinstance(parsed.get("parameters"), dict) else {}
    operation = str(parameters.get("operation") or entities.get("operation") or "").lower()
    field = parameters.get("field") or entities.get("field")
    new_value = (
        parameters.get("new_value")
        or parameters.get("new_price")
        or entities.get("new_value")
    )

    if operation in WRITE_OPERATIONS or field or new_value not in {None, ""}:
        return False

    if operation in READ_OPERATIONS:
        return True

    return bool(
        parameters.get("business_object")
        or entities.get("business_object")
        or parameters.get("query")
        or entities.get("record_keyword")
        or parsed.get("topic")
    )


def _semantic_values(parsed: dict) -> dict:
    values = {}

    for key in ("entities", "parameters"):
        source = parsed.get(key)

        if isinstance(source, dict):
            values.update(source)

    return values


def _semantic_text_signals(parsed: dict) -> set[str]:
    values = _semantic_values(parsed)
    signals = set()

    for key in (
        "metric",
        "operation",
        "requested_fields",
        "server_target",
        "target",
        "topic",
    ):
        value = values.get(key) if key != "topic" else parsed.get("topic")

        if isinstance(value, str):
            signals.update(part.strip().lower() for part in value.replace("_", " ").split())

    return {signal for signal in signals if signal}


def _semantic_text_blob(parsed: dict) -> str:
    values = _semantic_values(parsed)
    fragments = []

    for value in list(values.values()) + [parsed.get("topic"), parsed.get("capability")]:
        if isinstance(value, str):
            fragments.append(value)

    return " ".join(fragments).lower().replace("_", " ")


def _is_bank_accounting_semantic_route(parsed: dict) -> bool:
    if parsed.get("request_type") != "enterprise_action" or parsed.get("domain") != "odoo":
        return False

    values = _semantic_values(parsed)
    operation = str(values.get("operation") or "").strip().lower()
    field = values.get("field")
    new_value = values.get("new_value") or values.get("new_price")

    if operation in WRITE_OPERATIONS or field or new_value not in {None, ""}:
        return False

    blob = _semantic_text_blob(parsed)

    return any(term in blob for term in BANK_ACCOUNTING_SIGNAL_TERMS)


def _registered_capability_for_server_signal(signals: set[str]) -> str | None:
    for signal in sorted(signals):
        capability = SERVER_DIAGNOSTIC_CAPABILITY_BY_SIGNAL.get(signal)

        if not capability:
            continue

        metadata = get_capability_metadata(capability)

        if metadata and metadata.get("domain") == "server":
            return capability

    return None


def _normalize_server_domain_capability(parsed: dict) -> dict:
    domain = parsed.get("domain")
    capability = parsed.get("capability")

    if domain != "server" or capability != "server":
        return parsed

    signals = _semantic_text_signals(parsed)
    operation = str(_semantic_values(parsed).get("operation") or "").strip().lower()

    if parsed.get("request_type") in {"enterprise_knowledge", "general_knowledge"}:
        normalized = dict(parsed)
        normalized["domain"] = "knowledge"
        normalized["capability"] = (
            "knowledge.enterprise_answer"
            if parsed.get("request_type") == "enterprise_knowledge"
            else "knowledge.general_answer"
        )
        return normalized

    if operation in SERVER_KNOWLEDGE_OPERATIONS:
        normalized = dict(parsed)
        normalized["request_type"] = "general_knowledge"
        normalized["domain"] = "knowledge"
        normalized["capability"] = "knowledge.general_answer"
        return normalized

    capability = _registered_capability_for_server_signal(signals)

    if capability:
        normalized = dict(parsed)
        normalized["capability"] = capability
        return normalized

    if operation in SERVER_DIAGNOSTIC_OPERATIONS:
        normalized = dict(parsed)
        normalized["capability"] = "server.local_health"
        return normalized

    return parsed


def _documentation_summary_intent(parsed: dict) -> str | None:
    values = _semantic_values(parsed)
    operation = str(values.get("operation") or "").strip().lower()
    signals = _semantic_text_signals(parsed)
    has_summary_operation = operation in SERVER_KNOWLEDGE_OPERATIONS or bool(
        signals & SERVER_KNOWLEDGE_OPERATIONS
    )
    has_documentation_scope = bool(
        signals
        & {
            "documentation",
            "document",
            "manual",
            "manuel",
            "guide",
        }
    )

    if not has_summary_operation or not has_documentation_scope:
        return None

    if signals & {"server", "serveur", "serveurs"}:
        return "summarize_server_documentation"

    return "summarize_documentation"


def _unsupported_semantic_route(parsed: dict, reason: str) -> dict:
    request_type = parsed.get("request_type")
    domain = parsed.get("domain") if parsed.get("domain") in VALID_DOMAINS else "general"
    agent = DOMAIN_AGENT_MAP.get(domain, "general_agent")
    confidence = parsed.get("confidence")

    if confidence not in VALID_CONFIDENCE:
        confidence = "low"

    semantic_request = {
        "request_type": request_type if request_type in VALID_REQUEST_TYPES else "clarification",
        "domain": domain,
        "capability": parsed.get("capability"),
        "requires_internal_context": bool(parsed.get("requires_internal_context")),
        "topic": parsed.get("topic"),
        "entities": parsed.get("entities") if isinstance(parsed.get("entities"), dict) else {},
        "parameters": parsed.get("parameters") if isinstance(parsed.get("parameters"), dict) else {},
        "clarification_needed": bool(parsed.get("clarification_needed")),
        "missing_parameters": parsed.get("missing_parameters")
        if isinstance(parsed.get("missing_parameters"), list)
        else [],
        "semantic_source": "openai_structured",
    }

    return {
        "intent": "unsupported_capability",
        "request_type": semantic_request["request_type"],
        "domain": domain,
        "agent": agent,
        "selected_agent": agent,
        "action": "unsupported_capability",
        "target_system": domain,
        "risk_level": "low",
        "risk": "low",
        "requires_approval": False,
        "approval_required": False,
        "entities": _merge_entities_and_parameters(
            semantic_request["entities"],
            semantic_request["parameters"],
            semantic_request["topic"],
        ),
        "parameters": semantic_request["parameters"],
        "confidence": confidence,
        "reason": reason,
        "classifier_source": "openai_structured",
        "semantic_source": "openai_structured",
        "classifier_error": "capability_validation_failed",
        "semantic_request": semantic_request,
        "capability_validation_error": reason,
    }


def _normalize_semantic_route(parsed: dict) -> dict | None:
    parsed = _normalize_server_domain_capability(parsed)
    request_type = parsed.get("request_type")
    domain = parsed.get("domain")
    capability = parsed.get("capability")
    confidence = parsed.get("confidence")

    if request_type not in VALID_REQUEST_TYPES:
        return None

    if domain not in VALID_DOMAINS:
        return None

    if confidence not in VALID_CONFIDENCE:
        return None

    documentation_intent = _documentation_summary_intent(parsed)

    if documentation_intent and domain == "server":
        domain = "knowledge"
        capability = "knowledge.general_answer"
        parsed = dict(parsed)
        parsed["domain"] = domain
        parsed["capability"] = capability

    direct_knowledge_capability = {
        "conversational": "knowledge.general_answer",
        "creative_generation": "knowledge.creative_generation",
        "general_knowledge": "knowledge.general_answer",
        "writing_assistance": "knowledge.writing_assistance",
    }.get(request_type)

    if not capability and direct_knowledge_capability and domain in {"general", "knowledge"}:
        domain = "knowledge"
        capability = direct_knowledge_capability
        parsed = dict(parsed)
        parsed["domain"] = domain
        parsed["capability"] = capability

    if (
        capability
        in {
            "knowledge.creative_generation",
            "knowledge.general_answer",
            "knowledge.writing_assistance",
        }
        and domain == "general"
    ):
        domain = "knowledge"
        parsed = dict(parsed)
        parsed["domain"] = domain

    if (
        domain == "knowledge"
        and capability == "knowledge.writing_assistance"
        and _documentation_summary_intent(parsed)
    ):
        capability = "knowledge.general_answer"
        parsed = dict(parsed)
        parsed["capability"] = capability

    if _is_bank_accounting_semantic_route(parsed):
        capability = "odoo.accounting_bank_read"
        parsed = dict(parsed)
        parsed["capability"] = capability

    if not capability and _is_odoo_read_semantic_route(parsed):
        capability = "odoo.generic_read"
        parsed = dict(parsed)
        parsed["capability"] = capability

    if domain == "server" and not capability:
        capability = (
            _registered_capability_for_server_signal(_semantic_text_signals(parsed))
            or None
        )

        if not capability:
            operation = str(_semantic_values(parsed).get("operation") or "").strip().lower()

            if operation in SERVER_DIAGNOSTIC_OPERATIONS:
                capability = "server.local_health"

        if capability:
            parsed = dict(parsed)
            parsed["capability"] = capability

    if not capability:
        return _unsupported_semantic_route(
            parsed,
            "OpenAI understood the request, but did not select a registered capability.",
        )

    entities = parsed.get("entities") if isinstance(parsed.get("entities"), dict) else {}
    parameters = parsed.get("parameters") if isinstance(parsed.get("parameters"), dict) else {}
    selected_model = (
        parameters.get("model_name")
        or parameters.get("model")
        or entities.get("model")
        or entities.get("model_name")
    )

    if (
        domain == "odoo"
        and capability in {"odoo.generic_read_search", "odoo.generic_read_details"}
        and (
            parameters.get("business_object")
            or entities.get("business_object")
            or (selected_model and selected_model not in SAFE_ODOO_READ_MODELS)
        )
    ):
        capability = "odoo.generic_read"
        parsed = dict(parsed)
        parsed["capability"] = capability

    business_object_text = " ".join(
        str(value or "")
        for value in [
            parameters.get("business_object"),
            entities.get("business_object"),
            parameters.get("model"),
            entities.get("model"),
            parameters.get("model_name"),
            entities.get("model_name"),
        ]
    ).lower()
    product_object_terms = {
        "article",
        "articles",
        "inventaire",
        "inventory",
        "product",
        "products",
        "produit",
        "produits",
        "stock",
    }

    if (
        domain == "odoo"
        and capability == "odoo.product_search"
        and business_object_text.strip()
        and not any(term in business_object_text for term in product_object_terms)
    ):
        capability = "odoo.generic_read"
        parsed = dict(parsed)
        parsed["capability"] = capability

    capability_metadata = get_capability_metadata(str(capability))

    if not capability_metadata:
        return _unsupported_semantic_route(
            parsed,
            f"Capability is not registered: {capability}",
        )

    metadata_domain = capability_metadata.get("domain") or capability_metadata.get("system")

    if metadata_domain and metadata_domain != domain:
        return _unsupported_semantic_route(
            parsed,
            f"Capability {capability} does not belong to domain {domain}.",
        )

    topic = parsed.get("topic")
    merged_entities = _merge_entities_and_parameters(entities, parameters, topic)
    clarification_needed = bool(parsed.get("clarification_needed"))
    missing_parameters = parsed.get("missing_parameters")

    if not isinstance(missing_parameters, list):
        missing_parameters = []

    if metadata_domain == "server":
        clarification_needed = False
        missing_parameters = []

    if capability == "odoo.accounting_bank_read":
        clarification_needed = False
        missing_parameters = []

    semantic_request = {
        "request_type": request_type,
        "domain": domain,
        "capability": capability,
        "requires_internal_context": bool(parsed.get("requires_internal_context")),
        "topic": topic,
        "entities": entities,
        "parameters": parameters,
        "clarification_needed": clarification_needed,
        "missing_parameters": missing_parameters,
        "semantic_source": "openai_structured",
    }
    action = CAPABILITY_LEGACY_ACTIONS.get(capability, capability)
    intent = CAPABILITY_LEGACY_INTENTS.get(capability, request_type)
    route_intent = documentation_intent or INTENT_ALIASES.get(intent, intent)
    agent = DOMAIN_AGENT_MAP.get(domain, "general_agent")
    risk_level = capability_metadata.get("risk_level", "low")
    requires_approval = bool(capability_metadata.get("requires_approval"))

    return {
        "intent": route_intent,
        "request_type": request_type,
        "domain": domain,
        "capability": capability,
        "execution_mode": capability_metadata.get("execution_mode", "tool"),
        "agent": agent,
        "selected_agent": agent,
        "action": action,
        "target_system": domain,
        "risk_level": risk_level,
        "risk": risk_level,
        "requires_approval": requires_approval,
        "approval_required": requires_approval,
        "entities": merged_entities,
        "parameters": parameters,
        "clarification_needed": clarification_needed,
        "missing_parameters": missing_parameters,
        "confidence": confidence,
        "reason": str(parsed.get("reason") or "OpenAI semantic router selected this capability."),
        "classifier_source": "openai_structured",
        "semantic_source": "openai_structured",
        "classifier_error": None,
        "semantic_request": semantic_request,
    }


def _normalize_legacy_route(parsed: dict) -> dict | None:
    if not isinstance(parsed, dict):
        return None

    agent = parsed.get("agent")
    target_system = parsed.get("target_system")
    risk_level = parsed.get("risk_level")
    confidence = parsed.get("confidence")

    if agent not in VALID_AGENTS:
        return None

    if target_system not in VALID_TARGET_SYSTEMS:
        return None

    if risk_level not in VALID_RISK_LEVELS:
        return None

    if confidence not in VALID_CONFIDENCE:
        return None

    entities = parsed.get("entities")
    if not isinstance(entities, dict):
        entities = {}

    intent = INTENT_ALIASES.get(
        str(parsed.get("intent") or "general"),
        str(parsed.get("intent") or "general"),
    )

    return {
        "intent": intent,
        "agent": agent,
        "selected_agent": agent,
        "action": str(parsed.get("action") or "answer_question"),
        "target_system": target_system,
        "risk_level": risk_level,
        "risk": risk_level,
        "requires_approval": bool(parsed.get("requires_approval")),
        "approval_required": bool(parsed.get("requires_approval")),
        "entities": entities,
        "confidence": confidence,
        "reason": str(parsed.get("reason") or "OpenAI router selected this route."),
        "classifier_source": "openai_router",
        "classifier_error": None,
    }


def _normalize_route(parsed: dict) -> dict | None:
    if not isinstance(parsed, dict):
        return None

    if "request_type" in parsed or "capability" in parsed or "domain" in parsed:
        semantic_route = _normalize_semantic_route(parsed)

        if semantic_route:
            return semantic_route

    return _normalize_legacy_route(parsed)


def classify_with_openai_router(
    message: str,
    context_memory: dict | None = None,
    user_permissions: dict | None = None,
) -> dict | None:
    if not is_openai_configured():
        return None

    prompt = (
        f"{OPENAI_ROUTER_PROMPT}\n\n"
        f"Conversation/context memory:\n{context_memory or {}}\n\n"
        f"User role/permissions:\n{user_permissions or {}}\n\n"
        f"User request:\n{message}\n"
    )

    response = generate_structured_response(
        prompt=prompt,
        schema=OPENAI_ROUTER_SCHEMA,
        system_prompt=(
            "You are a safe enterprise routing classifier. Return only the "
            "requested JSON object. Never execute tools or reveal secrets."
        ),
        model=_router_model(),
    )

    if not response.get("success"):
        return None

    return _normalize_route(response.get("parsed"))
