import json
import re
import unicodedata
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
from agents.knowledge_agent import run as run_knowledge_agent
from integrations.odoo_connector import OdooConnector
from models.openai_adapter import (
    generate_response,
    get_openai_status,
    is_openai_configured,
)
from orchestrator.graph import process_request
from orchestrator.classifier_router import classify_message
from orchestrator.audit import (
    LOG_PATH as AUDIT_LOG_PATH,
    is_important_audit_event,
    log_request,
)
from orchestrator.auth import (
    ACCESS_DENIED_MESSAGE,
    INVALID_CREDENTIALS_MESSAGE,
    access_denied_payload,
    authenticate_demo_user,
    check_chat_permission,
    get_current_user,
    require_any_permission,
    require_permission,
    reset_audit_user_context,
    set_audit_user_context,
    unsupported_action_payload,
)
from orchestrator.approval_store import (
    attach_execution_result,
    get_approvals,
    update_approval_status,
)
from orchestrator.conversation_memory import conversation_memory
from orchestrator.contextual_resolver import resolve_contextual_message
from orchestrator.tool_executor import execute_tool
from orchestrator.permission_policy import resolve_route_permission
from orchestrator.tool_registry import get_capability_metadata, get_tool_metadata
from orchestrator.department_profiles import (
    DEPARTMENT_ACCESS_DENIED_MESSAGE,
    get_department_profile,
    is_route_allowed_for_department,
)
from orchestrator.official_web_ingestion import (
    OfficialWebIngestionError,
    OfficialWebsiteIngestionService,
)

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
    "odoo_update_field",
}

ODOO_APPROVAL_ACTIONS = {
    "change_price",
    "toggle_boolean_field",
    "update_document_line",
    "update_document_partner",
    "update_document_date",
    "odoo_update_field_request",
}

ODOO_READ_OPERATION_VALUES = {
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

ODOO_WRITE_OPERATION_VALUES = {
    "approve",
    "assign",
    "cancel",
    "change",
    "confirm",
    "create",
    "delete",
    "modify",
    "remove",
    "set",
    "unlink",
    "update",
    "validate",
    "write",
}


class ChatRequest(BaseModel):
    message: str
    session_id: str = "demo-session"


class AITestRequest(BaseModel):
    message: str


class LoginRequest(BaseModel):
    email: str
    password: str


class OfficialWebIngestRequest(BaseModel):
    url: str
    scope: str = "company_common"
    crawl: bool = True
    max_pages: int = 20
    max_depth: int = 2


class PublicSource(BaseModel):
    source_type: str | None = None
    title: str | None = None
    url: str | None = None
    label: str | None = None


class ChatTechnicalMetadata(BaseModel):
    intent: str | None = None
    request_type: str | None = None
    domain: str | None = None
    agent: str | None = None
    capability: str | None = None
    execution_mode: str | None = None
    action: str | None = None
    risk: str | None = None
    approval_status: str | None = None
    parser_source: str | None = None
    tool_used: str | None = None
    provider: str | None = None
    model: str | None = None
    llm_success: bool | None = None
    llm_error: str | None = None
    permission_decision: str | None = None
    department: str | None = None
    target_system: str | None = None
    odoo_model: str | None = None
    record_count: int | None = None
    selected_model: str | None = None
    candidate_models: list[str] | None = None
    fields_used: list[str] | None = None
    domain_used: list | None = None
    count_returned: int | None = None
    failure_reason: str | None = None
    aggregation_field: str | None = None
    odoo_method: str | None = None
    odoo_tool_steps: list[dict] | None = None
    final_odoo_model: str | None = None
    final_record_count: int | None = None
    retrieval_query: str | None = None
    classifier_source: str | None = None
    semantic_source: str | None = None
    knowledge_scopes: list[str] = Field(default_factory=list)
    approval_action: str | None = None
    approval_entity: str | None = None
    approval_requested_change: str | None = None
    memory_context_used: bool | None = None
    resolved_from_previous_model: str | None = None
    resolved_business_object: str | None = None
    follow_up_limit: int | None = None
    pending_context_used: bool | None = None
    pending_context_type: str | None = None
    original_request: str | None = None
    merged_request: str | None = None
    merged_parameters: dict | None = None
    cleared_pending_context: bool | None = None
    pending_context_cleared: bool | None = None


class PublicChatResponse(BaseModel):
    status: str
    response: str
    requires_approval: bool
    approval_id: str | None = None
    sources: list[PublicSource] = Field(default_factory=list)
    technical: ChatTechnicalMetadata = Field(default_factory=ChatTechnicalMetadata)


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


def user_permission_context(current_user: dict):
    return {
        "email": current_user.get("email"),
        "role": current_user.get("role"),
        "department": current_user.get("department"),
        "permissions": current_user.get("permissions", []),
        "department_profile": get_department_profile(
            current_user.get("department"),
        ).to_public_dict(),
    }


def result_needs_clarification(result: dict) -> bool:
    if not isinstance(result, dict):
        return False

    return (
        result.get("status") == "needs_clarification"
        or result.get("clarification_needed") is True
        or result.get("needs_clarification") is True
    )


def build_pending_clarification_state(
    session_id: str,
    original_request: str,
    resolved_request: str,
    classification: dict | None,
    result: dict | None,
):
    classification = classification or {}
    result = result or {}
    missing = (
        result.get("missing_parameters")
        or classification.get("missing_parameters")
        or []
    )

    if not isinstance(missing, list):
        missing = []

    return {
        "session_id": session_id,
        "original_request": original_request,
        "resolved_request": resolved_request,
        "classification": classification,
        "result": result,
        "missing_parameters": missing,
    }


def store_pending_clarification(
    session_id: str,
    original_request: str,
    resolved_request: str,
    classification: dict | None,
    result: dict | None,
):
    if not result_needs_clarification(result or {}):
        return

    conversation_memory.set_pending_clarification(
        session_id,
        build_pending_clarification_state(
            session_id,
            original_request,
            resolved_request,
            classification,
            result,
        ),
    )


def result_suggests_pending_task(result: dict) -> bool:
    if not isinstance(result, dict):
        return False

    status = str(result.get("status") or "").lower()
    agent = result.get("agent") or result.get("selected_agent")
    target_system = result.get("target_system")
    domain = result.get("domain")

    if status not in {"not_found", "no_results"}:
        return False

    if result.get("requires_approval") or result.get("approval_required"):
        return False

    return agent == "odoo_agent" or target_system == "odoo" or domain == "odoo"


def build_pending_task_state(
    session_id: str,
    original_request: str,
    resolved_request: str,
    classification: dict | None,
    result: dict | None,
):
    classification = classification or {}
    result = result or {}

    return {
        "session_id": session_id,
        "context_type": "retry_suggestion",
        "original_request": original_request,
        "resolved_request": resolved_request,
        "classification": classification,
        "result": result,
        "reason": result.get("status") or "no_result",
        "suggested_next_action": "retry_with_broader_or_adjusted_read_criteria",
    }


def store_pending_task(
    session_id: str,
    original_request: str,
    resolved_request: str,
    classification: dict | None,
    result: dict | None,
):
    if not result_suggests_pending_task(result or {}):
        return

    conversation_memory.set_pending_task(
        session_id,
        build_pending_task_state(
            session_id,
            original_request,
            resolved_request,
            classification,
            result,
        ),
    )


def _classification_is_security_sensitive(classification: dict) -> bool:
    if not isinstance(classification, dict):
        return False

    return (
        classification.get("selected_agent") == "security_agent"
        or classification.get("agent") == "security_agent"
        or classification.get("risk") == "blocked"
        or classification.get("risk_level") == "blocked"
        or classification.get("status") == "blocked"
        or classification.get("action") in {"blocked_sensitive_path", "security_blocked"}
    )


def _classification_domain(classification: dict) -> str:
    return str(classification.get("domain") or classification.get("target_system") or "").lower()


def _pending_domain(pending: dict) -> str:
    return str(pending.get("domain") or pending.get("target_system") or "").lower()


def _looks_like_standalone_question(message: str) -> bool:
    normalized = normalize_followup_text(message)
    tokens = normalized.split()

    if "?" in message and len(tokens) > 3:
        return True

    question_leads = {
        "what",
        "why",
        "how",
        "when",
        "where",
        "who",
        "which",
        "quoi",
        "pourquoi",
        "comment",
        "quand",
        "ou",
        "qui",
        "quel",
        "quelle",
        "quels",
        "quelles",
        "explique",
        "expliquer",
        "raconte",
        "resume",
        "résume",
    }

    return bool(tokens and tokens[0] in question_leads and len(tokens) > 3)


def _looks_like_backend_action(classification: dict) -> bool:
    if not isinstance(classification, dict):
        return False

    request_type = str(classification.get("request_type") or "").lower()
    capability = str(classification.get("capability") or "").lower()
    action = str(classification.get("action") or "").lower()

    return (
        request_type == "enterprise_action"
        or bool(capability and capability not in {"knowledge.general_answer"})
        or action in ODOO_WRITE_OPERATION_VALUES
    )


def _token_set(value: str) -> set[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "avec",
        "ce",
        "ces",
        "de",
        "des",
        "du",
        "en",
        "for",
        "from",
        "i",
        "j",
        "je",
        "la",
        "le",
        "les",
        "me",
        "moi",
        "of",
        "on",
        "sur",
        "the",
        "to",
        "un",
        "une",
    }

    return {
        token
        for token in normalize_followup_text(value).replace("-", " ").split()
        if len(token) > 2 and token not in stopwords
    }


def _pending_context_text(pending: dict) -> str:
    fragments = [
        pending.get("original_request"),
        pending.get("resolved_request"),
        pending.get("capability"),
        pending.get("action"),
        pending.get("intent"),
        pending.get("target_system"),
        pending.get("suggested_next_action"),
    ]

    for key in ("entities", "parameters"):
        value = pending.get(key)

        if isinstance(value, dict):
            fragments.extend(str(item) for item in value.values() if item not in {None, ""})

    return " ".join(str(fragment) for fragment in fragments if fragment)


def _looks_like_confirmation_or_reference(message: str, pending: dict) -> bool:
    normalized = normalize_followup_text(message)
    tokens = _token_set(message)

    if not tokens:
        return False

    confirmation_markers = {
        "yes",
        "yeah",
        "yep",
        "ok",
        "okay",
        "daccord",
        "oui",
        "continue",
        "proceed",
        "go",
        "fais",
        "faire",
        "cherche",
        "recherche",
        "autrement",
        "different",
        "different",
        "autre",
        "criteres",
        "critere",
        "broader",
        "elargis",
        "elargir",
    }
    reference_markers = {
        "asked",
        "requested",
        "previous",
        "avant",
        "demande",
        "demandee",
        "demandes",
        "mentionne",
        "precedent",
        "precedente",
        "celui",
        "celle",
        "ceux",
    }
    pending_tokens = _token_set(_pending_context_text(pending))

    if tokens & confirmation_markers:
        return len(tokens) <= 10 or bool(tokens & pending_tokens)

    if tokens & reference_markers:
        return True

    return bool(len(tokens) <= 8 and tokens & pending_tokens)


def _looks_like_clarification_answer(
    message: str,
    pending: dict,
    classification: dict,
) -> bool:
    if _classification_is_security_sensitive(classification):
        return False

    pending_domain = _pending_domain(pending)
    response_domain = _classification_domain(classification)
    request_type = str(classification.get("request_type") or "").lower()
    response_domain_is_general = (
        response_domain in {"knowledge", "general"}
        and request_type != "enterprise_action"
    )

    if response_domain and pending_domain and response_domain == pending_domain:
        return True

    if (
        response_domain
        and pending_domain
        and response_domain != pending_domain
        and not response_domain_is_general
    ):
        return False

    if _looks_like_standalone_question(message):
        return False

    normalized = normalize_followup_text(message)
    tokens = normalized.split()

    if len(tokens) <= 12 and not _looks_like_backend_action(classification):
        return True

    missing = pending.get("missing_parameters")
    missing_text = " ".join(str(item).lower() for item in missing or [])
    has_value_shape = bool(
        re.search(r"\b\d{1,4}([/-]\d{1,2})?([/-]\d{1,4})?\b", normalized)
        or re.search(r"\b[A-Z0-9][A-Z0-9._-]{2,}\b", message)
    )

    return bool(missing_text and has_value_shape)


def _looks_like_pending_task_followup(
    message: str,
    pending: dict,
    classification: dict,
) -> bool:
    if _classification_is_security_sensitive(classification):
        return False

    pending_domain = _pending_domain(pending)
    response_domain = _classification_domain(classification)
    request_type = str(classification.get("request_type") or "").lower()
    response_domain_is_general = (
        response_domain in {"knowledge", "general"}
        and request_type != "enterprise_action"
    )

    if response_domain and pending_domain and response_domain == pending_domain:
        return True

    if (
        response_domain
        and pending_domain
        and response_domain != pending_domain
        and not response_domain_is_general
    ):
        return False

    if _looks_like_standalone_question(message):
        return False

    return _looks_like_confirmation_or_reference(message, pending)


def resolve_pending_clarification_context(
    session_id: str,
    message: str,
    memory_context: dict,
    current_user: dict,
):
    pending = conversation_memory.get_pending_clarification(session_id)

    if not pending:
        return {
            "pending_context_used": False,
            "cleared_pending_context": False,
        }

    response_classification = classify_message(
        message,
        context_memory=memory_context,
        user_permissions=user_permission_context(current_user),
    )

    if _classification_is_security_sensitive(response_classification):
        return {
            "pending_context_used": False,
            "cleared_pending_context": False,
            "pending_sensitive_bypass_blocked": True,
        }

    if not _looks_like_clarification_answer(message, pending, response_classification):
        conversation_memory.clear_pending_clarification(session_id)
        return {
            "pending_context_used": False,
            "cleared_pending_context": True,
            "original_request": pending.get("original_request"),
        }

    missing_parameters = pending.get("missing_parameters") or []
    merged_request = (
        f"{pending.get('resolved_request') or pending.get('original_request')}\n\n"
        "Clarification utilisateur"
        f"{' pour ' + ', '.join(str(item) for item in missing_parameters) if missing_parameters else ''}: "
        f"{message}"
    )

    return {
        "pending_context_used": True,
        "cleared_pending_context": False,
        "original_request": pending.get("original_request"),
        "merged_request": merged_request,
        "merged_parameters": {
            "clarification": message,
            "missing_parameters": missing_parameters,
        },
    }


def resolve_pending_task_context(
    session_id: str,
    message: str,
    memory_context: dict,
    current_user: dict,
):
    pending = conversation_memory.get_pending_task(session_id)

    if not pending:
        return {
            "pending_context_used": False,
            "cleared_pending_context": False,
            "pending_context_cleared": False,
        }

    response_classification = classify_message(
        message,
        context_memory=memory_context,
        user_permissions=user_permission_context(current_user),
    )

    if _classification_is_security_sensitive(response_classification):
        return {
            "pending_context_used": False,
            "cleared_pending_context": False,
            "pending_context_cleared": False,
            "pending_sensitive_bypass_blocked": True,
        }

    if not _looks_like_pending_task_followup(message, pending, response_classification):
        conversation_memory.clear_pending_task(session_id)
        return {
            "pending_context_used": False,
            "pending_context_type": pending.get("context_type"),
            "cleared_pending_context": True,
            "pending_context_cleared": True,
            "original_request": pending.get("original_request"),
        }

    merged_request = (
        f"{pending.get('resolved_request') or pending.get('original_request')}\n\n"
        f"Contexte de suivi: l'utilisateur répond à la suggestion précédente "
        f"({pending.get('suggested_next_action') or 'continuer la tâche'}).\n"
        f"Suivi utilisateur: {message}\n"
        "Continue la même demande avec les mêmes garde-fous; si le résultat exact "
        "était vide, réessaie en lecture seule avec des critères plus larges ou ajustés, "
        "sans inventer de données."
    )

    return {
        "pending_context_used": True,
        "pending_context_type": pending.get("context_type") or "task_follow_up",
        "cleared_pending_context": False,
        "pending_context_cleared": False,
        "original_request": pending.get("original_request"),
        "merged_request": merged_request,
        "merged_parameters": {
            "follow_up": message,
            "suggested_next_action": pending.get("suggested_next_action"),
            "reason": pending.get("reason"),
            "entities": pending.get("entities") or {},
            "parameters": pending.get("parameters") or {},
        },
    }


def resolve_pending_context(
    session_id: str,
    message: str,
    memory_context: dict,
    current_user: dict,
):
    clarification_context = resolve_pending_clarification_context(
        session_id,
        message,
        memory_context,
        current_user,
    )

    if (
        clarification_context.get("pending_context_used")
        or clarification_context.get("pending_sensitive_bypass_blocked")
        or clarification_context.get("cleared_pending_context")
    ):
        clarification_context.setdefault("pending_context_type", "clarification")
        clarification_context.setdefault(
            "pending_context_cleared",
            clarification_context.get("cleared_pending_context") is True,
        )
        return clarification_context

    return resolve_pending_task_context(
        session_id,
        message,
        memory_context,
        current_user,
    )


def build_odoo_memory_followup_classification(context: dict):
    limit = context.get("limit") or 3
    model = context.get("model")
    business_object = context.get("business_object")

    return {
        "intent": "odoo_generic_read",
        "request_type": "enterprise_action",
        "domain": "odoo",
        "capability": "odoo.generic_read",
        "execution_mode": "tool",
        "agent": "odoo_agent",
        "selected_agent": "odoo_agent",
        "action": "odoo_generic_read",
        "target_system": "odoo",
        "risk_level": "low",
        "risk": "low",
        "requires_approval": False,
        "approval_required": False,
        "clarification_needed": False,
        "missing_parameters": [],
        "confidence": "high",
        "reason": "Resolved short follow-up against the previous successful Odoo read context.",
        "classifier_source": "conversation_memory",
        "semantic_source": "conversation_memory",
        "parameters": {
            "operation": "list",
            "business_object": business_object,
            "model": model,
            "model_hint": model,
            "requested_fields": context.get("safe_fields") or [],
            "limit": limit,
            "memory_followup": True,
        },
        "entities": {
            "business_object": business_object,
            "model": model,
            "limit": limit,
        },
    }


def resolve_odoo_result_memory_context(
    session_id: str,
    message: str,
    current_user: dict,
):
    response_classification = classify_message(
        message,
        context_memory={},
        user_permissions=user_permission_context(current_user),
    )

    if _classification_is_security_sensitive(response_classification):
        return {
            "memory_context_used": False,
            "memory_sensitive_bypass_blocked": True,
        }

    context = conversation_memory.resolve_odoo_result_reference(message, session_id)

    if not context:
        return {
            "memory_context_used": False,
        }

    limit = context.get("limit") or 3
    business_object = context.get("business_object") or context.get("model")
    merged_request = f"Liste {limit} {business_object} dans Odoo"

    return {
        "memory_context_used": True,
        "resolved_from_previous_model": context.get("model"),
        "resolved_business_object": business_object,
        "follow_up_limit": limit,
        "original_request": context.get("original_request"),
        "merged_request": merged_request,
        "classification": build_odoo_memory_followup_classification(context),
    }


def attach_context_metadata(
    result: dict,
    pending_context: dict | None,
    memory_followup_context: dict | None = None,
):
    if not isinstance(result, dict):
        return result

    pending_context = pending_context or {}
    memory_followup_context = memory_followup_context or {}

    result["pending_context_used"] = pending_context.get("pending_context_used") is True
    result["cleared_pending_context"] = pending_context.get("cleared_pending_context") is True
    result["pending_context_cleared"] = (
        pending_context.get("pending_context_cleared") is True
        or pending_context.get("cleared_pending_context") is True
    )
    result["memory_context_used"] = memory_followup_context.get("memory_context_used") is True

    for key in (
        "pending_context_type",
        "original_request",
        "merged_request",
        "merged_parameters",
    ):
        value = pending_context.get(key)

        if value not in (None, "", [], {}):
            result[key] = value

    for key in (
        "resolved_from_previous_model",
        "resolved_business_object",
        "follow_up_limit",
    ):
        value = memory_followup_context.get(key)

        if value not in (None, "", [], {}):
            result[key] = value

    return result


def attach_auth_metadata(result: dict, current_user: dict, permission_decision: str):
    if not isinstance(result, dict):
        return result

    result.setdefault("permission_decision", permission_decision)
    result.setdefault(
        "user",
        {
            "email": current_user.get("email"),
            "role": current_user.get("role"),
            "role_label": current_user.get("role_label"),
            "department": current_user.get("department"),
            "department_label": current_user.get("department_label"),
        },
    )
    return result


def _as_record(value):
    return value if isinstance(value, dict) else {}


def _safe_public_url(value):
    if not isinstance(value, str):
        return None

    try:
        from orchestrator.official_web_ingestion import validate_official_url

        return validate_official_url(value)
    except Exception:
        if value.startswith(("https://jamainbaco.com/", "https://www.jamainbaco.com/")):
            return value

    return None


def _sanitize_public_source(source: dict):
    if not isinstance(source, dict):
        return None

    url = _safe_public_url(source.get("url") or source.get("canonical_url"))
    source_type = source.get("source_type")
    sanitized = {
        "source_type": source_type,
        "title": source.get("title"),
        "url": url,
    }

    label = source.get("label")

    if not label and source_type == "official_web":
        label = "Site officiel Jamain Baco"

    if isinstance(label, str) and label.strip():
        sanitized["label"] = label.strip()

    return {
        key: value
        for key, value in sanitized.items()
        if value not in (None, "")
    }


def _extract_public_sources(result: dict):
    source_candidates = []
    agent_result = _as_record(result.get("agent_result"))
    nested_result = _as_record(result.get("result"))

    for candidate in (
        result.get("sources"),
        nested_result.get("sources"),
        agent_result.get("sources"),
        _as_record(agent_result.get("result")).get("sources"),
    ):
        if isinstance(candidate, list):
            source_candidates.extend(candidate)

    sources = []
    seen = set()

    for source in source_candidates:
        sanitized = _sanitize_public_source(source)

        if not sanitized:
            continue

        key = (
            sanitized.get("source_type"),
            sanitized.get("title"),
            sanitized.get("url"),
        )

        if key in seen:
            continue

        seen.add(key)
        sources.append(sanitized)

    return sources


def _extract_public_response_text(result: dict):
    response_value = result.get("response")

    if isinstance(response_value, str) and response_value.strip():
        return response_value.strip()

    if isinstance(response_value, dict):
        content = response_value.get("content")

        if isinstance(content, str) and content.strip():
            return content.strip()

    for candidate in (
        result.get("message"),
        _as_record(result.get("result")).get("answer"),
        _as_record(result.get("result")).get("message"),
        _as_record(result.get("data")).get("message"),
        _as_record(result.get("agent_result")).get("response"),
        _as_record(result.get("agent_result")).get("message"),
        _as_record(_as_record(result.get("agent_result")).get("result")).get("answer"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    if result.get("requires_approval") or result.get("approval_required"):
        return "Validation requise."

    status = result.get("status")

    if status == "blocked":
        return "Demande bloquée pour des raisons de sécurité."

    if status == "access_denied":
        return ACCESS_DENIED_MESSAGE

    if status == "department_access_denied":
        return DEPARTMENT_ACCESS_DENIED_MESSAGE

    if status == "unsupported":
        return "Action non disponible. Cette demande n’est pas encore connectée à un outil backend sécurisé."

    if status == "needs_clarification":
        return "Des informations sont nécessaires pour continuer."

    return "Demande traitée par l’orchestrateur."


def _normalize_public_status(status):
    if status == "needs_clarification":
        return "clarification_required"

    return status or "completed"


def _classification_values(classification: dict, *keys: str):
    values = []

    for key in keys:
        value = classification.get(key)

        if value not in {None, ""}:
            values.append(str(value).strip().lower())

    semantic = classification.get("semantic_request")

    if isinstance(semantic, dict):
        for container_name in ("entities", "parameters"):
            container = semantic.get(container_name)

            if isinstance(container, dict):
                for key in keys:
                    value = container.get(key)

                    if value not in {None, ""}:
                        values.append(str(value).strip().lower())

    for container_name in ("entities", "parameters"):
        container = classification.get(container_name)

        if isinstance(container, dict):
            for key in keys:
                value = container.get(key)

                if value not in {None, ""}:
                    values.append(str(value).strip().lower())

    return values


def _is_explicit_odoo_route(classification: dict):
    return (
        classification.get("domain") == "odoo"
        or classification.get("target_system") == "odoo"
        or classification.get("selected_agent") == "odoo_agent"
        or classification.get("agent") == "odoo_agent"
    )


def _is_structured_odoo_write(classification: dict):
    operation_values = _classification_values(classification, "operation")
    action_values = _classification_values(classification, "action", "intent")

    if any(value in ODOO_WRITE_OPERATION_VALUES for value in operation_values):
        return True

    if any(value in ODOO_WRITE_OPERATION_VALUES for value in action_values):
        return True

    if _classification_values(classification, "field", "new_value", "new_price"):
        return True

    if classification.get("requires_approval") is True or classification.get("approval_required") is True:
        return True

    return False


def _is_registered_odoo_write_capability(capability: str | None):
    if not capability:
        return False

    metadata = get_capability_metadata(capability)

    if not metadata:
        return False

    return (
        metadata.get("permission_category") == "odoo_write"
        or str(metadata.get("io_mode") or "").startswith("write")
        or metadata.get("requires_approval") is True
    )


def _unsupported_odoo_write_classification(classification: dict):
    normalized = dict(classification)
    normalized["domain"] = "odoo"
    normalized["target_system"] = "odoo"
    normalized["agent"] = "odoo_agent"
    normalized["selected_agent"] = "odoo_agent"
    normalized["action"] = "unsupported_capability"
    normalized["risk_level"] = "medium"
    normalized["risk"] = "medium"
    normalized["requires_approval"] = False
    normalized["approval_required"] = False
    normalized["capability_validation_error"] = (
        normalized.get("capability_validation_error")
        or "Odoo write request did not select a registered safe write capability."
    )
    return normalized


def _is_structured_odoo_read(classification: dict):
    operation_values = _classification_values(classification, "operation")

    if any(value in ODOO_READ_OPERATION_VALUES for value in operation_values):
        return True

    return bool(
        _classification_values(
            classification,
            "business_object",
            "query",
            "record_keyword",
            "target",
            "topic",
            "model",
            "model_name",
            "model_hint",
        )
    )


def normalize_safe_odoo_read_fallback(classification: dict | None):
    if not isinstance(classification, dict):
        return classification

    if classification.get("action_type") == "unsupported":
        return classification

    if not _is_explicit_odoo_route(classification):
        return classification

    if _is_structured_odoo_write(classification):
        action = str(classification.get("action") or "").strip().lower()
        has_known_action = action and action not in {
            "unknown",
            "unsupported",
            "unsupported_capability",
        }

        if (
            not _is_registered_odoo_write_capability(classification.get("capability"))
            and not has_known_action
        ):
            return _unsupported_odoo_write_classification(classification)

        return classification

    capability = classification.get("capability")

    if capability in {
        "odoo.generic_read",
        "odoo.partner_search",
        "odoo.document_search",
        "odoo.accounting_bank_read",
        "odoo.customer_invoice_list",
        "odoo.connection_status",
        "odoo.purchase_supplier_ranking",
        "odoo.sale_customer_ranking",
        "odoo.analytic_account_search",
        "odoo.analytic_account_details",
        "odoo.product_search",
        "odoo.product_stock",
        "odoo.inventory_summary",
    }:
        return classification

    if not _is_structured_odoo_read(classification):
        return classification

    normalized = dict(classification)
    normalized["request_type"] = normalized.get("request_type") or "enterprise_action"
    normalized["intent"] = "odoo_generic_read"
    normalized["domain"] = "odoo"
    normalized["target_system"] = "odoo"
    normalized["agent"] = "odoo_agent"
    normalized["selected_agent"] = "odoo_agent"
    normalized["capability"] = "odoo.generic_read"
    normalized["execution_mode"] = "tool"
    normalized["action"] = "odoo_generic_read"
    normalized["risk_level"] = "low"
    normalized["risk"] = "low"
    normalized["requires_approval"] = False
    normalized["approval_required"] = False
    normalized["capability_validation_error"] = None
    normalized.setdefault("parameters", {})

    if not isinstance(normalized["parameters"], dict):
        normalized["parameters"] = {}

    if not normalized["parameters"].get("operation"):
        normalized["parameters"]["operation"] = "list"

    if not normalized["parameters"].get("business_object"):
        for value in _classification_values(
            classification,
            "business_object",
            "query",
            "record_keyword",
            "target",
            "topic",
        ):
            normalized["parameters"]["business_object"] = value
            break

    return normalized


def _extract_approval_id(result: dict):
    result_record = _as_record(result.get("result"))
    data_record = _as_record(result.get("data"))
    approval = (
        _as_record(result.get("approval"))
        or _as_record(result_record.get("approval"))
        or _as_record(data_record.get("approval"))
    )

    return (
        result.get("approval_id")
        or data_record.get("approval_id")
        or result_record.get("approval_id")
        or approval.get("id")
    )


def _extract_approval_summary(result: dict):
    result_record = _as_record(result.get("result"))
    data_record = _as_record(result.get("data"))
    approval = (
        _as_record(result.get("approval"))
        or _as_record(result_record.get("approval"))
        or _as_record(data_record.get("approval"))
    )

    if not approval:
        return {}

    return {
        "action": approval.get("action") or result.get("action") or result.get("parsed_action"),
        "entity_name": approval.get("entity_name"),
        "requested_change": approval.get("requested_change"),
    }


def _build_public_technical(result: dict):
    agent_result = _as_record(result.get("agent_result"))
    model_response = _as_record(result.get("response"))
    selected_model = _as_record(result.get("selected_model"))
    nested_result = _as_record(result.get("result"))
    nested_nested_result = _as_record(nested_result.get("result"))
    user = _as_record(result.get("user"))

    provider = (
        result.get("provider")
        or agent_result.get("provider")
        or selected_model.get("provider")
        or model_response.get("provider")
    )
    model = (
        result.get("model")
        or agent_result.get("model")
        or selected_model.get("model")
        or model_response.get("model")
    )
    odoo_tool_steps = result.get("tool_sequence") or nested_result.get("tool_sequence")
    final_odoo_model = (
        result.get("odoo_model")
        or nested_result.get("model")
        or next(iter(result.get("models_used") or nested_result.get("models_used") or []), None)
    )
    final_record_count = result.get("record_count") or nested_result.get("record_count")
    final_business_scope_status = (
        result.get("business_scope_status")
        or nested_result.get("business_scope_status")
        or nested_nested_result.get("business_scope_status")
        or agent_result.get("business_scope_status")
    )

    if not final_business_scope_status and isinstance(odoo_tool_steps, list):
        final_business_scope_status = next(
            (
                item.get("business_scope_status")
                for item in reversed(odoo_tool_steps)
                if isinstance(item, dict) and item.get("business_scope_status")
            ),
            None,
        )
    action = (
        result.get("parsed_action")
        or result.get("action")
        or agent_result.get("parsed_action")
    )
    approval_summary = _extract_approval_summary(result)
    capability = result.get("capability")

    if not capability:
        agent = result.get("agent") or result.get("selected_agent") or agent_result.get("agent")

        if agent == "knowledge_agent":
            capability = "knowledge.general_answer"
        elif agent == "support_agent":
            capability = "support.troubleshooting"
        elif agent == "server_agent":
            capability = result.get("tool_used") or agent_result.get("tool_used") or "server.local_health"
        elif agent == "odoo_agent":
            capability = result.get("tool_used") or action

    fields_used = (
        result.get("fields_used")
        if "fields_used" in result
        else agent_result.get("fields_used")
        if "fields_used" in agent_result
        else nested_result.get("fields_used")
    )
    domain_used = (
        result.get("domain_used")
        if "domain_used" in result
        else agent_result.get("domain_used")
        if "domain_used" in agent_result
        else nested_result.get("domain_used")
    )
    count_returned = (
        result.get("count_returned")
        if "count_returned" in result
        else agent_result.get("count_returned")
        if "count_returned" in agent_result
        else nested_result.get("count_returned")
    )

    technical = {
        "intent": result.get("intent"),
        "request_type": result.get("request_type"),
        "domain": result.get("domain"),
        "agent": result.get("agent") or result.get("selected_agent") or agent_result.get("agent"),
        "capability": capability,
        "execution_mode": result.get("execution_mode"),
        "action": action,
        "risk": result.get("risk") or result.get("risk_level"),
        "approval_status": result.get("approval_status"),
        "parser_source": result.get("parser_source") or agent_result.get("parser_source"),
        "tool_used": result.get("tool_used") or agent_result.get("tool_used"),
        "provider": provider,
        "model": model,
        "llm_success": (
            result.get("llm_success")
            if "llm_success" in result
            else nested_result.get("llm_success")
        ),
        "llm_error": result.get("llm_error") or nested_result.get("llm_error"),
        "permission_decision": result.get("permission_decision"),
        "department": user.get("department"),
        "knowledge_scopes": result.get("knowledge_scopes") or nested_result.get("knowledge_scopes"),
        "target_system": result.get("target_system"),
        "odoo_model": final_odoo_model,
        "record_count": final_record_count,
        "selected_model": result.get("selected_model_name") or agent_result.get("selected_model_name") or result.get("selected_odoo_model") or final_odoo_model,
        "candidate_models": result.get("candidate_models") or agent_result.get("candidate_models") or nested_result.get("candidate_models"),
        "fields_used": fields_used,
        "domain_used": domain_used,
        "count_returned": count_returned,
        "failure_reason": result.get("failure_reason") or agent_result.get("failure_reason") or nested_result.get("failure_reason"),
        "aggregation_field": result.get("aggregation_field") or agent_result.get("aggregation_field") or nested_result.get("aggregation_field"),
        "odoo_method": result.get("odoo_method") or agent_result.get("odoo_method") or nested_result.get("odoo_method"),
        "odoo_tool_steps": odoo_tool_steps,
        "final_odoo_model": final_odoo_model,
        "final_record_count": final_record_count,
        "business_scope_status": final_business_scope_status,
        "retrieval_query": result.get("retrieval_query") or nested_result.get("retrieval_query"),
        "classifier_source": result.get("classifier_source"),
        "semantic_source": result.get("semantic_source"),
        "approval_action": approval_summary.get("action"),
        "approval_entity": approval_summary.get("entity_name"),
        "approval_requested_change": approval_summary.get("requested_change"),
        "memory_context_used": result.get("memory_context_used"),
        "resolved_from_previous_model": result.get("resolved_from_previous_model"),
        "resolved_business_object": result.get("resolved_business_object"),
        "follow_up_limit": result.get("follow_up_limit"),
        "pending_context_used": result.get("pending_context_used"),
        "pending_context_type": result.get("pending_context_type"),
        "original_request": result.get("original_request"),
        "merged_request": result.get("merged_request"),
        "merged_parameters": result.get("merged_parameters"),
        "cleared_pending_context": result.get("cleared_pending_context"),
        "pending_context_cleared": result.get("pending_context_cleared"),
    }

    return {
        key: value
        for key, value in technical.items()
        if value not in (None, "", [], {}) or key == "domain_used" and value == []
    }


def serialize_chat_response(result) -> PublicChatResponse:
    if not isinstance(result, dict):
        return PublicChatResponse(
            status="completed",
            response=str(result),
            requires_approval=False,
            approval_id=None,
            sources=[],
            technical=ChatTechnicalMetadata(),
        )

    return PublicChatResponse(
        status=_normalize_public_status(result.get("status")),
        response=_extract_public_response_text(result),
        requires_approval=bool(
            result.get("requires_approval") or result.get("approval_required")
        ),
        approval_id=_extract_approval_id(result),
        sources=[
            PublicSource(**source)
            for source in _extract_public_sources(result)
        ],
        technical=ChatTechnicalMetadata(**_build_public_technical(result)),
    )


def normalize_public_chat_response(result) -> PublicChatResponse:
    return serialize_chat_response(result)


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
            "record_id": metadata.get("record_id"),
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

    if action == "odoo_update_field_request" and tool_name == "odoo_update_field":
        tool_kwargs = {
            "model_name": metadata.get("target_model"),
            "record_id": metadata.get("record_id"),
            "field_name": metadata.get("field_name"),
            "new_value": metadata.get("new_value"),
        }

        if (
            tool_kwargs["model_name"] is None
            or tool_kwargs["record_id"] is None
            or tool_kwargs["field_name"] is None
            or tool_kwargs["new_value"] is None
        ):
            return None, {}, "Approval metadata is missing model, record, field, or requested value."

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


def build_direct_support_response(
    message: str,
    classification: dict | None = None,
):
    classification = classification or {}
    try:
        agent_result = run_support_agent(
            message,
            action=classification.get("action"),
            capability=classification.get("capability"),
            execution_mode=classification.get("execution_mode"),
        )
    except TypeError:
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
        "request_type": classification.get("request_type"),
        "domain": classification.get("domain"),
        "capability": classification.get("capability"),
        "execution_mode": classification.get("execution_mode"),
        "classifier_source": classification.get("classifier_source"),
        "semantic_source": classification.get("semantic_source"),
        "action": agent_result.get("parsed_action") if isinstance(agent_result, dict) else "troubleshoot_issue",
        "message": "Support troubleshooting response generated.",
    })

    return {
        "intent": "support",
        "agent": "support_agent",
        "selected_agent": "support_agent",
        "risk": "low",
        "risk_level": "low",
        "request_type": classification.get("request_type"),
        "domain": classification.get("domain"),
        "capability": classification.get("capability") or "support.troubleshooting",
        "execution_mode": classification.get("execution_mode"),
        "classifier_source": classification.get("classifier_source"),
        "semantic_source": classification.get("semantic_source"),
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


def build_department_access_denied_response(
    classification: dict,
    current_user: dict,
    capability: str,
):
    agent = classification.get("selected_agent") or classification.get("agent", "orchestrator")

    return {
        "intent": classification.get("intent", "department_access_denied"),
        "agent": agent,
        "selected_agent": agent,
        "risk": classification.get("risk", classification.get("risk_level", "low")),
        "risk_level": classification.get("risk_level", classification.get("risk", "low")),
        "requires_approval": False,
        "approval_required": False,
        "approval_status": "not_required",
        "status": "department_access_denied",
        "message": DEPARTMENT_ACCESS_DENIED_MESSAGE,
        "tool_used": None,
        "action": "department_access_denied",
        "target_system": classification.get("target_system"),
        "capability": capability,
        "result": {
            "allowed": False,
            "capability": capability,
            "department": current_user.get("department"),
            "message": DEPARTMENT_ACCESS_DENIED_MESSAGE,
        },
        "agent_result": {
            "agent": agent,
            "tool_used": None,
            "result": {
                "allowed": False,
                "capability": capability,
                "message": DEPARTMENT_ACCESS_DENIED_MESSAGE,
            },
        },
        "permission_decision": "department_denied",
        "user": {
            "email": current_user.get("email"),
            "role": current_user.get("role"),
            "role_label": current_user.get("role_label"),
            "department": current_user.get("department"),
            "department_label": current_user.get("department_label"),
        },
    }


def build_clarification_response(classification: dict, current_user: dict):
    missing = classification.get("missing_parameters")

    if not isinstance(missing, list):
        missing = []

    missing_text = ", ".join(str(item) for item in missing if item)
    message = (
        f"Il me manque ces informations pour continuer : {missing_text}."
        if missing_text
        else "Il me manque des informations pour continuer."
    )
    agent = classification.get("selected_agent") or classification.get("agent", "orchestrator")

    return {
        "intent": classification.get("intent", "clarification"),
        "request_type": classification.get("request_type"),
        "domain": classification.get("domain"),
        "agent": agent,
        "selected_agent": agent,
        "risk": classification.get("risk", classification.get("risk_level", "low")),
        "risk_level": classification.get("risk_level", classification.get("risk", "low")),
        "requires_approval": False,
        "approval_required": False,
        "approval_status": "not_required",
        "status": "needs_clarification",
        "message": message,
        "tool_used": None,
        "action": classification.get("action", "needs_clarification"),
        "target_system": classification.get("target_system"),
        "capability": classification.get("capability"),
        "execution_mode": classification.get("execution_mode"),
        "missing_parameters": missing,
        "result": {
            "missing_parameters": missing,
            "message": message,
        },
        "agent_result": {
            "agent": agent,
            "tool_used": None,
            "result": {
                "missing_parameters": missing,
                "message": message,
            },
        },
        "permission_decision": "allowed",
        "user": {
            "email": current_user.get("email"),
            "role": current_user.get("role"),
            "role_label": current_user.get("role_label"),
            "department": current_user.get("department"),
            "department_label": current_user.get("department_label"),
        },
    }


def build_direct_knowledge_response(
    message: str,
    department_profile=None,
    knowledge_query: str | None = None,
    classification: dict | None = None,
):
    classification = classification or {}
    knowledge_scopes = (
        department_profile.knowledge_scopes
        if department_profile is not None
        else ("company_common",)
    )
    llm_project_env = (
        department_profile.llm_project_env
        if department_profile is not None
        else None
    )
    try:
        agent_result = run_knowledge_agent(
            message,
            knowledge_scopes=knowledge_scopes,
            llm_project_env=llm_project_env,
            knowledge_query=knowledge_query,
            capability=classification.get("capability"),
            execution_mode=classification.get("execution_mode"),
            semantic_request=classification.get("semantic_request"),
        )
    except TypeError:
        agent_result = run_knowledge_agent(
            message,
            knowledge_scopes=knowledge_scopes,
            llm_project_env=llm_project_env,
            knowledge_query=knowledge_query,
        )
    result = agent_result.get("result") if isinstance(agent_result, dict) else None
    knowledge_message = ""
    provider = "local_policy"
    model = "knowledge_agent"
    reason = "Direct knowledge route handled the request."

    if isinstance(agent_result, dict):
        knowledge_message = agent_result.get("response") or agent_result.get("message") or ""
        provider = agent_result.get("provider") or provider
        model = agent_result.get("model") or model

        if agent_result.get("tool_used") == "public_llm_answer":
            reason = "Public knowledge question answered by the configured LLM provider."
        elif agent_result.get("tool_used") == "internal_documents":
            reason = "Internal knowledge question answered from configured internal documents."
    else:
        knowledge_message = str(agent_result)

    if not knowledge_message and isinstance(result, dict):
        knowledge_message = result.get("answer") or result.get("message")

    llm_success = (
        agent_result.get("llm_success")
        if isinstance(agent_result, dict)
        else None
    )
    llm_error = (
        agent_result.get("llm_error")
        if isinstance(agent_result, dict)
        else None
    )

    if not knowledge_message:
        knowledge_message = (
            "Je ne peux pas générer une réponse fiable pour le moment, car le "
            "fournisseur LLM configuré n’est pas disponible."
        )
        if isinstance(agent_result, dict):
            agent_result["llm_success"] = False
            agent_result.setdefault("llm_error", "empty_response")
            llm_success = False
            llm_error = agent_result.get("llm_error")

    sources = []
    retrieval_query = None

    if isinstance(agent_result, dict):
        sources = agent_result.get("sources") or []
        retrieval_query = agent_result.get("retrieval_query")

    if not sources and isinstance(result, dict):
        sources = result.get("sources") or []

    if retrieval_query is None and isinstance(result, dict):
        retrieval_query = result.get("retrieval_query")

    log_request({
        "event_type": "knowledge_request",
        "system": "knowledge",
        "agent": "knowledge_agent",
        "status": "completed",
        "risk": "low",
        "approval_status": "not_required",
        "user_message": message,
        "request_type": classification.get("request_type"),
        "domain": classification.get("domain"),
        "capability": classification.get("capability"),
        "execution_mode": classification.get("execution_mode"),
        "classifier_source": classification.get("classifier_source"),
        "semantic_source": classification.get("semantic_source"),
        "action": agent_result.get("parsed_action") if isinstance(agent_result, dict) else "answer_question",
        "message": "Knowledge response generated.",
    })

    return {
        "intent": "knowledge",
        "agent": "knowledge_agent",
        "selected_agent": "knowledge_agent",
        "risk": "low",
        "risk_level": "low",
        "request_type": classification.get("request_type"),
        "domain": classification.get("domain"),
        "capability": classification.get("capability") or "knowledge.general_answer",
        "execution_mode": classification.get("execution_mode"),
        "classifier_source": classification.get("classifier_source"),
        "semantic_source": classification.get("semantic_source"),
        "selected_model": {
            "provider": provider,
            "model": model,
            "reason": reason,
        },
        "requires_approval": False,
        "approval_required": False,
        "approval_status": "not_required",
        "status": "completed",
        "message": knowledge_message,
        "llm_success": llm_success,
        "llm_error": llm_error,
        "parser_source": agent_result.get("parser_source", "knowledge_fallback") if isinstance(agent_result, dict) else "knowledge_fallback",
        "parsed_action": (
            classification.get("action")
            or agent_result.get("parsed_action", "answer_knowledge_question")
        )
        if isinstance(agent_result, dict)
        else classification.get("action", "answer_knowledge_question"),
        "tool_used": agent_result.get("tool_used") if isinstance(agent_result, dict) else None,
        "agent_result": agent_result,
        "result": result,
        "knowledge_scopes": list(knowledge_scopes),
        "sources": sources,
        "retrieval_query": retrieval_query,
    }


def build_direct_server_response(message: str):
    agent_result = run_server_agent(message)
    result = agent_result.get("result") if isinstance(agent_result, dict) else None
    tool_used = agent_result.get("tool_used") if isinstance(agent_result, dict) else None
    tool_metadata = get_tool_metadata(tool_used) if tool_used else None
    capability = (
        tool_metadata.get("capability")
        if isinstance(tool_metadata, dict)
        else None
    )

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
        "domain": "server",
        "capability": capability,
        "execution_mode": "tool" if capability else None,
        "parser_source": agent_result.get("parser_source", "server_fallback") if isinstance(agent_result, dict) else "server_fallback",
        "parsed_action": agent_result.get("parsed_action", "unknown") if isinstance(agent_result, dict) else "unknown",
        "tool_used": tool_used,
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


@app.post("/auth/login")
def auth_login(request: LoginRequest):
    result = authenticate_demo_user(request.email, request.password)

    if result is None:
        raise HTTPException(
            status_code=401,
            detail=INVALID_CREDENTIALS_MESSAGE,
        )

    return result


@app.get("/auth/me")
def auth_me(current_user: dict = Depends(get_current_user)):
    return {
        "email": current_user.get("email"),
        "role": current_user.get("role"),
        "role_label": current_user.get("role_label"),
        "department": current_user.get("department"),
        "department_label": current_user.get("department_label"),
        "permissions": current_user.get("permissions", []),
    }


@app.post("/chat", response_model=PublicChatResponse)
def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    audit_token = set_audit_user_context(current_user, "allowed")

    try:
        return normalize_public_chat_response(
            _authenticated_chat(request, current_user)
        )
    finally:
        reset_audit_user_context(audit_token)


def _authenticated_chat(request: ChatRequest, current_user: dict):
    original_message = request.message
    message = original_message.strip()
    session_id = request.session_id or "demo-session"

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty",
        )

    memory_context = conversation_memory.get_safe_context(session_id)
    permissions_context = user_permission_context(current_user)
    memory_followup_context = resolve_odoo_result_memory_context(
        session_id,
        message,
        current_user,
    )
    pending_context = {
        "pending_context_used": False,
        "cleared_pending_context": False,
        "pending_context_cleared": False,
    }

    if not memory_followup_context.get("memory_context_used"):
        pending_context = resolve_pending_context(
            session_id,
            message,
            memory_context,
            current_user,
        )

    if pending_context.get("pending_context_used"):
        message = pending_context.get("merged_request") or message
    elif memory_followup_context.get("memory_context_used"):
        message = memory_followup_context.get("merged_request") or message

    contextual_resolution = resolve_contextual_message(message, memory_context)
    enriched_message = contextual_resolution.get("resolved_message") or message

    def finish_chat_result(
        result: dict,
        classification: dict | None = None,
        permission_decision: str | None = None,
    ):
        if isinstance(result, dict):
            attach_context_metadata(result, pending_context, memory_followup_context)

        if pending_context.get("pending_context_used") and isinstance(result, dict):
            if result_needs_clarification(result):
                store_pending_clarification(
                    session_id,
                    original_message,
                    enriched_message,
                    classification,
                    result,
                )
            else:
                conversation_memory.clear_pending_clarification(session_id)
                conversation_memory.clear_pending_task(session_id)
                result["cleared_pending_context"] = True
                result["pending_context_cleared"] = True
        elif pending_context.get("cleared_pending_context") and isinstance(result, dict):
            result["cleared_pending_context"] = True
            result["pending_context_cleared"] = True
        elif isinstance(result, dict) and result_needs_clarification(result):
            store_pending_clarification(
                session_id,
                original_message,
                enriched_message,
                classification,
                result,
            )
        elif isinstance(result, dict) and result_suggests_pending_task(result):
            store_pending_task(
                session_id,
                original_message,
                enriched_message,
                classification,
                result,
            )

        if permission_decision:
            result = attach_auth_metadata(result, current_user, permission_decision)

        remember_chat_result(session_id, result)
        return result

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

    primary_classification = (
        memory_followup_context.get("classification")
        if memory_followup_context.get("memory_context_used")
        else classify_message(
            enriched_message,
            context_memory=memory_context,
            user_permissions=permissions_context,
        )
    )
    primary_classification = normalize_safe_odoo_read_fallback(primary_classification)
    primary_agent = primary_classification.get("selected_agent")
    route_permission = resolve_route_permission(primary_classification)
    department_profile = get_department_profile(current_user.get("department"))

    if primary_classification.get("capability_validation_error"):
        unsupported_result = unsupported_action_payload(primary_classification, current_user)
        unsupported_result["capability"] = primary_classification.get("capability")
        unsupported_result["execution_mode"] = primary_classification.get("execution_mode")
        unsupported_result["request_type"] = primary_classification.get("request_type")
        unsupported_result["domain"] = primary_classification.get("domain")
        log_request({
            "event_type": "unsupported_capability",
            "title": "Capacité non enregistrée",
            "system": primary_classification.get("target_system", "orchestrator"),
            "agent": primary_agent or "orchestrator",
            "status": "unsupported",
            "risk": primary_classification.get("risk_level", "low"),
            "approval_status": "not_required",
            "permission_decision": "denied",
            "user_message": enriched_message,
            "request_type": primary_classification.get("request_type"),
            "domain": primary_classification.get("domain"),
            "capability": primary_classification.get("capability"),
            "execution_mode": primary_classification.get("execution_mode"),
            "intent": primary_classification.get("intent"),
            "action": primary_classification.get("action"),
            "message": primary_classification.get("capability_validation_error"),
        })
        return finish_chat_result(unsupported_result, primary_classification)

    if primary_classification.get("clarification_needed"):
        clarification_result = build_clarification_response(
            primary_classification,
            current_user,
        )
        log_request({
            "event_type": "clarification_required",
            "title": "Clarification requise",
            "system": primary_classification.get("target_system", "orchestrator"),
            "agent": primary_agent or "orchestrator",
            "status": "needs_clarification",
            "risk": primary_classification.get("risk_level", "low"),
            "approval_status": "not_required",
            "permission_decision": "allowed",
            "user_message": enriched_message,
            "request_type": primary_classification.get("request_type"),
            "domain": primary_classification.get("domain"),
            "capability": primary_classification.get("capability"),
            "execution_mode": primary_classification.get("execution_mode"),
            "intent": primary_classification.get("intent"),
            "action": primary_classification.get("action"),
            "missing_parameters": primary_classification.get("missing_parameters"),
            "message": "La capacité est comprise mais des paramètres sont manquants.",
        })
        return finish_chat_result(clarification_result, primary_classification)

    if route_permission.blocked:
        blocked_result = process_request(
            enriched_message,
            classification=primary_classification,
        )
        return finish_chat_result(blocked_result, primary_classification, "denied")

    if route_permission.unsupported:
        unsupported_result = unsupported_action_payload(primary_classification, current_user)
        log_request({
            "event_type": "unsupported_action",
            "title": "Action non prise en charge",
            "system": primary_classification.get("target_system", "orchestrator"),
            "agent": primary_agent or "orchestrator",
            "status": "unsupported",
            "risk": primary_classification.get("risk_level", "low"),
            "approval_status": "not_required",
            "permission_decision": "denied",
            "user_message": enriched_message,
            "request_type": primary_classification.get("request_type"),
            "domain": primary_classification.get("domain"),
            "capability": primary_classification.get("capability"),
            "execution_mode": primary_classification.get("execution_mode"),
            "intent": primary_classification.get("intent"),
            "action": primary_classification.get("action"),
            "message": "Action non prise en charge. Aucun outil n’a été exécuté.",
        })
        return finish_chat_result(unsupported_result, primary_classification)

    department_allowed, capability = is_route_allowed_for_department(
        current_user.get("department"),
        primary_classification,
        route_permission,
    )

    if not department_allowed:
        denied_result = build_department_access_denied_response(
            primary_classification,
            current_user,
            capability,
        )
        log_request({
            "event_type": "department_access_denied",
            "title": "Fonctionnalité indisponible pour le département",
            "system": primary_classification.get("target_system", "orchestrator"),
            "agent": primary_agent or "orchestrator",
            "status": "department_access_denied",
            "risk": primary_classification.get("risk_level", "low"),
            "approval_status": "not_required",
            "permission_decision": "department_denied",
            "user_message": enriched_message,
            "request_type": primary_classification.get("request_type"),
            "domain": primary_classification.get("domain"),
            "capability": primary_classification.get("capability"),
            "execution_mode": primary_classification.get("execution_mode"),
            "intent": primary_classification.get("intent"),
            "action": "department_access_denied",
            "capability": capability,
            "department": current_user.get("department"),
            "message": DEPARTMENT_ACCESS_DENIED_MESSAGE,
        })
        return finish_chat_result(denied_result, primary_classification)

    if not check_chat_permission(current_user, enriched_message, primary_classification):
        denied_result = access_denied_payload(primary_classification, current_user)
        log_request({
            "event_type": "permission_denied",
            "title": "Accès refusé",
            "system": primary_classification.get("target_system", "orchestrator"),
            "agent": primary_agent or "orchestrator",
            "status": "denied",
            "risk": primary_classification.get("risk_level", "low"),
            "approval_status": "not_required",
            "permission_decision": "denied",
            "user_message": enriched_message,
            "request_type": primary_classification.get("request_type"),
            "domain": primary_classification.get("domain"),
            "capability": primary_classification.get("capability"),
            "execution_mode": primary_classification.get("execution_mode"),
            "intent": primary_classification.get("intent"),
            "action": primary_classification.get("action"),
            "message": ACCESS_DENIED_MESSAGE,
        })
        return finish_chat_result(denied_result, primary_classification)

    if primary_agent == "support_agent":
        result = build_direct_support_response(
            enriched_message,
            classification=primary_classification,
        )
        return finish_chat_result(result, primary_classification, "allowed")

    if primary_agent == "server_agent":
        result = build_direct_server_response(enriched_message)
        return finish_chat_result(result, primary_classification, "allowed")

    if primary_agent == "knowledge_agent":
        entities = primary_classification.get("entities")

        if not isinstance(entities, dict):
            entities = {}

        knowledge_query = (
            entities.get("knowledge_topic")
            or entities.get("target")
            or entities.get("record_keyword")
        )
        result = build_direct_knowledge_response(
            enriched_message,
            department_profile,
            knowledge_query=knowledge_query,
            classification=primary_classification,
        )
        return finish_chat_result(result, primary_classification, "allowed")

    if primary_agent == "odoo_agent":
        try:
            odoo_result = run_odoo_agent(
                enriched_message,
                classification=primary_classification,
            )
        except TypeError:
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
            odoo_result.setdefault("request_type", primary_classification.get("request_type"))
            odoo_result.setdefault("domain", primary_classification.get("domain"))
            odoo_result.setdefault("capability", primary_classification.get("capability"))
            odoo_result.setdefault("execution_mode", primary_classification.get("execution_mode"))
            odoo_result.setdefault("target_system", primary_classification.get("target_system"))

        return finish_chat_result(
            odoo_result,
            primary_classification,
            "requires_approval"
            if isinstance(odoo_result, dict) and odoo_result.get("approval_required")
            else "allowed",
        )

    result = process_request(enriched_message, classification=primary_classification)
    return finish_chat_result(
        result,
        primary_classification,
        "requires_approval"
        if isinstance(result, dict) and result.get("approval_required")
        else "allowed",
    )


@app.get("/debug/conversation/{session_id}")
def debug_conversation(session_id: str):
    return conversation_memory.get_safe_context(session_id)


@app.get("/debug/routes")
def debug_routes():
    return sorted(route.path for route in app.routes)


@app.post("/knowledge/web/ingest")
def ingest_official_web(
    request: OfficialWebIngestRequest,
    current_user: dict = Depends(get_current_user),
):
    require_permission(current_user, "knowledge_manage")
    audit_token = set_audit_user_context(current_user, "allowed")

    try:
        try:
            result = OfficialWebsiteIngestionService().ingest(
                url=request.url,
                scope=request.scope,
                crawl=request.crawl,
                max_pages=request.max_pages,
                max_depth=request.max_depth,
            )
        except OfficialWebIngestionError as error:
            log_request({
                "event_type": "official_web_ingestion_rejected",
                "title": "Ingestion site officiel refusée",
                "system": "knowledge",
                "agent": "knowledge_agent",
                "status": "rejected",
                "risk": "medium",
                "approval_status": "not_required",
                "permission_decision": "allowed",
                "action": "official_web_ingestion",
                "source_type": "official_web",
                "scope": request.scope,
                "message": str(error),
            })
            raise HTTPException(status_code=400, detail=str(error))

        public_result = {
            "status": result.get("status", "completed"),
            "source_type": result.get("source_type", "official_web"),
            "scope": result.get("scope", "company_common"),
            "pages_discovered": result.get("pages_discovered", 0),
            "pages_fetched": result.get("pages_fetched", 0),
            "pages_ingested": result.get("pages_ingested", 0),
            "pages_unchanged": result.get("pages_unchanged", 0),
            "pages_failed": result.get("pages_failed", 0),
            "documents": result.get("documents", []),
        }

        log_request({
            "event_type": "official_web_ingestion",
            "title": "Ingestion site officiel Jamain Baco",
            "system": "knowledge",
            "agent": "knowledge_agent",
            "status": public_result["status"],
            "risk": "low",
            "approval_status": "not_required",
            "permission_decision": "allowed",
            "action": "official_web_ingestion",
            "source_type": public_result["source_type"],
            "scope": public_result["scope"],
            "pages_discovered": public_result["pages_discovered"],
            "pages_ingested": public_result["pages_ingested"],
            "pages_unchanged": public_result["pages_unchanged"],
            "pages_failed": public_result["pages_failed"],
        })

        return public_result
    finally:
        reset_audit_user_context(audit_token)


@app.get("/logs")
def get_logs(
    current_user: dict = Depends(get_current_user),
    view: Literal["important", "all"] = Query("important"),
):
    require_permission(current_user, "view_audit_logs")
    log_path = AUDIT_LOG_PATH

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

            if view == "all" or is_important_audit_event(entry):
                logs.append(entry)

    return sorted(
        logs,
        key=lambda item: item.get("timestamp", ""),
        reverse=True,
    )


@app.get("/approvals")
def approvals(current_user: dict = Depends(get_current_user)):
    require_any_permission(current_user, {"view_approvals", "approve_odoo_actions"})
    return get_approvals()


@app.post("/approvals/{approval_id}/approve")
def approve_approval(
    approval_id: str,
    current_user: dict = Depends(get_current_user),
):
    require_permission(current_user, "approve_odoo_actions")
    audit_token = set_audit_user_context(current_user, "allowed")

    try:
        return _approve_approval(approval_id)
    finally:
        reset_audit_user_context(audit_token)


def _approve_approval(approval_id: str):
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
            detail="Validation introuvable.",
        )

    if current_approval.get("status") == "approved" and current_approval.get("executed"):
        return current_approval

    approval = update_approval_status(approval_id, "approved")

    if approval is None:
        raise HTTPException(
            status_code=404,
            detail="Validation introuvable.",
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
def reject_approval(
    approval_id: str,
    current_user: dict = Depends(get_current_user),
):
    require_permission(current_user, "approve_odoo_actions")
    audit_token = set_audit_user_context(current_user, "allowed")

    try:
        return _reject_approval(approval_id)
    finally:
        reset_audit_user_context(audit_token)


def _reject_approval(approval_id: str):
    approval = update_approval_status(approval_id, "rejected")

    if approval is None:
        raise HTTPException(
            status_code=404,
            detail="Validation introuvable.",
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
def odoo_status(current_user: dict = Depends(get_current_user)):
    require_any_permission(
        current_user,
        {"view_odoo_products", "view_odoo_documents", "view_limited_odoo_info"},
    )
    return odoo.test_connection()


@app.get("/odoo/stock/{product_name}")
def odoo_stock(
    product_name: str,
    current_user: dict = Depends(get_current_user),
):
    require_any_permission(
        current_user,
        {"view_odoo_products", "view_limited_odoo_info"},
    )
    return odoo.check_stock(product_name)


@app.get("/odoo/product/{product_name}")
def odoo_product(
    product_name: str,
    current_user: dict = Depends(get_current_user),
):
    require_any_permission(
        current_user,
        {"view_odoo_products", "view_limited_odoo_info"},
    )
    return odoo.check_stock(product_name)


@app.get("/odoo/product-search/{query}")
def odoo_product_search(
    query: str,
    current_user: dict = Depends(get_current_user),
):
    require_any_permission(
        current_user,
        {"view_odoo_products", "view_limited_odoo_info"},
    )
    return odoo.search_product_templates_for_debug(query)


@app.get("/odoo/product-by-id/{product_id}")
def odoo_product_by_id(
    product_id: int,
    current_user: dict = Depends(get_current_user),
):
    require_any_permission(
        current_user,
        {"view_odoo_products", "view_limited_odoo_info"},
    )
    return odoo.get_product_template_by_id(product_id)


@app.get("/odoo/analytic-fields")
def odoo_analytic_fields(current_user: dict = Depends(get_current_user)):
    require_any_permission(current_user, {"view_odoo_products", "request_odoo_write"})
    return odoo.get_analytic_boolean_fields()


@app.get("/odoo/document/search")
def odoo_document_search(
    document_type: DocumentEndpointType = Query(..., alias="type"),
    query: str = Query(..., min_length=1),
    current_user: dict = Depends(get_current_user),
):
    require_any_permission(
        current_user,
        {"view_odoo_documents", "view_limited_odoo_info"},
    )
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
    current_user: dict = Depends(get_current_user),
):
    require_any_permission(
        current_user,
        {"view_odoo_documents", "view_limited_odoo_info"},
    )
    result = dispatch_document_details(document_type, query)
    return normalize_document_endpoint_response(document_type, query, result)
