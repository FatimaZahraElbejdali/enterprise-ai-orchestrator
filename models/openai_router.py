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

INTENT_ALIASES = {
    "server_documentation_summary": "summarize_server_documentation",
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
  odoo.generic_read, odoo.generic_read_search, odoo.generic_read_details, odoo.document_search,
  odoo.document_details, odoo.document_details_by_id, odoo.product_price_update,
  odoo.generic_write_prepare: registered safe Odoo capabilities.

Use semantic intent, not exact prompt wording:
- Creative naming request for the application -> request_type creative_generation, domain knowledge, capability knowledge.creative_generation, requires_internal_context false.
- Question about Jamain Baco history/company facts -> enterprise_knowledge, knowledge.enterprise_answer, requires_internal_context true, topic preserved.
- Question such as "qu'est-ce qu'Odoo ?" -> general_knowledge, knowledge.general_answer.
- Odoo login/application access issue -> troubleshooting, support.troubleshooting.
- Odoo business data reads/writes -> enterprise_action with an Odoo capability.
- Broad read-only Odoo business data questions that are not one of the specialized capabilities -> odoo.generic_read.
  Put the business object, optional installed model hint, operation, query, and limit in parameters.
- Missing required parameters -> set clarification_needed true and list missing_parameters.

If no registered capability fits, set capability to null and explain briefly.
Security-sensitive requests may be routed to security, but backend safety
blocking is authoritative.
"""


SEMANTIC_VALUE_SCHEMA = {
    "type": ["string", "number", "boolean", "null"],
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
    missing_parameters = parsed.get("missing_parameters")

    if not isinstance(missing_parameters, list):
        missing_parameters = []

    semantic_request = {
        "request_type": request_type,
        "domain": domain,
        "capability": capability,
        "requires_internal_context": bool(parsed.get("requires_internal_context")),
        "topic": topic,
        "entities": entities,
        "parameters": parameters,
        "clarification_needed": bool(parsed.get("clarification_needed")),
        "missing_parameters": missing_parameters,
        "semantic_source": "openai_structured",
    }
    action = CAPABILITY_LEGACY_ACTIONS.get(capability, capability)
    intent = CAPABILITY_LEGACY_INTENTS.get(capability, request_type)
    agent = DOMAIN_AGENT_MAP.get(domain, "general_agent")
    risk_level = capability_metadata.get("risk_level", "low")
    requires_approval = bool(capability_metadata.get("requires_approval"))

    return {
        "intent": INTENT_ALIASES.get(intent, intent),
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
        "clarification_needed": bool(parsed.get("clarification_needed")),
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
