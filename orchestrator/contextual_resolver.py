import json
import re
import unicodedata
from typing import Any

from models.openai_adapter import generate_structured_response


SAFE_MEMORY_FIELDS = [
    "last_agent",
    "last_intent",
    "last_product_name",
    "last_product_id",
    "last_document_name",
    "last_document_id",
    "last_document_model",
    "last_document_type",
    "last_partner_name",
]

CONFIDENCE_VALUES = {"high", "medium", "low"}

RESOLVER_SCHEMA = {
    "type": "json_schema",
    "name": "contextual_resolution",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "original_message": {"type": "string"},
            "resolved_message": {"type": "string"},
            "used_memory": {"type": "boolean"},
            "resolved_references": {
                "type": "object",
                "additionalProperties": {
                    "type": ["string", "number", "boolean", "null"],
                },
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
        },
        "required": [
            "original_message",
            "resolved_message",
            "used_memory",
            "resolved_references",
            "confidence",
        ],
    },
}


SYSTEM_PROMPT = """
You rewrite contextual enterprise assistant messages into standalone requests.
You never execute tools, approve actions, route requests, or decide risk.
Use only the safe memory context provided by the backend.
Preserve the user's language when possible.
Resolve pronouns and references like it, its, this product, ce produit, ses détails,
son stock, sa référence, ce document, ce bon, son fournisseur, son statut,
and similar phrases.
Do not invent product names, IDs, document names, prices, quantities, suppliers, or actions.
If memory is insufficient, keep the original message and set confidence low.
Do not add secrets or sensitive configuration details.
Output JSON only.
"""


def _safe_memory(memory_context: dict | None) -> dict:
    if not isinstance(memory_context, dict):
        return {}

    return {
        key: memory_context.get(key)
        for key in SAFE_MEMORY_FIELDS
        if memory_context.get(key) not in {None, ""}
    }


def _base_resolution(
    message: str,
    resolved_message: str | None = None,
    used_memory: bool = False,
    resolved_references: dict | None = None,
    confidence: str = "low",
) -> dict:
    return {
        "original_message": message,
        "resolved_message": resolved_message or message,
        "used_memory": used_memory,
        "resolved_references": resolved_references or {},
        "confidence": confidence if confidence in CONFIDENCE_VALUES else "low",
    }


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().replace("’", "'").split())


def _extract_price(message: str) -> tuple[str, str] | None:
    price_match = re.search(
        r"(?:to|à|a)\s+(\d+(?:[.,]\d+)?)\s*(dh|dhs|mad|dirhams?)?",
        message,
        re.IGNORECASE,
    )

    if not price_match:
        return None

    return price_match.group(1).replace(",", "."), (price_match.group(2) or "DH").upper()


def _document_context(memory_context: dict) -> dict:
    document_name = memory_context.get("last_document_name")
    document_id = memory_context.get("last_document_id")

    if not document_name and document_id is None:
        return {}

    context = {
        "reference_type": "document",
    }

    if document_name:
        context["document_name"] = document_name

    if document_id is not None:
        context["document_id"] = document_id

    for memory_key, reference_key in [
        ("last_document_model", "document_model"),
        ("last_document_type", "document_type"),
        ("last_partner_name", "partner_name"),
    ]:
        if memory_context.get(memory_key):
            context[reference_key] = memory_context[memory_key]

    return context


def _document_label(document_context: dict) -> str:
    name = document_context.get("document_name")
    document_id = document_context.get("document_id")
    document_type = document_context.get("document_type")
    type_suffix = f" de type {document_type}" if document_type else ""

    if name and document_id is not None:
        return f"document Odoo {name} avec l'ID {document_id}{type_suffix}"

    if document_id is not None:
        return f"document Odoo avec l'ID {document_id}{type_suffix}"

    return f"document Odoo {name}{type_suffix}"


def _fallback_document_resolution(message: str, memory_context: dict) -> dict | None:
    resolved_references = _document_context(memory_context)

    if not resolved_references:
        return None

    normalized = _normalize_text(message)
    label = _document_label(resolved_references)

    detail_terms = [
        "ce document",
        "ce bon",
        "cette facture",
        "details de ce document",
        "détails de ce document",
        "montre-moi les details de ce document",
        "montre moi les details de ce document",
        "show its details",
        "its details",
    ]
    supplier_terms = [
        "son fournisseur",
        "who is the supplier",
        "supplier",
        "fournisseur",
    ]
    status_terms = [
        "son statut",
        "son etat",
        "son état",
        "what is its status",
        "its status",
        "status",
        "statut",
    ]
    summary_terms = [
        "resume ce document",
        "résume ce document",
        "resumer ce document",
        "summarize this document",
    ]

    if any(term in normalized for term in supplier_terms):
        return _base_resolution(
            message,
            f"Quel est le fournisseur du {label} dans Odoo ?",
            True,
            resolved_references,
            "medium",
        )

    if any(term in normalized for term in status_terms):
        return _base_resolution(
            message,
            f"Quel est le statut du {label} dans Odoo ?",
            True,
            resolved_references,
            "medium",
        )

    if any(term in normalized for term in summary_terms):
        return _base_resolution(
            message,
            f"Résume le {label} dans Odoo",
            True,
            resolved_references,
            "medium",
        )

    if any(term in normalized for term in detail_terms):
        return _base_resolution(
            message,
            f"Montre-moi les détails du {label}",
            True,
            resolved_references,
            "medium",
        )

    return None


def _fallback_resolution(message: str, memory_context: dict) -> dict:
    document_resolution = _fallback_document_resolution(message, memory_context)

    if document_resolution:
        return document_resolution

    product_name = memory_context.get("last_product_name")
    product_id = memory_context.get("last_product_id")

    if not product_name:
        return _base_resolution(message)

    normalized = _normalize_text(message)
    resolved_references = {
        "reference_type": "product",
        "product_name": product_name,
    }

    if product_id is not None:
        resolved_references["product_id"] = product_id

    price = _extract_price(message)
    price_update_terms = [
        "change its price",
        "its price",
        "changer son prix",
        "modifier son prix",
    ]

    if price and any(term in normalized for term in price_update_terms):
        amount, currency = price
        return _base_resolution(
            message,
            f"Change the price of product {product_name} to {amount} {currency} in Odoo",
            True,
            resolved_references,
            "medium",
        )

    if any(term in normalized for term in ["son stock", "its stock", "its quantity", "sa quantite"]):
        return _base_resolution(
            message,
            f"Quel est le stock du produit {product_name} dans Odoo ?",
            True,
            resolved_references,
            "medium",
        )

    if any(term in normalized for term in ["son prix", "its price"]):
        return _base_resolution(
            message,
            f"Quel est le prix du produit {product_name} dans Odoo ?",
            True,
            resolved_references,
            "medium",
        )

    if any(term in normalized for term in ["sa reference", "its reference"]):
        return _base_resolution(
            message,
            f"Quelle est la référence interne du produit {product_name} dans Odoo ?",
            True,
            resolved_references,
            "medium",
        )

    followup_terms = [
        "ses details",
        "ses informations",
        "ses infos",
        "sa fiche",
        "ce produit",
        "cet article",
        "ce dernier",
        "celui-ci",
        "celui ci",
        "its details",
        "its information",
        "its info",
        "this product",
        "that product",
    ]

    if any(term in normalized for term in followup_terms):
        return _base_resolution(
            message,
            f"Montre-moi les détails du produit {product_name} dans Odoo",
            True,
            resolved_references,
            "medium",
        )

    return _base_resolution(message)


def _validate_resolution(message: str, parsed: Any) -> dict | None:
    if not isinstance(parsed, dict):
        return None

    resolved_message = parsed.get("resolved_message")

    if not isinstance(resolved_message, str) or not resolved_message.strip():
        return None

    resolved_references = parsed.get("resolved_references")

    if not isinstance(resolved_references, dict):
        resolved_references = {}

    return _base_resolution(
        message=message,
        resolved_message=resolved_message.strip(),
        used_memory=parsed.get("used_memory") is True,
        resolved_references=resolved_references,
        confidence=str(parsed.get("confidence") or "low"),
    )


def resolve_contextual_message(message: str, memory_context: dict) -> dict:
    safe_memory = _safe_memory(memory_context)

    if not message or not message.strip():
        return _base_resolution(message or "")

    prompt = json.dumps(
        {
            "current_user_message": message,
            "safe_memory_context": safe_memory,
            "examples": [
                {
                    "memory": {
                        "last_agent": "odoo",
                        "last_product_name": "BACO CLEAN",
                        "last_product_id": 3471,
                    },
                    "message": "Montre-moi ses détails",
                    "resolved_message": "Montre-moi les détails du produit BACO CLEAN dans Odoo",
                },
                {
                    "memory": {
                        "last_agent": "odoo",
                        "last_product_name": "BACO CLEAN",
                        "last_product_id": 3471,
                    },
                    "message": "Quel est son stock ?",
                    "resolved_message": "Quel est le stock du produit BACO CLEAN dans Odoo ?",
                },
                {
                    "memory": {
                        "last_agent": "odoo",
                        "last_product_name": "BACO CLEAN",
                        "last_product_id": 3471,
                    },
                    "message": "change its price to 5 DH",
                    "resolved_message": "Change the price of product BACO CLEAN to 5 DH in Odoo",
                },
                {
                    "memory": {
                        "last_agent": "odoo",
                        "last_product_name": "BACO CLEAN",
                        "last_product_id": 3471,
                    },
                    "message": "Et sa référence ?",
                    "resolved_message": "Quelle est la référence interne du produit BACO CLEAN dans Odoo ?",
                },
                {
                    "memory": {
                        "last_agent": "odoo",
                        "last_document_name": "BC-BPP2600313",
                        "last_document_id": 793,
                        "last_document_model": "purchase.order",
                        "last_document_type": "purchase_order",
                        "last_partner_name": "P.A.N",
                    },
                    "message": "Quel est son fournisseur ?",
                    "resolved_message": "Quel est le fournisseur du document Odoo BC-BPP2600313 avec l'ID 793 dans Odoo ?",
                },
                {
                    "memory": {
                        "last_agent": "odoo",
                        "last_document_name": "BC-BPP2600313",
                        "last_document_id": 793,
                    },
                    "message": "show its details",
                    "resolved_message": "Montre-moi les détails du document Odoo BC-BPP2600313 avec l'ID 793",
                },
            ],
        },
        ensure_ascii=False,
    )

    response = generate_structured_response(
        prompt=prompt,
        schema=RESOLVER_SCHEMA,
        system_prompt=SYSTEM_PROMPT,
    )

    if response.get("success"):
        validated = _validate_resolution(message, response.get("parsed"))

        if validated:
            return validated

    return _fallback_resolution(message, safe_memory)
