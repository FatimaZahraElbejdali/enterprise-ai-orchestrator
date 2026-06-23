import json
import re
import unicodedata
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.odoo_agent import run as run_odoo_agent
from agents.support_agent import (
    is_odoo_access_issue,
    is_support_request,
    run as run_support_agent,
)
from agents.server_agent import (
    is_server_request,
    run as run_server_agent,
)
from integrations.odoo_connector import OdooConnector
from models.openai_adapter import (
    generate_response,
    get_openai_status,
    is_openai_configured,
)
from orchestrator.graph import process_request
from orchestrator.audit import log_request
from orchestrator.approval_store import (
    attach_execution_result,
    get_approvals,
    update_approval_status,
)
from orchestrator.conversation_memory import conversation_memory
from orchestrator.contextual_resolver import resolve_contextual_message
from orchestrator.tool_executor import execute_tool

load_dotenv()

app = FastAPI(
    title="Enterprise AI Orchestrator API",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://123.123.123.12:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

odoo = OdooConnector()

AUTHORIZED_ODOO_UPDATE_TOOLS = {
    "odoo_update_product_price",
    "odoo_update_analytic_boolean_field",
    "odoo_update_sale_order_line",
    "odoo_update_purchase_order_line",
    "odoo_update_invoice_line",
    "odoo_update_delivery_quantity",
    "odoo_update_document_partner",
    "odoo_update_document_date",
}

ODOO_APPROVAL_ACTIONS = {
    "change_price",
    "toggle_boolean_field",
    "update_document_line",
    "update_document_partner",
    "update_document_date",
}


class ChatRequest(BaseModel):
    message: str
    session_id: str = "demo-session"


class AITestRequest(BaseModel):
    message: str


DocumentEndpointType = Literal[
    "sale_order",
    "purchase_order",
    "invoice",
    "delivery",
]


def enrich_message_with_memory_context(message: str, resolved_context: dict):
    context_lines = []

    if resolved_context.get("product_name"):
        context_lines.append(
            f"Context: the referenced product is {resolved_context['product_name']}."
        )

    if resolved_context.get("product_id") is not None:
        context_lines.append(
            f"Context: the referenced product ID is {resolved_context['product_id']}."
        )

    if not context_lines:
        return message

    return f"{message}\n\n" + "\n".join(context_lines)


def extract_document_id_from_message(message: str):
    patterns = [
        r"Context:\s+the selected Odoo document ID is\s+(\d+)\b",
        r"\bdocument\s+id\s+(\d+)\b",
        r"\bid\s+du\s+document\s+(\d+)\b",
        r"\bid\s+document\s+(\d+)\b",
        r"\b(?:l['’]?)?id\s+(\d+)\b",
        r"\b(?:facture|invoice|bon\s+de\s+livraison|livraison|stock\s+picking|bon\s+de\s+commande|commande\s+fournisseur|purchase\s+order|sale\s+order)\s+id\s+(\d+)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)

        if match:
            return int(match.group(1))

    return None


def enrich_message_with_document_candidate(message: str, candidate: dict):
    context_lines = []

    if candidate.get("document_id") is not None:
        context_lines.append(
            f"Context: the selected Odoo document ID is {candidate['document_id']}."
        )

    if candidate.get("document_name"):
        context_lines.append(
            f"Context: the selected Odoo document name is {candidate['document_name']}."
        )

    if candidate.get("document_model"):
        context_lines.append(
            f"Context: the selected Odoo document model is {candidate['document_model']}."
        )

    if candidate.get("document_type"):
        context_lines.append(
            f"Context: the selected Odoo document type is {candidate['document_type']}."
        )

    if candidate.get("partner_name"):
        context_lines.append(
            f"Context: the selected Odoo document partner is {candidate['partner_name']}."
        )

    if not context_lines:
        return message

    return f"{message}\n\n" + "\n".join(context_lines)


def normalize_followup_text(message: str):
    normalized = unicodedata.normalize("NFKD", message or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().replace("’", "'").split())


def clarify_product_reference_message(message: str, resolved_context: dict):
    product_name = resolved_context.get("product_name")

    if not product_name:
        return message

    normalized = normalize_followup_text(message)
    has_price_update_reference = any(
        phrase in normalized
        for phrase in [
            "its price",
            "change its price",
            "son prix",
            "changer son prix",
            "modifier son prix",
        ]
    )

    price_match = re.search(
        r"(?:to|à|a)\s+(\d+(?:[.,]\d+)?)\s*(dh|dhs|mad|dirhams?)?",
        message,
        re.IGNORECASE,
    )

    if has_price_update_reference and price_match:
        price = price_match.group(1).replace(",", ".")
        currency = price_match.group(2) or "DH"

        return f"Change the price of {product_name} to {price} {currency.upper()}"

    if any(term in normalized for term in ["son stock", "its stock", "its quantity", "sa quantite"]):
        return f"Quel est le stock du produit {product_name} ?"

    if any(term in normalized for term in ["son prix", "its price"]):
        return f"Quel est le prix du produit {product_name} ?"

    if any(term in normalized for term in ["sa reference", "its reference"]):
        return f"Quelle est la référence interne du produit {product_name} ?"

    if any(
        term in normalized
        for term in [
            "ses details",
            "ses informations",
            "ses infos",
            "sa fiche",
            "its details",
            "its information",
            "its info",
            "ce produit",
            "cet article",
            "ce dernier",
            "celui-ci",
            "celui ci",
            "le produit",
            "l'article",
            "larticle",
        ]
    ):
        return f"Montre-moi les détails du produit {product_name}"

    if resolved_context.get("reference_type") == "product":
        return f"Montre-moi les détails du produit {product_name}"

    return message


def remember_chat_result(session_id: str, result):
    conversation_memory.update_from_result(session_id, result)
    print(
        "[conversation_memory:update]",
        {
            "session_id": session_id,
            "updated_memory_context": conversation_memory.get_safe_context(session_id),
        },
    )


def normalize_document_endpoint_response(
    document_type: str,
    query: str,
    result: dict,
    include_record: bool = True,
):
    result = result if isinstance(result, dict) else {}
    record = result.get("record")

    if not isinstance(record, dict):
        record = result.get("document") if isinstance(result.get("document"), dict) else None

    if not isinstance(record, dict) and result.get("record_id"):
        record = {
            "id": result.get("record_id"),
            "name": result.get("name"),
            "partner": result.get("partner"),
            "state": result.get("state"),
            "date": result.get("date"),
        }

    if isinstance(record, dict) and "lines" in result:
        record = {
            **record,
            "lines": result.get("lines") or [],
        }

    source = result.get("source")
    endpoint_success = bool(result.get("success")) or source == "real_odoo"

    response = {
        "success": endpoint_success,
        "type": document_type,
        "model": result.get("model") or "",
        "query": query,
        "found": bool(result.get("found")),
        "ambiguous": bool(result.get("ambiguous")),
        "candidates": result.get("candidates") or [],
        "message": result.get("message") or "",
    }

    if include_record:
        response["record"] = record or {}

    return response


def dispatch_document_search(document_type: str, query: str):
    if document_type == "sale_order":
        return odoo.search_sale_order(query)

    if document_type == "purchase_order":
        return odoo.search_purchase_order(query)

    if document_type == "invoice":
        return odoo.search_invoice(query)

    if document_type == "delivery":
        return odoo.search_delivery_order(query)

    raise HTTPException(status_code=400, detail="Unsupported document type")


def dispatch_document_details(document_type: str, query: str):
    if document_type == "sale_order":
        return odoo.get_sale_order_details(query)

    if document_type == "purchase_order":
        return odoo.get_purchase_order_details(query)

    if document_type == "invoice":
        return odoo.get_invoice_details(query)

    if document_type == "delivery":
        return odoo.get_delivery_order_details(query)

    raise HTTPException(status_code=400, detail="Unsupported document type")


def build_odoo_approval_tool_call(approval: dict):
    metadata = approval.get("metadata") or {}
    tool_name = metadata.get("tool_name")
    action = approval.get("action")

    if tool_name not in AUTHORIZED_ODOO_UPDATE_TOOLS:
        return None, {}, "Approval metadata does not contain an authorized Odoo update tool."

    def without_none(values: dict):
        return {
            key: value
            for key, value in values.items()
            if value is not None
        }

    if action == "change_price" and tool_name == "odoo_update_product_price":
        product_name = metadata.get("product_name") or approval.get("entity_name")
        requested_value = metadata.get("new_price")
        tool_kwargs = {
            "product_name": product_name,
            "new_price": requested_value,
        }

        if product_name is None or requested_value is None:
            return None, {}, "Approval metadata is missing product name or new price."

        return tool_name, without_none(tool_kwargs), None

    if action == "toggle_boolean_field" and tool_name == "odoo_update_analytic_boolean_field":
        record_query = metadata.get("record_query") or approval.get("entity_name")
        field_name = metadata.get("field_name")
        requested_value = metadata.get("new_value")
        tool_kwargs = {
            "record_query": record_query,
            "field_name": field_name,
            "new_value": requested_value,
        }

        if record_query is None or field_name is None or requested_value is None:
            return None, {}, "Approval metadata is missing analytic account, field name, or requested value."

        return tool_name, without_none(tool_kwargs), None

    if action == "update_document_line":
        document_query = metadata.get("document_query")
        document_id = metadata.get("document_id")
        partner_name = metadata.get("partner_name")
        product_query = metadata.get("product_query")
        field_name = metadata.get("field_name")
        new_value = metadata.get("new_value")

        if tool_name == "odoo_update_sale_order_line":
            tool_kwargs = {
                "order_query": document_query,
                "product_query": product_query,
                "field": field_name,
                "new_value": new_value,
                "document_id": document_id,
                "partner_name": partner_name,
            }
        elif tool_name == "odoo_update_purchase_order_line":
            tool_kwargs = {
                "order_query": document_query,
                "product_query": product_query,
                "field": field_name,
                "new_value": new_value,
                "document_id": document_id,
                "partner_name": partner_name,
            }
        elif tool_name == "odoo_update_invoice_line":
            tool_kwargs = {
                "invoice_query": document_query,
                "product_query": product_query,
                "field": field_name,
                "new_value": new_value,
                "document_id": document_id,
                "partner_name": partner_name,
            }
        elif tool_name == "odoo_update_delivery_quantity":
            tool_kwargs = {
                "picking_query": document_query,
                "product_query": product_query,
                "new_quantity": new_value,
                "document_id": document_id,
                "partner_name": partner_name,
            }
        else:
            return None, {}, "Approval metadata does not match the requested document line action."

        if (
            document_query is None
            and document_id is None
            or product_query is None
            or field_name is None
            or new_value is None
        ):
            return None, {}, "Approval metadata is missing document, product, field, or requested value."

        return tool_name, without_none(tool_kwargs), None

    if action == "update_document_partner" and tool_name == "odoo_update_document_partner":
        partner_query = metadata.get("partner_query") or metadata.get("new_value")
        tool_kwargs = {
            "model_name": metadata.get("target_model"),
            "document_query": metadata.get("document_query"),
            "partner_query": partner_query,
            "document_id": metadata.get("document_id"),
            "current_partner_name": metadata.get("current_partner_name"),
        }

        if (
            tool_kwargs["model_name"] is None
            or (
                tool_kwargs["document_query"] is None
                and tool_kwargs["document_id"] is None
            )
            or partner_query is None
        ):
            return None, {}, "Approval metadata is missing document model, document reference, or partner."

        return tool_name, without_none(tool_kwargs), None

    if action == "update_document_date" and tool_name == "odoo_update_document_date":
        new_date = metadata.get("new_date") or metadata.get("new_value")
        tool_kwargs = {
            "model_name": metadata.get("target_model"),
            "document_query": metadata.get("document_query"),
            "date_field": metadata.get("date_field") or metadata.get("field_name"),
            "new_date": new_date,
            "document_id": metadata.get("document_id"),
            "partner_name": metadata.get("partner_name"),
        }

        if (
            tool_kwargs["model_name"] is None
            or (
                tool_kwargs["document_query"] is None
                and tool_kwargs["document_id"] is None
            )
            or tool_kwargs["date_field"] is None
            or new_date is None
        ):
            return None, {}, "Approval metadata is missing document model, document reference, date field, or new date."

        return tool_name, without_none(tool_kwargs), None

    return None, {}, "Approval action does not match an authorized Odoo update tool."


def is_odoo_related(message: str) -> bool:
    if is_odoo_access_issue(message):
        return False

    text = message.lower()
    normalized = (
        text.replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace("’", "'")
    )

    odoo_reference_patterns = [
        r"\bdocument\s+id\s+\d+\b",
        r"\bid\s+du\s+document\s+\d+\b",
        r"\bid\s+document\s+\d+\b",
        r"\bd[ée]tails?\s+du\s+document\s+id\s+\d+\b",
        r"\bdetails?\s+of\s+document\s+id\s+\d+\b",
        r"\b[a-z]{2,5}[-/][a-z0-9][a-z0-9/-]*\d{3,}\b",
        r"\bfac/\d{4}/\d+\b",
        r"\bfnp/\d{4}/\d+\b",
        r"\bbc-[a-z0-9-]+\b",
        r"\bol-[a-z0-9-]+\b",
        r"\bwh/(?:out|in|pick)/\d+\b",
    ]

    if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in odoo_reference_patterns):
        return True

    keywords = [
        "baco",
        "stock",
        "inventory",
        "inventaire",
        "product",
        "produit",
        "price",
        "prix",
        "unit",
        "unité",
        "unite",
        "invoice",
        "facture",
        "customer",
        "client",
        "purchase",
        "achat",
        "commande",
        "sale order",
        "purchase order",
        "quotation",
        "quote",
        "delivery",
        "livraison",
        "supplier",
        "fournisseur",
        "fournisseurs",
        "bon fournisseur",
        "bon de commande",
        "commande fournisseur",
        "bon de livraison",
        "document id",
        "id document",
        "id du document",
        "stock picking",
        "devis",
        "arrivée prévue",
        "arrivee prevue",
        "date d'arrivée",
        "date d'arrivee",
        "date de réception",
        "date de reception",
        "cocher",
        "décocher",
        "decocher",
        "dotation",
        "pointage",
        "résilier",
        "resilier",
        "analytique",
        "analytic",
    ]

    return any(keyword in text or keyword in normalized for keyword in keywords)


def build_direct_support_response(message: str):
    agent_result = run_support_agent(message)
    result = agent_result.get("result") if isinstance(agent_result, dict) else None
    support_message = agent_result.get("response") or agent_result.get("message")

    if not support_message and isinstance(result, dict):
        support_message = result.get("message")

        if not support_message and isinstance(result.get("steps"), list):
            support_message = "Étapes à vérifier : " + "; ".join(
                str(step) for step in result["steps"]
            )

        if not support_message and isinstance(result.get("suggested_steps"), list):
            support_message = "Étapes à vérifier : " + "; ".join(
                str(step) for step in result["suggested_steps"]
            )

    if not support_message:
        support_message = "Demande support traitée."

    log_request({
        "event_type": "support_request",
        "system": "support",
        "agent": "support_agent",
        "status": "completed",
        "risk": "low",
        "approval_status": "not_required",
        "user_message": message,
        "action": agent_result.get("parsed_action") if isinstance(agent_result, dict) else "troubleshoot_issue",
        "message": "Support troubleshooting response generated.",
    })

    return {
        "intent": "support",
        "agent": "support_agent",
        "selected_agent": "support_agent",
        "risk": "low",
        "risk_level": "low",
        "selected_model": {
            "provider": "local_fallback",
            "model": "support_fallback",
            "reason": "Direct support route selected by local policy.",
        },
        "requires_approval": False,
        "approval_required": False,
        "approval_status": "not_required",
        "status": "completed",
        "message": support_message,
        "parser_source": agent_result.get("parser_source", "support_fallback") if isinstance(agent_result, dict) else "support_fallback",
        "parsed_action": agent_result.get("parsed_action", "troubleshoot_issue") if isinstance(agent_result, dict) else "troubleshoot_issue",
        "tool_used": agent_result.get("tool_used") if isinstance(agent_result, dict) else None,
        "agent_result": agent_result,
        "result": result,
    }


def build_direct_server_response(message: str):
    agent_result = run_server_agent(message)
    result = agent_result.get("result") if isinstance(agent_result, dict) else None

    log_request({
        "event_type": "server_request",
        "system": "internal_server",
        "agent": "server_agent",
        "status": agent_result.get("status", "completed") if isinstance(agent_result, dict) else "completed",
        "risk": "low",
        "approval_status": "not_required",
        "user_message": message,
        "action": agent_result.get("parsed_action") if isinstance(agent_result, dict) else "unknown",
        "message": "Internal server demo action handled by local policy.",
    })

    return {
        "intent": "server",
        "agent": "server_agent",
        "selected_agent": "server_agent",
        "risk": "low",
        "risk_level": "low",
        "selected_model": {
            "provider": "local_fallback",
            "model": "server_fallback",
            "reason": "Direct server route selected by local policy.",
        },
        "requires_approval": False,
        "approval_required": False,
        "approval_status": "not_required",
        "status": agent_result.get("status", "completed") if isinstance(agent_result, dict) else "completed",
        "message": agent_result.get("message") if isinstance(agent_result, dict) else str(agent_result),
        "parser_source": agent_result.get("parser_source", "server_fallback") if isinstance(agent_result, dict) else "server_fallback",
        "parsed_action": agent_result.get("parsed_action", "unknown") if isinstance(agent_result, dict) else "unknown",
        "tool_used": agent_result.get("tool_used") if isinstance(agent_result, dict) else None,
        "agent_result": agent_result,
        "result": result,
    }


@app.get("/")
def home():
    return {
        "message": "Enterprise AI Orchestrator API is running",
        "status": "online",
    }


@app.get("/status")
def status():
    return {
        "status": "online",
        "service": "Enterprise AI Orchestrator",
        "version": "0.2.0",
        "features": {
            "intent_classification": True,
            "agent_routing": True,
            "model_routing": True,
            "audit_logging": True,
            "approval_detection": True,
            "approval_storage": True,
            "real_model_apis": is_openai_configured(),
            "odoo_connector": True,
            "odoo_real_integration": True,
            "sensitive_action_blocking": True,
        },
    }


@app.get("/ai/providers")
def ai_providers():
    openai_status = get_openai_status()

    return {
        "openai": openai_status,
        "default_provider": "openai" if openai_status["configured"] else "mock",
    }


@app.post("/ai/test")
def ai_test(request: AITestRequest):
    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty",
        )

    if not is_openai_configured():
        status_info = get_openai_status()

        return {
            "provider": "openai",
            "model": status_info["model"],
            "success": False,
            "content": "",
            "error": "missing_api_key",
            "status": status_info["status"],
        }

    response = generate_response(
        prompt=message,
        system_prompt=(
            "You are testing the Enterprise AI Orchestrator OpenAI provider. "
            "Reply briefly and do not execute any enterprise action."
        ),
    )

    log_request({
        "event_type": "ai_model_call",
        "provider": "openai",
        "model": response.get("model"),
        "agent": "general_agent",
        "status": "completed" if response.get("success") else "failed",
        "risk": "low",
        "approval_status": "not_required",
    })

    return response


@app.post("/chat")
def chat(request: ChatRequest):
    original_message = request.message
    message = original_message.strip()
    session_id = request.session_id or "demo-session"

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty",
        )

    memory_context = conversation_memory.get_safe_context(session_id)
    contextual_resolution = resolve_contextual_message(message, memory_context)
    enriched_message = contextual_resolution.get("resolved_message") or message

    if (
        contextual_resolution.get("confidence") == "low"
        and contextual_resolution.get("used_memory") is not True
    ):
        fallback_context = conversation_memory.resolve_references(message, session_id)

        if fallback_context:
            clarified_message = clarify_product_reference_message(message, fallback_context)
            enriched_message = enrich_message_with_memory_context(
                clarified_message,
                fallback_context,
            )
            contextual_resolution = {
                "original_message": original_message,
                "resolved_message": enriched_message,
                "used_memory": True,
                "resolved_references": fallback_context,
                "confidence": "medium",
            }

    print(
        "[contextual_resolver]",
        {
            "session_id": session_id,
            "original_message": original_message,
            "resolved_message": enriched_message,
            "used_memory": contextual_resolution.get("used_memory"),
            "confidence": contextual_resolution.get("confidence"),
            "resolved_references": contextual_resolution.get("resolved_references"),
            "enriched_message": enriched_message,
        },
    )

    resolved_references = contextual_resolution.get("resolved_references")
    resolved_document_context_applied = False

    if (
        isinstance(resolved_references, dict)
        and resolved_references.get("reference_type") == "document"
    ):
        enriched_message = enrich_message_with_document_candidate(
            enriched_message,
            resolved_references,
        )
        resolved_document_context_applied = True

    document_id = extract_document_id_from_message(enriched_message)

    if document_id is not None and not resolved_document_context_applied:
        document_candidate = conversation_memory.resolve_document_candidate(
            session_id,
            document_id,
        )

        if document_candidate:
            enriched_message = enrich_message_with_document_candidate(
                enriched_message,
                document_candidate,
            )
            print(
                "[conversation_memory:document_candidate]",
                {
                    "session_id": session_id,
                    "document_id": document_id,
                    "resolved_candidate": document_candidate,
                },
            )

    if is_support_request(enriched_message):
        result = build_direct_support_response(enriched_message)
        remember_chat_result(session_id, result)
        return result

    if is_server_request(enriched_message):
        result = build_direct_server_response(enriched_message)
        remember_chat_result(session_id, result)
        return result

    if is_odoo_related(enriched_message):
        odoo_result = run_odoo_agent(enriched_message)

        if isinstance(odoo_result, dict):
            odoo_result.setdefault("agent", "odoo_agent")
            odoo_result.setdefault("selected_agent", odoo_result.get("agent", "odoo_agent"))
            odoo_result.setdefault("selected_model", {
                "provider": "mock",
                "model": "policy_engine",
                "reason": "Odoo actions are controlled by local policy and approval rules.",
            })
            odoo_result.setdefault("agent_result", {
                "agent": odoo_result.get("agent", "odoo_agent"),
                "tool_used": odoo_result.get("tool_used"),
                "result": odoo_result.get("result") or odoo_result.get("data"),
            })

        remember_chat_result(session_id, odoo_result)
        return odoo_result

    result = process_request(enriched_message)
    remember_chat_result(session_id, result)
    return result


@app.get("/debug/conversation/{session_id}")
def debug_conversation(session_id: str):
    return conversation_memory.get_safe_context(session_id)


@app.get("/debug/routes")
def debug_routes():
    return sorted(route.path for route in app.routes)


@app.get("/logs")
def get_logs():
    log_path = Path("logs/audit_log.jsonl")

    if not log_path.exists():
        return []

    logs = []

    with open(log_path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(entry, dict):
                continue

            title = entry.get("title")
            message = entry.get("message")

            if title == "string" or message == "string":
                continue

            logs.append(entry)

    return sorted(
        logs,
        key=lambda item: item.get("timestamp", ""),
        reverse=True,
    )


@app.get("/approvals")
def approvals():
    return get_approvals()


@app.post("/approvals/{approval_id}/approve")
def approve_approval(approval_id: str):
    current_approval = next(
        (
            item
            for item in get_approvals()
            if item.get("id") == approval_id
        ),
        None,
    )

    if current_approval is None:
        raise HTTPException(
            status_code=404,
            detail="Approval not found",
        )

    if current_approval.get("status") == "approved" and current_approval.get("executed"):
        return current_approval

    approval = update_approval_status(approval_id, "approved")

    if approval is None:
        raise HTTPException(
            status_code=404,
            detail="Approval not found",
        )

    log_request({
        "event_type": "approval_decision",
        "title": "Demande approuvée",
        "system": approval.get("source_system", "orchestrator"),
        "agent": approval.get("selected_agent", "orchestrator"),
        "status": "approved",
        "risk": approval.get("risk", "medium"),
        "approval_status": "approved",
        "approval_id": approval.get("id"),
        "user_message": approval.get("user_message"),
        "action": approval.get("action"),
        "product": approval.get("entity_name"),
        "requested_value": approval.get("requested_change"),
        "executed": approval.get("executed", False),
        "message": "La demande a été approuvée. L’exécution contrôlée peut démarrer si un outil autorisé est configuré.",
    })

    if approval.get("source_system") == "odoo" and approval.get("action") in ODOO_APPROVAL_ACTIONS:
        metadata = approval.get("metadata") or {}
        action = approval.get("action")
        product_name = (
            metadata.get("product_name")
            or metadata.get("record_query")
            or metadata.get("document_query")
            or (
                f"ID {metadata.get('document_id')}"
                if metadata.get("document_id") is not None
                else None
            )
            or approval.get("entity_name")
        )
        requested_value = (
            metadata.get("new_price")
            if action == "change_price"
            else metadata.get("new_value")
        )
        tool_name, tool_kwargs, tool_error = build_odoo_approval_tool_call(approval)

        if tool_error:
            execution_result = {
                "success": False,
                "source": "orchestrator",
                "action": action,
                "product": product_name,
                "document": metadata.get("document_query"),
                "document_id": metadata.get("document_id"),
                "partner_name": metadata.get("partner_name"),
                "product_id": None,
                "old_price": None,
                "requested_price": requested_value if action == "change_price" else None,
                "new_price": None,
                "requested_value": requested_value,
                "executed": False,
                "verified": False,
                "found": False,
                "message": tool_error,
            }
        else:
            tool_response = execute_tool(
                tool_name,
                **tool_kwargs,
            )
            execution_result = (
                tool_response.get("result")
                if isinstance(tool_response, dict) and "result" in tool_response
                else tool_response
            )

        if not isinstance(execution_result, dict):
            execution_result = {
                "success": False,
                "source": "orchestrator",
                "action": action,
                "product": product_name,
                "document": metadata.get("document_query"),
                "document_id": metadata.get("document_id"),
                "partner_name": metadata.get("partner_name"),
                "executed": False,
                "verified": False,
                "found": False,
                "message": "Tool executor returned an invalid response.",
            }

        verified = (
            execution_result.get("success") is True
            and execution_result.get("verified") is True
        )
        updated_approval = attach_execution_result(
            approval_id=approval_id,
            execution_result=execution_result,
        )

        log_request({
            "event_type": "odoo_write_executed",
            "title": (
                "Prix produit modifié dans Odoo"
                if action == "change_price"
                else "Champ analytique modifié dans Odoo"
                if action == "toggle_boolean_field"
                else "Document Odoo modifié"
            ),
            "system": "odoo",
            "agent": "odoo_agent",
            "status": "completed" if verified else "failed",
            "risk": approval.get("risk", "medium"),
            "approval_status": "approved",
            "approval_id": approval.get("id"),
            "user_message": approval.get("user_message"),
            "action": action,
            "product": product_name,
            "document": metadata.get("document_query"),
            "document_id": metadata.get("document_id"),
            "partner_name": metadata.get("partner_name"),
            "field": metadata.get("field_name"),
            "requested_value": requested_value,
            "executed": bool(
                execution_result.get("executed")
                and execution_result.get("verified")
            ),
            "execution_result": execution_result,
            "message": execution_result.get("message"),
        })

        return updated_approval or approval

    return approval


@app.post("/approvals/{approval_id}/reject")
def reject_approval(approval_id: str):
    approval = update_approval_status(approval_id, "rejected")

    if approval is None:
        raise HTTPException(
            status_code=404,
            detail="Approval not found",
        )

    log_request({
        "event_type": "approval_decision",
        "title": "Demande rejetée",
        "system": approval.get("source_system", "orchestrator"),
        "agent": approval.get("selected_agent", "orchestrator"),
        "status": "rejected",
        "risk": approval.get("risk", "medium"),
        "approval_status": "rejected",
        "approval_id": approval.get("id"),
        "user_message": approval.get("user_message"),
        "action": approval.get("action"),
        "product": approval.get("entity_name"),
        "requested_value": approval.get("requested_change"),
        "executed": False,
        "message": "La demande a été rejetée. Aucune modification Odoo n’a été exécutée.",
    })

    return approval


@app.get("/odoo/status")
def odoo_status():
    return odoo.test_connection()


@app.get("/odoo/stock/{product_name}")
def odoo_stock(product_name: str):
    return odoo.check_stock(product_name)


@app.get("/odoo/product/{product_name}")
def odoo_product(product_name: str):
    return odoo.check_stock(product_name)


@app.get("/odoo/product-search/{query}")
def odoo_product_search(query: str):
    return odoo.search_product_templates_for_debug(query)


@app.get("/odoo/product-by-id/{product_id}")
def odoo_product_by_id(product_id: int):
    return odoo.get_product_template_by_id(product_id)


@app.get("/odoo/analytic-fields")
def odoo_analytic_fields():
    return odoo.get_analytic_boolean_fields()


@app.get("/odoo/document/search")
def odoo_document_search(
    document_type: DocumentEndpointType = Query(..., alias="type"),
    query: str = Query(..., min_length=1),
):
    result = dispatch_document_search(document_type, query)
    return normalize_document_endpoint_response(
        document_type,
        query,
        result,
        include_record=False,
    )


@app.get("/odoo/document/details")
def odoo_document_details(
    document_type: DocumentEndpointType = Query(..., alias="type"),
    query: str = Query(..., min_length=1),
):
    result = dispatch_document_details(document_type, query)
    return normalize_document_endpoint_response(document_type, query, result)
