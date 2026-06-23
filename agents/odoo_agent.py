import os
import re
import unicodedata

from models.openai_adapter import generate_structured_response
from orchestrator.tool_executor import execute_tool
from orchestrator.risk import classify_risk
from orchestrator.approval import requires_approval
from orchestrator.approval_store import create_approval
from orchestrator.audit import log_request


CHANGE_KEYWORDS = [
    "change",
    "modify",
    "update",
    "set",
    "increase",
    "decrease",
    "changer",
    "modifier",
    "mettre à jour",
    "mettre a jour",
    "définir",
    "definir",
    "augmenter",
    "diminuer",
]

SUPPORTED_ODOO_ACTIONS = {
    "check_product_stock",
    "product_search",
    "product_details",
    "inventory_summary",
    "update_product_price",
    "document_search",
    "document_details",
    "update_document_date",
    "update_line_price",
    "update_line_quantity",
    "update_partner",
    "unknown",
    "needs_clarification",
}

BUSINESS_TO_INTERNAL_ACTION = {
    "check_product_stock": "check_stock",
    "product_search": "product_search",
    "product_details": "product_details",
    "inventory_summary": "inventory_summary",
    "update_product_price": "change_price",
    "document_search": "search_document",
    "document_details": "document_details",
    "update_document_date": "update_document_date",
    "update_line_price": "update_document_line",
    "update_line_quantity": "update_document_line",
    "update_partner": "update_document_partner",
    "unknown": "unknown",
    "needs_clarification": "unknown",
}

INTERNAL_TO_BUSINESS_ACTION = {
    "check_stock": "check_product_stock",
    "check_price": "product_details",
    "check_unit": "product_details",
    "check_product_details": "product_details",
    "change_price": "update_product_price",
    "search_document": "document_search",
    "document_details": "document_details",
    "update_document_date": "update_document_date",
    "update_document_partner": "update_partner",
    "inventory_summary": "inventory_summary",
    "product_search": "product_search",
    "product_details": "product_details",
}


ODOO_ACTION_SCHEMA = {
    "type": "json_schema",
    "name": "odoo_action_parse",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["odoo", "support", "server", "general", "unknown"],
            },
            "action": {
                "type": "string",
                "enum": [
                    "check_product_stock",
                    "product_search",
                    "product_details",
                    "inventory_summary",
                    "update_product_price",
                    "document_search",
                    "document_details",
                    "update_document_date",
                    "update_line_price",
                    "update_line_quantity",
                    "update_partner",
                    "unknown",
                    "needs_clarification",
                ],
            },
            "language": {
                "type": "string",
                "enum": ["fr", "en", "mixed"],
            },
            "requires_approval": {"type": "boolean"},
            "needs_clarification": {"type": "boolean"},
            "clarification_reason": {"type": ["string", "null"]},
            "entities": {
                "type": "object",
                "properties": {
                    "product_name": {"type": ["string", "null"]},
                    "document_type": {
                        "type": ["string", "null"],
                        "enum": [
                            "sale_order",
                            "purchase_order",
                            "invoice",
                            "delivery",
                            "unknown",
                            None,
                        ],
                    },
                    "document_reference": {"type": ["string", "null"]},
                    "document_id": {"type": ["integer", "null"]},
                    "partner_name": {"type": ["string", "null"]},
                    "line_product": {"type": ["string", "null"]},
                    "field": {
                        "type": ["string", "null"],
                        "enum": [
                            "expected_arrival_date",
                            "order_date",
                            "invoice_date",
                            "delivery_date",
                            "price_unit",
                            "quantity",
                            "partner",
                            "unknown",
                            None,
                        ],
                    },
                    "new_value": {
                        "type": ["string", "number", "boolean", "null"],
                    },
                    "filename": {"type": ["string", "null"]},
                    "content": {"type": ["string", "null"]},
                },
                "required": [
                    "product_name",
                    "document_type",
                    "document_reference",
                    "document_id",
                    "partner_name",
                    "line_product",
                    "field",
                    "new_value",
                    "filename",
                    "content",
                ],
                "additionalProperties": False,
            },
        },
        "required": [
            "intent",
            "action",
            "language",
            "requires_approval",
            "needs_clarification",
            "clarification_reason",
            "entities",
        ],
        "additionalProperties": False,
    },
}


def normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().split())


def clean_product_name(value: str) -> str:
    if not value:
        return ""

    value = value.strip()

    value = re.sub(
        r"\s+(to|à|a)\s+\d+([.,]\d+)?\s*(dh|dhs|mad|dirhams?)?.*$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\s+(to|à|a)\s+[A-Za-zÀ-ÿ]+$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(r"[?.!,;:]+$", "", value)

    return value.strip()


def extract_product_name(message: str) -> str:
    text = message.strip()

    context_match = re.search(
        r"Context:\s+the referenced product is\s+(.+?)(?:\.|\n|$)",
        text,
        re.IGNORECASE,
    )

    if context_match:
        return clean_product_name(context_match.group(1))

    patterns = [
        r"(?:stock|inventory|inventaire)\s+(?:for|of|du|de|pour)\s+(.+)",
        r"(?:check|show|view|verify|get|consult|search)\s+(?:the\s+)?(?:stock|inventory|product|details|information)\s+(?:for|of)?\s*(.+)",
        r"(?:vérifier|verifier|consulter|afficher|chercher|rechercher)\s+(?:le\s+|la\s+|les\s+)?(?:stock|inventaire|produit|détails|details|informations?)\s+(?:de|du|pour)?\s*(.+)",

        r"(?:change|modify|update|set)\s+(?:the\s+)?(?:sale\s+)?price\s+(?:of|for)\s+(.+?)\s+(?:to|à|a)\s+",
        r"(?:changer|modifier|mettre à jour|mettre a jour|définir|definir)\s+(?:le\s+)?prix\s+(?:de|du|pour)\s+(.+?)\s+(?:à|a|to)\s+",

        r"(?:change|modify|update|set)\s+(?:the\s+)?stock\s+(?:of|for)\s+(.+?)\s+(?:to|à|a)\s+",
        r"(?:changer|modifier|mettre à jour|mettre a jour|définir|definir)\s+(?:le\s+)?stock\s+(?:de|du|pour)\s+(.+?)\s+(?:à|a|to)\s+",

        r"(?:change|modify|update|set)\s+(?:the\s+)?unit\s+(?:of|for)\s+(.+?)\s+(?:to|à|a)\s+",
        r"(?:changer|modifier|mettre à jour|mettre a jour|définir|definir)\s+(?:l['’]unité|unité|unite)\s+(?:de|du|pour)\s+(.+?)\s+(?:à|a|to)\s+",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return clean_product_name(match.group(1))

    fallback = text

    fallback = re.sub(
        r"^(check|show|view|get|verify|consult|search|find)\s+",
        "",
        fallback,
        flags=re.IGNORECASE,
    )

    fallback = re.sub(
        r"^(vérifier|verifier|afficher|voir|consulter|chercher|rechercher)\s+",
        "",
        fallback,
        flags=re.IGNORECASE,
    )

    fallback = re.sub(
        r"^(stock|inventory|inventaire|product|produit|details|détails|informations?)\s+(for|of|de|du|pour)?\s*",
        "",
        fallback,
        flags=re.IGNORECASE,
    )

    return clean_product_name(fallback)


def extract_requested_value(message: str):
    value_match = re.search(
        r"(?:to|à|a)\s+(\d+(?:[.,]\d+)?)\s*(dh|dhs|mad|dirhams?)?",
        message,
        re.IGNORECASE,
    )

    if value_match:
        number = value_match.group(1).replace(",", ".")
        currency = value_match.group(2) or ""
        return f"{number} {currency}".strip()

    unit_match = re.search(
        r"(?:to|à|a)\s+([A-Za-zÀ-ÿ]+)$",
        message.strip(),
        re.IGNORECASE,
    )

    if unit_match:
        return unit_match.group(1).strip()

    return None


def extract_requested_price(message: str):
    requested_value = extract_requested_value(message)

    if not requested_value:
        return None

    price_match = re.search(r"\d+(?:[.,]\d+)?", requested_value)

    if not price_match:
        return None

    try:
        return float(price_match.group(0).replace(",", "."))
    except ValueError:
        return None


def detect_odoo_action(message: str) -> str:
    text = message.lower()
    normalized = normalize_label(message)

    has_change = any(keyword in text for keyword in CHANGE_KEYWORDS)

    if is_odoo_document_details_request(message):
        return "document_details"

    if is_odoo_document_search_request(message):
        return "search_document"

    if any(
        phrase in normalized
        for phrase in [
            "combien de produits",
            "nombre de produits",
            "how many products",
            "inventory summary",
            "resume inventaire",
            "resume du stock",
        ]
    ):
        return "inventory_summary"

    if "price" in text or "prix" in text:
        return "change_price" if has_change else "check_price"

    if "unit" in text or "unité" in text or "unite" in text:
        return "change_unit" if has_change else "check_unit"

    if "stock" in text or "inventory" in text or "inventaire" in text:
        return "change_stock" if has_change else "check_stock"

    if "invoice" in text or "facture" in text:
        if any(word in text for word in ["create", "update", "delete", "modify", "créer", "creer", "modifier", "supprimer"]):
            return "modify_invoice"
        return "check_invoice"

    if "purchase" in text or "achat" in text or "commande" in text:
        if any(word in text for word in ["create", "créer", "creer"]):
            return "create_purchase_request"
        return "check_purchase"

    if "product" in text or "produit" in text or "details" in text or "détails" in text or "information" in text:
        return "check_product_details"

    return "odoo_status"


def extract_document_id(message: str):
    patterns = [
        r"Context:\s+the selected Odoo document ID is\s+(\d+)\b",
        r"\bdocument\s+id\s+(\d+)\b",
        r"\bid\s+du\s+document\s+(\d+)\b",
        r"\bid\s+document\s+(\d+)\b",
        r"\bd[ée]tails?\s+du\s+document\s+id\s+(\d+)\b",
        r"\bdetails?\s+of\s+document\s+id\s+(\d+)\b",
        r"\b(?:l['’]?)?id\s+(\d+)\b",
        r"\b(?:purchase\s+order|sale\s+order|invoice|facture|livraison|stock\s+picking|bon\s+de\s+livraison|bon\s+de\s+commande|commande\s+fournisseur)\s+id\s+(\d+)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)

        if match:
            return int(match.group(1))

    return None


def extract_context_document_field(message: str, field_label: str):
    match = re.search(
        rf"Context:\s+the selected Odoo document {field_label} is\s+([^\n]+)",
        message,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).strip().removesuffix(".").strip()

    return None


def extract_context_document_model(message: str):
    return extract_context_document_field(message, "model")


def extract_context_document_type(message: str):
    return extract_context_document_field(message, "type")


def extract_context_document_name(message: str):
    return extract_context_document_field(message, "name")


def extract_context_document_partner(message: str):
    return extract_context_document_field(message, "partner")


def extract_document_reference(message: str):
    patterns = [
        r"\b(BC-[A-Z0-9-]+)\b",
        r"\b(FAC/\d{4}/\d+)\b",
        r"\b(FNP/\d{4}/\d+)\b",
        r"\b(WH/(?:OUT|IN|PICK)/\d+)\b",
        r"\b(SO\d+|S\d{4,})\b",
        r"\b(PO\d+|P\d{4,})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)

        if match:
            return match.group(1)

    return None


def infer_document_type_from_message(message: str):
    normalized = normalize_label(message)

    if any(term in normalized for term in ["bon de commande", "commande fournisseur", "purchase order"]):
        return "purchase_order"

    if "purchase_order" in normalized:
        return "purchase_order"

    if "sale order" in normalized or "commande client" in normalized or "sale_order" in normalized:
        return "sale_order"

    if "facture" in normalized or "invoice" in normalized or "account_move" in normalized:
        return "invoice"

    if "bon de livraison" in normalized or "livraison" in normalized or "stock picking" in normalized or "delivery" in normalized or "stock_picking" in normalized:
        return "delivery"

    return None


def is_odoo_document_details_request(message: str):
    normalized = normalize_label(message)

    return (
        bool(extract_document_id(message))
        and any(
            term in normalized
            for term in [
                "document",
                "facture",
                "invoice",
                "livraison",
                "bon de livraison",
                "stock picking",
                "purchase order",
                "sale order",
                "bon de commande",
                "commande fournisseur",
            ]
        )
        or any(
            term in normalized
            for term in [
                "details du document id",
                "details of document id",
                "show details of document id",
                "details facture id",
                "details de la facture",
                "details facture",
                "details du bon de commande",
                "details commande fournisseur",
                "details du bon de livraison",
            ]
        )
    )


def is_odoo_document_search_request(message: str):
    normalized = normalize_label(message)

    return any(
        term in normalized
        for term in [
            "bon de commande",
            "commande fournisseur",
            "bon de livraison",
            "facture",
            "livraison",
            "stock picking",
            "purchase order",
            "sale order",
            "invoice",
        ]
    )


def _empty_parse() -> dict:
    return {
        "intent": "odoo",
        "action": "unknown",
        "business_action": "unknown",
        "risk": "low",
        "requires_approval": False,
        "target_model": None,
        "record_query": None,
        "document_query": None,
        "product_query": None,
        "field_label": None,
        "field_name": None,
        "new_value": None,
        "document_type": None,
        "document_reference": None,
        "document_id": None,
        "partner_name": None,
        "line_product": None,
        "field": None,
        "technical_field": None,
        "language": None,
        "needs_clarification": False,
        "clarification_reason": None,
        "confidence": 0.0,
        "parser_source": "local_rules",
        "parser_error": None,
    }


def _parse_toggle_boolean_fallback(message: str):
    patterns = [
        (
            r"^(?:cocher|activer|enable|check|tick)\s+(.+?)\s+(?:pour|for)\s+(.+)$",
            True,
        ),
        (
            r"^(?:décocher|decocher|désactiver|desactiver|disable|uncheck|untick)\s+(.+?)\s+(?:pour|for)\s+(.+)$",
            False,
        ),
    ]

    for pattern, new_value in patterns:
        match = re.search(pattern, message.strip(), re.IGNORECASE)

        if not match:
            continue

        return {
            "intent": "odoo",
            "action": "toggle_boolean_field",
            "risk": "medium",
            "requires_approval": True,
            "target_model": "account.analytic.account",
            "record_query": match.group(2).strip(),
            "field_label": match.group(1).strip(),
            "field_name": None,
            "new_value": new_value,
            "confidence": 0.85,
            "parser_source": "local_rules",
            "parser_error": None,
        }

    return None


def parse_odoo_action_deterministic(message: str) -> dict:
    toggle_parse = _parse_toggle_boolean_fallback(message)

    if toggle_parse:
        return toggle_parse

    action = detect_odoo_action(message)

    if action == "change_price":
        return {
            "intent": "odoo",
            "action": "change_price",
            "business_action": "update_product_price",
            "risk": "medium",
            "requires_approval": True,
            "target_model": "product.template",
            "record_query": extract_product_name(message),
            "field_label": "Prix de vente",
            "field_name": "list_price",
            "new_value": extract_requested_price(message),
            "confidence": 0.8,
            "parser_source": "local_rules",
            "parser_error": None,
        }

    if action in ["check_stock", "check_price", "check_unit", "check_product_details"]:
        return {
            "intent": "odoo",
            "action": "check_stock",
            "business_action": INTERNAL_TO_BUSINESS_ACTION.get(action, "check_product_stock"),
            "risk": "low",
            "requires_approval": False,
            "target_model": "product.template",
            "record_query": extract_product_name(message),
            "field_label": None,
            "field_name": None,
            "new_value": None,
            "confidence": 0.75,
            "parser_source": "local_rules",
            "parser_error": None,
        }

    if action == "inventory_summary":
        return {
            "intent": "odoo",
            "action": "inventory_summary",
            "business_action": "inventory_summary",
            "risk": "low",
            "requires_approval": False,
            "target_model": "product.template",
            "record_query": None,
            "field_label": None,
            "field_name": None,
            "new_value": None,
            "confidence": 0.75,
            "parser_source": "local_rules",
            "parser_error": None,
        }

    if action in {"search_document", "document_details"}:
        document_id = extract_document_id(message)
        document_reference = extract_document_reference(message)
        document_type = infer_document_type_from_message(message)
        context_document_type = extract_context_document_type(message)
        target_model = (
            DOCUMENT_TYPE_TO_MODEL.get(document_type or "")
            or extract_context_document_model(message)
            or DOCUMENT_TYPE_TO_MODEL.get(context_document_type or "")
        )

        return {
            "intent": "odoo_document_details" if action == "document_details" else "odoo_document_search",
            "action": action,
            "business_action": INTERNAL_TO_BUSINESS_ACTION.get(action, "document_details"),
            "risk": "low",
            "requires_approval": False,
            "target_model": target_model,
            "record_query": None,
            "document_query": None if document_id else (document_reference or extract_context_document_name(message) or message),
            "product_query": None,
            "field_label": None,
            "field_name": None,
            "new_value": None,
            "document_type": document_type or context_document_type or MODEL_TO_DOCUMENT_TYPE.get(target_model),
            "document_reference": document_reference,
            "document_id": document_id,
            "partner_name": extract_context_document_partner(message),
            "line_product": None,
            "field": None,
            "technical_field": None,
            "language": "fr" if re.search(r"\b(montre|détails|details|bon|commande|facture|livraison)\b", message, re.IGNORECASE) else None,
            "needs_clarification": False,
            "clarification_reason": None,
            "confidence": 0.82,
            "parser_source": "local_rules",
            "parser_error": None,
        }

    fallback = _empty_parse()
    fallback["action"] = action if action != "odoo_status" else "unknown"
    return fallback


def is_expected_arrival_date_request(message: str) -> bool:
    normalized = normalize_label(message)

    return any(
        phrase in normalized
        for phrase in [
            "expected arrival date",
            "expected arrival",
            "date d arrivee prevue",
            "arrivee prevue",
            "date prevue",
        ]
    )


DOCUMENT_TYPE_TO_MODEL = {
    "sale_order": "sale.order",
    "purchase_order": "purchase.order",
    "invoice": "account.move",
    "delivery": "stock.picking",
}

MODEL_TO_DOCUMENT_TYPE = {
    value: key
    for key, value in DOCUMENT_TYPE_TO_MODEL.items()
}

DOCUMENT_ACTION_ALIASES = {
    "update_line_price": "update_document_line",
    "update_line_quantity": "update_document_line",
    "update_partner": "update_document_partner",
    "read_document": "search_document",
}


def generic_entities(parsed: dict):
    entities = parsed.get("entities")
    return entities if isinstance(entities, dict) else {}


def parsed_value(parsed: dict, entities: dict, entity_key: str, legacy_key: str = ""):
    value = entities.get(entity_key)

    if value is not None:
        return value

    return parsed.get(legacy_key or entity_key)


def technical_field_for_document_action(
    document_type: str | None,
    field: str | None,
    technical_field: str | None,
):
    if technical_field:
        return technical_field

    if field == "expected_arrival_date" and document_type == "purchase_order":
        return "date_planned"

    if field == "order_date" and document_type in {"sale_order", "purchase_order"}:
        return "date_order"

    if field == "invoice_date" and document_type == "invoice":
        return "invoice_date"

    if field == "delivery_date" and document_type == "delivery":
        return "scheduled_date"

    if field == "price_unit":
        return "price_unit"

    if field == "quantity":
        return {
            "sale_order": "product_uom_qty",
            "purchase_order": "product_qty",
            "invoice": "quantity",
            "delivery": "product_uom_qty",
        }.get(document_type or "")

    if field == "partner":
        return "partner_id"

    return None


def document_action_for_field(action: str, field: str | None):
    action = BUSINESS_TO_INTERNAL_ACTION.get(action, action)
    action = DOCUMENT_ACTION_ALIASES.get(action, action)

    if action in {
        "update_document_date",
        "update_document_line",
        "update_document_partner",
        "search_document",
        "document_details",
        "product_search",
        "product_details",
        "inventory_summary",
        "unknown",
    }:
        return action

    if field in {
        "expected_arrival_date",
        "order_date",
        "invoice_date",
        "delivery_date",
    }:
        return "update_document_date"

    if field in {"price_unit", "quantity"}:
        return "update_document_line"

    if field == "partner":
        return "update_document_partner"

    return action


def business_action_for(parsed_action: str | None, internal_action: str | None):
    if parsed_action in SUPPORTED_ODOO_ACTIONS:
        return parsed_action

    if parsed_action == "read_document":
        return "document_search"

    if parsed_action in {"update_document_line"}:
        return "update_line_price"

    return INTERNAL_TO_BUSINESS_ACTION.get(internal_action or "", parsed_action or "unknown")


def normalize_openai_parse(
    parsed: dict,
    parser_source: str,
    parser_error=None,
    message: str = "",
) -> dict | None:
    if not isinstance(parsed, dict):
        return None

    entities = generic_entities(parsed)
    raw_action = parsed.get("action")
    document_type = parsed_value(parsed, entities, "document_type")
    business_field = parsed_value(parsed, entities, "field")
    action = document_action_for_field(raw_action, business_field)

    if action not in {
        "check_stock",
        "change_price",
        "toggle_boolean_field",
        "product_search",
        "product_details",
        "inventory_summary",
        "update_document_line",
        "update_document_partner",
        "update_document_date",
        "search_document",
        "document_details",
        "unknown",
    }:
        return None

    target_model = parsed.get("target_model") or DOCUMENT_TYPE_TO_MODEL.get(document_type or "")
    record_query = parsed.get("record_query") or parsed_value(parsed, entities, "product_name")
    document_query = (
        parsed.get("document_query")
        or parsed_value(parsed, entities, "document_reference")
    )
    product_query = (
        parsed.get("product_query")
        or parsed_value(parsed, entities, "line_product")
        or (
            parsed_value(parsed, entities, "product_name")
            if action in {"update_document_line"}
            else None
        )
    )
    new_value = parsed.get("new_value")

    if new_value is None:
        new_value = parsed_value(parsed, entities, "new_value")

    result = {
        "intent": parsed.get("intent") or "odoo",
        "action": action,
        "business_action": business_action_for(raw_action, action),
        "risk": parsed.get("risk") if parsed.get("risk") in {"low", "medium", "high"} else "low",
        "requires_approval": bool(parsed.get("requires_approval")),
        "target_model": target_model,
        "record_query": record_query,
        "document_query": document_query,
        "product_query": product_query,
        "field_label": parsed.get("field_label"),
        "field_name": (
            parsed.get("field_name")
            or technical_field_for_document_action(
                document_type,
                business_field,
                parsed.get("technical_field"),
            )
        ),
        "new_value": new_value,
        "confidence": parsed.get("confidence") if isinstance(parsed.get("confidence"), (int, float)) else 0.0,
        "parser_source": parser_source,
        "parser_error": parser_error,
        "document_type": document_type,
        "document_reference": document_query,
        "document_id": parsed_value(parsed, entities, "document_id"),
        "partner_name": parsed_value(parsed, entities, "partner_name"),
        "line_product": parsed_value(parsed, entities, "line_product") or parsed.get("product_query"),
        "field": business_field,
        "technical_field": parsed.get("technical_field"),
        "language": parsed.get("language"),
        "needs_clarification": bool(parsed.get("needs_clarification")),
        "clarification_reason": parsed.get("clarification_reason"),
        "entities": entities,
    }

    context_document_model = extract_context_document_model(message)
    context_document_type = extract_context_document_type(message)
    context_document_name = extract_context_document_name(message)
    context_document_partner = extract_context_document_partner(message)

    if action in {"search_document", "document_details"}:
        if result.get("document_type") == "unknown":
            result["document_type"] = None

        if not result.get("target_model"):
            result["target_model"] = (
                context_document_model
                or DOCUMENT_TYPE_TO_MODEL.get(context_document_type or "")
            )

        if not result.get("document_type"):
            result["document_type"] = (
                context_document_type
                or MODEL_TO_DOCUMENT_TYPE.get(result.get("target_model"))
            )

        if not result.get("document_query") and context_document_name:
            result["document_query"] = context_document_name
            result["document_reference"] = context_document_name

        if not result.get("partner_name") and context_document_partner:
            result["partner_name"] = context_document_partner

        if action == "document_details" and result.get("document_id") is not None:
            result["needs_clarification"] = False
            result["clarification_reason"] = None

    if action == "check_stock":
        result.update({
            "risk": "low",
            "requires_approval": False,
            "target_model": "product.template",
        })

    if action in {"product_search", "product_details"}:
        result.update({
            "risk": "low",
            "requires_approval": False,
            "target_model": "product.template",
        })

    if action == "inventory_summary":
        result.update({
            "risk": "low",
            "requires_approval": False,
            "target_model": "product.template",
        })

    if action == "change_price":
        result.update({
            "risk": "medium",
            "requires_approval": True,
            "target_model": "product.template",
            "field_label": result.get("field_label") or "Prix de vente",
            "field_name": "list_price",
        })

        try:
            result["new_value"] = float(result["new_value"])
        except (TypeError, ValueError):
            if result.get("needs_clarification"):
                result["new_value"] = None
            else:
                return None

    if action == "toggle_boolean_field":
        result.update({
            "risk": "medium",
            "requires_approval": True,
            "target_model": "account.analytic.account",
            "new_value": result.get("new_value") is True,
        })

    if action in {
        "update_document_line",
        "update_document_partner",
        "update_document_date",
    }:
        target_model = result.get("target_model")

        if target_model not in {
            "sale.order",
            "purchase.order",
            "stock.picking",
            "account.move",
        }:
            return None

        result["document_type"] = (
            result.get("document_type")
            or MODEL_TO_DOCUMENT_TYPE.get(target_model)
        )
        result["document_reference"] = (
            result.get("document_reference")
            or result.get("document_query")
        )
        result["line_product"] = (
            result.get("line_product")
            or result.get("product_query")
        )

        result.update({
            "risk": "high",
            "requires_approval": True,
        })

        field_name = result.get("field_name")

        if action == "update_document_line":
            if field_name == "quantity":
                field_name = {
                    "sale.order": "product_uom_qty",
                    "purchase.order": "product_qty",
                    "stock.picking": "product_uom_qty",
                    "account.move": "quantity",
                }.get(target_model)

            if (
                target_model == "stock.picking"
                and field_name not in {"product_uom_qty", "quantity"}
            ):
                return None

            allowed_fields = {
                "sale.order": {"price_unit", "product_uom_qty"},
                "purchase.order": {"price_unit", "product_qty"},
                "stock.picking": {"product_uom_qty"},
                "account.move": {"price_unit", "quantity"},
            }

            if field_name not in allowed_fields[target_model]:
                return None

            try:
                result["new_value"] = float(result["new_value"])
            except (TypeError, ValueError):
                result["new_value"] = None

        if action == "update_document_partner":
            field_name = "partner_id"

        if action == "update_document_date":
            allowed_date_fields = {
                "sale.order": "date_order",
                "purchase.order": "date_order",
                "account.move": "invoice_date",
                "stock.picking": "scheduled_date",
            }

            if (
                target_model == "purchase.order"
                and is_expected_arrival_date_request(message)
            ):
                allowed_date_fields["purchase.order"] = "date_planned"

            expected_field = allowed_date_fields[target_model]

            if (
                target_model == "purchase.order"
                and field_name == "date_planned"
            ):
                expected_field = "date_planned"

            if field_name not in {expected_field, None, "date_order"}:
                return None

            field_name = expected_field

        result["field_name"] = field_name
        result["technical_field"] = field_name

        if not result.get("field"):
            result["field"] = {
                "date_planned": "expected_arrival_date",
                "date_order": "order_date",
                "invoice_date": "invoice_date",
                "scheduled_date": "delivery_date",
                "price_unit": "price_unit",
                "product_qty": "quantity",
                "product_uom_qty": "quantity",
                "quantity": "quantity",
                "partner_id": "partner",
            }.get(field_name, "unknown")

    if action == "search_document":
        if result.get("target_model") not in {
            "sale.order",
            "purchase.order",
            "stock.picking",
            "account.move",
        }:
            return None

        result.update({
            "risk": "low",
            "requires_approval": False,
        })
        result["document_type"] = (
            result.get("document_type")
            or MODEL_TO_DOCUMENT_TYPE.get(result.get("target_model"))
        )

    if action == "document_details":
        if result.get("target_model") not in {
            "sale.order",
            "purchase.order",
            "stock.picking",
            "account.move",
        } and result.get("document_id") is None:
            return None

        result.update({
            "risk": "low",
            "requires_approval": False,
        })
        result["document_type"] = (
            result.get("document_type")
            or MODEL_TO_DOCUMENT_TYPE.get(result.get("target_model"))
        )

    return result


def parse_odoo_action_with_openai(message: str) -> dict:
    prompt = f"""
Parse this Odoo request into the required generic action schema.

Supported Odoo actions:
- check_product_stock: read stock for one named product.
- product_search: search one product or product family.
- product_details: read product details for one named product.
- inventory_summary: broad inventory count/summary questions such as "Combien de produits j’ai dans le stock ?" or "How many products do we have in inventory?". Do not treat these as product names.
- update_product_price: change the sale price of one product. Sensitive, requires approval.
- document_search: find a sale order, purchase order, invoice, or delivery.
- document_details: read details/lines for a sale order, purchase order, invoice, or delivery.
- update_document_date: change order/invoice/delivery/expected arrival dates. Sensitive, requires approval.
- update_line_price: change a document line unit price. Sensitive, requires approval.
- update_line_quantity: change a document line quantity. Sensitive, requires approval.
- update_partner: change a customer/supplier on a document. Sensitive, requires approval.
- unknown: request is Odoo-related but unsupported.
- needs_clarification: required fields are missing.

Return exactly the requested JSON structure:
- intent must be odoo for Odoo/ERP requests.
- action must be one supported Odoo action.
- language is fr, en, or mixed.
- requires_approval is true only for sensitive write actions.
- needs_clarification is true when a supported action is missing required entities.
- clarification_reason explains the missing data in the user's language.
- entities.product_name is for product actions.
- entities.document_type is sale_order, purchase_order, invoice, delivery, or unknown.
- entities.document_reference is exact document reference such as BC-BPP2600313, FNP/2026/04016, OL-BPT2600682.
- entities.document_id is the integer Odoo ID when the user says "ID 793".
- entities.partner_name is supplier/customer/vendor/client name when provided.
- entities.line_product is the line product for line price/quantity updates.
- entities.field is expected_arrival_date, order_date, invoice_date, delivery_date, price_unit, quantity, partner, or unknown.
- entities.new_value is the normalized target value. Convert French numeric dates like 15/06/2026 to 2026-06-15.
- entities.filename and entities.content are null for Odoo actions.

Document aliases:
- purchase_order: bon de commande fournisseur, commande fournisseur, achat, purchase order, supplier order, vendor order.
- sale_order: commande client, bon de commande client, commande de vente, devis, sale order, sales order, quotation.
- invoice: facture, facture client, facture fournisseur, invoice, vendor bill, customer invoice.
- delivery: bon de livraison, livraison, transfert, delivery order, delivery, transfer.

Field aliases:
- expected_arrival_date: arrivée prévue, date d’arrivée prévue, date prévue, date de réception prévue, expected arrival date, planned arrival date, expected receipt date.
- order_date: date de commande, order date.
- invoice_date: date de facture, invoice date.
- delivery_date: date de livraison, date prévue, delivery date, scheduled date.
- price_unit: prix, prix unitaire, prix de la ligne, price, unit price, line price.
- quantity: quantité, qté, quantity, qty.
- partner: client, fournisseur, customer, supplier, vendor.

User request:
{message}
"""

    response = generate_structured_response(
        prompt=prompt,
        schema=ODOO_ACTION_SCHEMA,
        system_prompt=(
            "You parse Odoo user requests. You never approve or execute actions. "
            "Return only structured data for local backend policy to enforce."
        ),
        model=os.getenv("OPENAI_ODOO_ASSIST_MODEL"),
    )

    parsed = response.get("parsed") if isinstance(response.get("parsed"), dict) else {}
    log_request({
        "event_type": "ai_model_call",
        "provider": "openai",
        "model": response.get("model") or os.getenv("OPENAI_ODOO_ASSIST_MODEL"),
        "agent": "odoo_agent",
        "status": "completed" if response.get("success") else "failed",
        "risk": "low",
        "approval_status": "not_required",
        "purpose": "odoo_structured_parse",
        "parser_action": parsed.get("action"),
        "parser_intent": parsed.get("intent"),
        "error": response.get("error"),
    })

    if response.get("success"):
        normalized = normalize_openai_parse(
            response.get("parsed"),
            parser_source="openai",
            message=message,
        )

        if (
            normalized
            and (
                normalized.get("action") != "unknown"
                or normalized.get("needs_clarification")
            )
        ):
            return normalized

    fallback = parse_odoo_action_deterministic(message)
    fallback["parser_source"] = "fallback"
    fallback["parser_error"] = response.get("error")
    return fallback


def unwrap_tool_response(tool_response):
    if not isinstance(tool_response, dict):
        return tool_response

    if tool_response.get("success") is True and "result" in tool_response:
        return tool_response["result"]

    return tool_response


def normalize_stock_result(raw_result: dict, action: str):
    raw_result = unwrap_tool_response(raw_result)

    if not isinstance(raw_result, dict):
        return {
            "action": action,
            "source": "unknown",
            "found": False,
            "raw": raw_result,
        }

    return {
        "action": action,
        "found": raw_result.get("found", False),
        "product": raw_result.get("product"),
        "product_name": raw_result.get("product_name") or raw_result.get("product"),
        "product_id": raw_result.get("product_id"),
        "metadata": raw_result.get("metadata") or {
            "product_name": raw_result.get("product_name") or raw_result.get("product"),
            "product_id": raw_result.get("product_id"),
            "source": raw_result.get("source", "real_odoo"),
        },
        "internal_reference": raw_result.get("internal_reference"),
        "available_stock": raw_result.get("stock_quantity"),
        "forecast_stock": raw_result.get("forecast_quantity"),
        "sale_price": raw_result.get("sale_price"),
        "unit": raw_result.get("unit"),
        "warehouse": raw_result.get("warehouse"),
        "source": raw_result.get("source", "real_odoo"),
    }


def check_stock(product_name: str):
    return unwrap_tool_response(
        execute_tool(
            "odoo_check_stock",
            product_name=product_name,
        )
    )


def search_product(product_name: str):
    return unwrap_tool_response(
        execute_tool(
            "odoo_search_product",
            product_name=product_name,
        )
    )


def search_customer(customer_name: str):
    return unwrap_tool_response(
        execute_tool(
            "odoo_search_customer",
            customer_name=customer_name,
        )
    )


def resolve_analytic_field_name(field_label: str):
    raw_result = unwrap_tool_response(
        execute_tool("odoo_list_analytic_boolean_fields")
    )

    if not isinstance(raw_result, dict):
        return None

    normalized_label = normalize_label(field_label)

    for field in raw_result.get("fields", []):
        if normalize_label(field.get("label", "")) == normalized_label:
            return field

    for field in raw_result.get("fields", []):
        if normalize_label(field.get("name", "")) == normalized_label:
            return field

    return None


def document_tool_name(parsed_action: dict):
    action = parsed_action.get("action")
    target_model = parsed_action.get("target_model")

    if action == "update_document_line":
        return {
            "sale.order": "odoo_update_sale_order_line",
            "purchase.order": "odoo_update_purchase_order_line",
            "account.move": "odoo_update_invoice_line",
            "stock.picking": "odoo_update_delivery_quantity",
        }.get(target_model)

    if action == "update_document_partner":
        return "odoo_update_document_partner"

    if action == "update_document_date":
        return "odoo_update_document_date"

    return None


def search_document_tool_name(target_model: str | None):
    return {
        "sale.order": "odoo_search_sale_order",
        "purchase.order": "odoo_search_purchase_order",
        "account.move": "odoo_search_invoice",
        "stock.picking": "odoo_search_delivery_order",
    }.get(target_model or "")


def document_details_tool_name(target_model: str | None):
    return {
        "sale.order": "odoo_get_sale_order_details",
        "purchase.order": "odoo_get_purchase_order_details",
        "account.move": "odoo_get_invoice_details",
        "stock.picking": "odoo_get_delivery_order_details",
    }.get(target_model or "")


def document_details_query_arg(target_model: str | None):
    return {
        "sale.order": "order_query",
        "purchase.order": "order_query",
        "account.move": "invoice_query",
        "stock.picking": "picking_query",
    }.get(target_model or "")


def wants_document_details(message: str) -> bool:
    normalized = normalize_label(message)

    return any(
        phrase in normalized
        for phrase in [
            "details",
            "detail",
            "detaille",
            "montre moi",
            "show me",
        ]
    )


def detect_document_response_focus(message: str) -> str | None:
    normalized = normalize_label(message)

    if any(
        phrase in normalized
        for phrase in [
            "son fournisseur",
            "le fournisseur",
            "qui est le fournisseur",
            "what is its supplier",
            "who is the supplier",
            "supplier",
        ]
    ):
        return "partner"

    if any(
        phrase in normalized
        for phrase in [
            "son statut",
            "le statut",
            "what is its status",
            "status",
            "statut",
        ]
    ):
        return "status"

    if any(
        phrase in normalized
        for phrase in [
            "sa date",
            "la date",
            "what is its date",
            "date",
        ]
    ):
        return "date"

    if any(
        phrase in normalized
        for phrase in [
            "ses articles",
            "ses lignes",
            "les articles",
            "les lignes",
            "show its lines",
            "its lines",
            "articles",
            "lignes",
            "lines",
        ]
    ):
        return "lines"

    return None


def document_partner_label(raw_result: dict, focus: str | None = None) -> str:
    metadata = raw_result.get("metadata") if isinstance(raw_result.get("metadata"), dict) else {}
    document_type = raw_result.get("document_type") or metadata.get("document_type")
    model_name = raw_result.get("document_model") or raw_result.get("model")

    if document_type == "sale_order" or model_name == "sale.order":
        return "Client"

    if focus == "partner":
        return "Fournisseur"

    return "Partenaire"


def _document_value(raw_result: dict, key: str):
    metadata = raw_result.get("metadata") if isinstance(raw_result.get("metadata"), dict) else {}
    document = raw_result.get("document") if isinstance(raw_result.get("document"), dict) else {}
    return raw_result.get(key) or metadata.get(key) or document.get(key)


def format_document_lines_summary(lines: list[dict]) -> str:
    if not lines:
        return "Articles : aucun article trouvé."

    formatted_lines = []

    for line in lines[:8]:
        product_name = line.get("product_name") or line.get("product") or line.get("name") or "Article"
        quantity = line.get("quantity")
        price = line.get("price_unit")
        parts = [str(product_name)]

        if quantity is not None:
            parts.append(f"quantité {quantity}")

        if price is not None:
            parts.append(f"prix unitaire {price}")

        formatted_lines.append("- " + " · ".join(parts))

    remaining_count = len(lines) - len(formatted_lines)

    if remaining_count > 0:
        formatted_lines.append(f"- ... (+{remaining_count} lignes)")

    return "Articles :\n" + "\n".join(formatted_lines)


def focused_document_response_message(message: str, raw_result: dict) -> tuple[str | None, str | None]:
    focus = detect_document_response_focus(message)

    if not focus:
        return None, None

    if focus == "partner":
        partner_name = (
            raw_result.get("partner_name")
            or raw_result.get("partner")
            or _document_value(raw_result, "partner_name")
            or _document_value(raw_result, "partner")
        )
        return f"{document_partner_label(raw_result, focus)} : {partner_name or 'non renseigné'}", focus

    if focus == "status":
        state = raw_result.get("state") or _document_value(raw_result, "state")
        return f"Statut : {state or 'non renseigné'}", focus

    if focus == "date":
        date_value = raw_result.get("date") or _document_value(raw_result, "date")
        return f"Date : {date_value or 'non renseignée'}", focus

    if focus == "lines":
        lines = raw_result.get("lines") or []
        return format_document_lines_summary(lines), focus

    return None, None


def document_type_label(model_name: str | None):
    return {
        "sale.order": "Bon de commande client",
        "purchase.order": "Bon de commande fournisseur",
        "account.move": "Facture",
        "stock.picking": "Bon de livraison",
    }.get(model_name or "", "Document Odoo")


def _missing_document_fields(parsed_action: dict):
    action = parsed_action.get("action")
    missing = []

    if not parsed_action.get("target_model"):
        missing.append("type de document")

    if not parsed_action.get("document_query") and not parsed_action.get("document_id"):
        missing.append("référence du document")

    if action == "update_document_line" and not parsed_action.get("product_query"):
        missing.append("produit")

    if action in {"update_document_line", "update_document_date"} and not parsed_action.get("field_name"):
        missing.append("champ à modifier")

    if parsed_action.get("new_value") in {None, ""}:
        missing.append("nouvelle valeur")

    return missing


def build_parser_debug(parsed_action: dict, action: str | None = None):
    product_name = (
        parsed_action.get("record_query")
        or parsed_action.get("product_query")
        or parsed_action.get("line_product")
    )

    return {
        "parser_source": parsed_action.get("parser_source") or "fallback",
        "language": parsed_action.get("language"),
        "parsed_action": (
            parsed_action.get("business_action")
            or business_action_for(parsed_action.get("action"), action)
        ),
        "document_type": parsed_action.get("document_type"),
        "document_reference": (
            parsed_action.get("document_reference")
            or parsed_action.get("document_query")
        ),
        "document_id": parsed_action.get("document_id"),
        "partner_name": parsed_action.get("partner_name"),
        "product_name": product_name,
        "line_product": (
            parsed_action.get("line_product")
            or parsed_action.get("product_query")
        ),
        "field": parsed_action.get("field"),
        "technical_field": (
            parsed_action.get("technical_field")
            or parsed_action.get("field_name")
        ),
        "new_value": parsed_action.get("new_value"),
        "requires_approval": bool(parsed_action.get("requires_approval")),
        "needs_clarification": bool(parsed_action.get("needs_clarification")),
    }


def with_parser_debug(response: dict, parsed_action: dict, action: str | None = None):
    debug = build_parser_debug(parsed_action, action)
    debug["requires_approval"] = bool(
        response.get("requires_approval") or response.get("approval_required")
    )
    debug["needs_clarification"] = response.get("status") == "needs_clarification"

    response.update(debug)
    response["parser_debug"] = debug

    return response


def build_needs_clarification_response(message: str, parsed_action: dict, missing_fields: list[str]):
    clarification_message = "Informations manquantes: " + ", ".join(missing_fields) + "."

    if missing_fields == ["nouveau prix"]:
        clarification_message = "Veuillez préciser le nouveau prix."

    return with_parser_debug({
        "intent": "odoo",
        "agent": "odoo_agent",
        "risk": "low",
        "requires_approval": False,
        "approval_required": False,
        "status": "needs_clarification",
        "message": clarification_message,
        "tool_used": None,
        "data": {
            "action": parsed_action.get("action"),
            "target_model": parsed_action.get("target_model"),
            "document_query": parsed_action.get("document_query"),
            "document_id": parsed_action.get("document_id"),
            "partner_name": parsed_action.get("partner_name"),
            "product_query": parsed_action.get("product_query"),
            "field_name": parsed_action.get("field_name"),
            "field": parsed_action.get("field"),
            "technical_field": parsed_action.get("technical_field"),
            "executed": False,
        },
        "result": {
            "user_message": message,
            "missing_fields": missing_fields,
        },
    }, parsed_action, parsed_action.get("action"))


def build_safe_unsupported_document_response(message: str, parsed_action: dict):
    return with_parser_debug({
        "intent": "odoo",
        "agent": "odoo_agent",
        "risk": "low",
        "requires_approval": False,
        "approval_required": False,
        "status": "unsupported",
        "message": (
            parsed_action.get("clarification_reason")
            or (
                "Je comprends votre demande, mais cette action n’est pas encore disponible "
                "dans les outils autorisés de l’orchestrateur. Vous pouvez me demander de "
                "consulter Odoo, modifier des données Odoo avec validation, diagnostiquer "
                "un problème IT ou accéder aux fichiers du serveur interne."
            )
        ),
        "tool_used": None,
        "data": {
            "action": parsed_action.get("action"),
            "document_type": parsed_action.get("document_type"),
            "document_query": parsed_action.get("document_query"),
            "document_id": parsed_action.get("document_id"),
            "field": parsed_action.get("field"),
            "technical_field": parsed_action.get("technical_field"),
            "executed": False,
        },
        "result": {
            "user_message": message,
        },
    }, parsed_action, parsed_action.get("action"))


def build_ambiguous_response(message: str, parsed_action: dict, candidates: list, entity_label: str = "résultats"):
    return with_parser_debug({
        "intent": "odoo",
        "agent": "odoo_agent",
        "risk": "low",
        "requires_approval": False,
        "approval_required": False,
        "status": "ambiguous",
        "message": (
            f"Plusieurs {entity_label} correspondent à votre demande. "
            "Veuillez préciser lequel utiliser."
        ),
        "tool_used": None,
        "candidates": candidates,
        "data": {
            "action": parsed_action.get("action"),
            "candidates": candidates,
            "executed": False,
        },
        "result": {
            "user_message": message,
            "candidates": candidates,
        },
    }, parsed_action, parsed_action.get("action"))


def build_document_metadata(parsed_action: dict):
    action = parsed_action.get("action")
    target_model = parsed_action.get("target_model")
    tool_name = document_tool_name(parsed_action)
    field_name = parsed_action.get("field_name")
    new_value = parsed_action.get("new_value")
    document_query = parsed_action.get("document_query")
    product_query = parsed_action.get("product_query")

    metadata = {
        "tool_name": tool_name,
        "target_model": target_model,
        "document_type": document_type_label(target_model),
        "document_type_key": parsed_action.get("document_type"),
        "document_reference": document_query,
        "document_id": parsed_action.get("document_id"),
        "partner_name": parsed_action.get("partner_name"),
        "document_query": document_query,
        "product_query": product_query,
        "line_product": parsed_action.get("line_product") or product_query,
        "field_name": field_name,
        "field": (
            "expected_arrival_date"
            if target_model == "purchase.order" and field_name == "date_planned"
            else parsed_action.get("field") or field_name
        ),
        "technical_field": parsed_action.get("technical_field") or field_name,
        "new_value": new_value,
        "executed": False,
    }

    if action == "update_document_partner":
        metadata["partner_query"] = str(new_value)

    if action == "update_document_date":
        metadata["date_field"] = field_name
        metadata["new_date"] = str(new_value)

    return metadata


def build_sensitive_approval_response(message: str, action: str, parsed_action: dict | None = None):
    parsed_action = parsed_action or {}
    risk = parsed_action.get("risk")

    if risk not in {"low", "medium", "high"}:
        risk = classify_risk(message)

    if action in {
        "change_price",
        "toggle_boolean_field",
        "update_document_line",
        "update_document_partner",
        "update_document_date",
    } and risk == "low":
        risk = "medium"

    product_name = parsed_action.get("record_query") or extract_product_name(message)
    requested_value = extract_requested_value(message)
    requested_price = (
        parsed_action.get("new_value")
        if action == "change_price" and parsed_action.get("new_value") is not None
        else extract_requested_price(message)
    )

    action_labels = {
        "change_price": "Modification du prix produit",
        "change_stock": "Modification du stock produit",
        "change_unit": "Modification de l’unité produit",
        "modify_invoice": "Action sensible sur facture",
        "create_purchase_request": "Création d’une demande d’achat",
        "toggle_boolean_field": "Modification d’un champ analytique",
        "update_document_line": "Modification d’une ligne de document",
        "update_document_partner": "Modification du client/fournisseur",
        "update_document_date": "Modification de date document",
    }

    title = action_labels.get(action, "Action Odoo sensible")
    metadata = {
        "product": product_name,
        "requested_value": requested_value,
        "executed": False,
        "simulation": True,
    }

    if action == "change_price":
        requested_value = requested_value or str(requested_price)
        resolved_product = unwrap_tool_response(
            execute_tool(
                "odoo_resolve_product_for_write",
                product_name=product_name,
            )
        )

        if isinstance(resolved_product, dict) and resolved_product.get("ambiguous"):
            return build_ambiguous_response(
                message,
                parsed_action,
                resolved_product.get("candidates", []),
                entity_label="produits",
            )

        if isinstance(resolved_product, dict) and resolved_product.get("found") is False:
            return with_parser_debug({
                "intent": "odoo",
                "agent": "odoo_agent",
                "risk": "low",
                "requires_approval": False,
                "approval_required": False,
                "status": "not_found",
                "message": "Produit introuvable dans Odoo. Aucune validation créée.",
                "tool_used": "odoo_resolve_product_for_write",
                "data": resolved_product,
                "result": resolved_product,
            }, parsed_action, action)

        metadata.update({
            "tool_name": "odoo_update_product_price",
            "product_name": product_name,
            "new_price": requested_price,
        })

    if action == "toggle_boolean_field":
        field_label = parsed_action.get("field_label")
        resolved_field = resolve_analytic_field_name(field_label or "")
        field_name = (
            parsed_action.get("field_name")
            or (resolved_field or {}).get("name")
        )
        field_label = (
            (resolved_field or {}).get("label")
            or field_label
        )
        requested_value = "true" if parsed_action.get("new_value") is True else "false"
        metadata.update({
            "tool_name": "odoo_update_analytic_boolean_field",
            "model": "account.analytic.account",
            "record_query": product_name,
            "field_label": field_label,
            "field_name": field_name,
            "new_value": parsed_action.get("new_value") is True,
        })

    if action in {
        "update_document_line",
        "update_document_partner",
        "update_document_date",
    }:
        missing_fields = _missing_document_fields(parsed_action)

        if missing_fields:
            return build_needs_clarification_response(
                message,
                parsed_action,
                missing_fields,
            )

        metadata = build_document_metadata(parsed_action)
        product_name = (
            parsed_action.get("document_query")
            or (
                f"ID {parsed_action.get('document_id')}"
                if parsed_action.get("document_id") is not None
                else None
            )
        )
        requested_value = parsed_action.get("new_value")
        title = action_labels.get(action, "Modification document Odoo")

    approval = create_approval(
        user_message=message,
        intent="odoo",
        selected_agent="odoo_agent",
        selected_model="policy_engine",
        action=action,
        risk=risk,
        title=title,
        description="Cette demande nécessite une validation humaine avant toute exécution dans Odoo.",
        source_system="odoo",
        entity_name=product_name,
        requested_change=requested_value,
        metadata=metadata,
    )

    log_request({
        "event_type": "approval_required",
        "title": title,
        "system": "odoo",
        "agent": "odoo_agent",
        "status": "pending_approval",
        "risk": risk,
        "approval_status": "pending",
        "approval_id": approval["id"],
        "user_message": message,
        "action": action,
        "product": product_name,
        "requested_value": requested_value,
        "target_model": parsed_action.get("target_model"),
        "document_query": parsed_action.get("document_query"),
        "document_id": parsed_action.get("document_id"),
        "partner_name": parsed_action.get("partner_name"),
        "product_query": parsed_action.get("product_query"),
        "field_name": metadata.get("field_name"),
        "field": metadata.get("field"),
        "technical_field": metadata.get("technical_field"),
        "parser_source": parsed_action.get("parser_source"),
        "executed": False,
        "message": "Action bloquée avant exécution. Validation humaine requise.",
    })

    return with_parser_debug({
        "intent": "odoo",
        "agent": "odoo_agent",
        "risk": risk,
        "requires_approval": True,
        "approval_required": True,
        "status": "pending_approval",
        "message": "Cette action nécessite une validation humaine avant exécution dans Odoo.",
        "approval_id": approval["id"],
        "tool_used": None,
        "data": {
            "action": action,
            "product": product_name,
            "requested_value": requested_value,
            "target_model": parsed_action.get("target_model"),
            "document_type": document_type_label(parsed_action.get("target_model")),
            "document_query": parsed_action.get("document_query"),
            "document_id": parsed_action.get("document_id"),
            "partner_name": parsed_action.get("partner_name"),
            "product_query": parsed_action.get("product_query"),
            "field_label": parsed_action.get("field_label"),
            "field_name": metadata.get("field_name"),
            "field": metadata.get("field"),
            "technical_field": metadata.get("technical_field"),
            "source": "approval_simulation",
            "executed": False,
        },
        "result": {
            "approval": approval,
        },
    }, parsed_action, action)


def run(message: str):
    parsed_action = parse_odoo_action_with_openai(message)
    action = parsed_action.get("action")
    business_action = parsed_action.get("business_action") or business_action_for(action, action)

    if (
        action == "document_details"
        and parsed_action.get("document_id") is not None
        and parsed_action.get("needs_clarification")
    ):
        parsed_action["needs_clarification"] = False
        parsed_action["clarification_reason"] = None

    if parsed_action.get("needs_clarification"):
        reason = parsed_action.get("clarification_reason")
        return build_needs_clarification_response(
            message,
            parsed_action,
            [reason] if reason else ["informations nécessaires"],
        )

    if action == "change_price" and parsed_action.get("new_value") in {None, ""}:
        return build_needs_clarification_response(
            message,
            parsed_action,
            ["nouveau prix"],
        )

    if action == "change_price" and not parsed_action.get("record_query"):
        return build_needs_clarification_response(
            message,
            parsed_action,
            ["nom du produit"],
        )

    if (
        action == "unknown"
        and parsed_action.get("parser_source") in {"openai", "test"}
    ):
        return build_safe_unsupported_document_response(message, parsed_action)

    if action == "unknown":
        action = detect_odoo_action(message)

    if action == "unknown":
        parsed_action["action"] = "unknown"
        parsed_action["business_action"] = "unknown"
        return build_safe_unsupported_document_response(message, parsed_action)

    sensitive_actions = {
        "change_price",
        "change_stock",
        "change_unit",
        "modify_invoice",
        "create_purchase_request",
        "toggle_boolean_field",
        "update_document_line",
        "update_document_partner",
        "update_document_date",
    }

    if action in sensitive_actions or requires_approval(message):
        return build_sensitive_approval_response(message, action, parsed_action)

    if (
        action in {"check_stock", "product_search", "product_details"}
        and not parsed_action.get("record_query")
        and not parsed_action.get("product_query")
    ):
        return build_needs_clarification_response(
            message,
            parsed_action,
            ["nom du produit"],
        )

    if action == "inventory_summary":
        raw_result = unwrap_tool_response(execute_tool("odoo_inventory_summary"))
        success = bool(isinstance(raw_result, dict) and raw_result.get("success"))

        log_request({
            "event_type": "odoo_read",
            "title": "Résumé inventaire Odoo",
            "system": "odoo",
            "agent": "odoo_agent",
            "status": "completed" if success else "failed",
            "risk": "low",
            "approval_status": "not_required",
            "user_message": message,
            "action": business_action,
            "message": "Résumé inventaire consulté sans modification.",
            "data": raw_result,
        })

        return with_parser_debug({
            "intent": parsed_action.get("intent") or "odoo_document_details",
            "agent": "odoo_agent",
            "risk": "low",
            "risk_level": "low",
            "requires_approval": False,
            "approval_required": False,
            "status": "completed" if success else "failed",
            "message": "Résumé inventaire consulté avec succès." if success else "Résumé inventaire indisponible.",
            "tool_used": "odoo_inventory_summary",
            "data": raw_result,
            "result": raw_result,
        }, parsed_action, action)

    if action in ["check_stock", "check_price", "check_unit", "check_product_details", "product_details"]:
        product_name = parsed_action.get("record_query") or extract_product_name(message)
        raw_result = check_stock(product_name)
        data = normalize_stock_result(raw_result, action)

        found = bool(data.get("found"))

        log_request({
            "event_type": "odoo_read",
            "title": "Consultation produit Odoo",
            "system": "odoo",
            "agent": "odoo_agent",
            "status": "completed" if found else "not_found",
            "risk": "low",
            "approval_status": "not_required",
            "user_message": message,
            "action": action,
            "product": product_name,
            "message": "Données produit consultées dans Odoo sans modification.",
            "data": data,
        })

        return with_parser_debug({
            "intent": parsed_action.get("intent") or "odoo_document_details",
            "agent": "odoo_agent",
            "risk": "low",
            "risk_level": "low",
            "requires_approval": False,
            "approval_required": False,
            "status": "completed" if found else "not_found",
            "message": "Données produit consultées avec succès." if found else "Produit introuvable dans Odoo.",
            "tool_used": "odoo_check_stock",
            "data": data,
            "result": raw_result,
        }, parsed_action, action)

    if action == "product_search":
        product_name = parsed_action.get("record_query") or extract_product_name(message)
        raw_result = search_product(product_name)
        found = bool(isinstance(raw_result, dict) and raw_result.get("found"))

        log_request({
            "event_type": "odoo_read",
            "title": "Recherche produit Odoo",
            "system": "odoo",
            "agent": "odoo_agent",
            "status": "completed" if found else "not_found",
            "risk": "low",
            "approval_status": "not_required",
            "user_message": message,
            "action": business_action,
            "product": product_name,
            "message": "Recherche produit consultative sans modification.",
            "data": raw_result,
        })

        return with_parser_debug({
            "intent": parsed_action.get("intent") or "odoo_document_details",
            "agent": "odoo_agent",
            "risk": "low",
            "risk_level": "low",
            "requires_approval": False,
            "approval_required": False,
            "status": "completed" if found else "not_found",
            "message": "Recherche produit exécutée." if found else "Produit introuvable dans Odoo.",
            "tool_used": "odoo_search_product",
            "data": raw_result,
            "result": raw_result,
        }, parsed_action, action)

    if action in {"search_document", "document_details"}:
        target_model = parsed_action.get("target_model")
        document_id = parsed_action.get("document_id")
        document_query = (
            parsed_action.get("document_query")
            or parsed_action.get("record_query")
            or (f"ID {document_id}" if document_id is not None else message)
        )
        tool_name = search_document_tool_name(target_model)

        if not tool_name and not (action == "document_details" and document_id is not None):
            return build_needs_clarification_response(
                message,
                parsed_action,
                ["type de document"],
            )

        if action == "document_details" and document_id is not None and not target_model:
            tool_name = "odoo_get_document_details_by_id"
            raw_result = unwrap_tool_response(
                execute_tool(tool_name, document_id=document_id)
            )
        elif action == "document_details" or wants_document_details(message):
            details_tool_name = document_details_tool_name(target_model)
            query_arg = document_details_query_arg(target_model)

            if details_tool_name and query_arg:
                tool_name = details_tool_name
                tool_kwargs = {query_arg: document_query}

                if document_id is not None:
                    tool_kwargs["document_id"] = document_id

                raw_result = unwrap_tool_response(execute_tool(tool_name, **tool_kwargs))
            else:
                raw_result = unwrap_tool_response(
                    execute_tool(tool_name, query=document_query)
                )
        else:
            raw_result = unwrap_tool_response(
                execute_tool(tool_name, query=document_query)
            )

        found = bool(isinstance(raw_result, dict) and raw_result.get("found"))
        ambiguous = bool(isinstance(raw_result, dict) and raw_result.get("ambiguous"))
        focused_message, response_focus = (
            focused_document_response_message(message, raw_result)
            if found and not ambiguous
            else (None, None)
        )

        log_request({
            "event_type": "odoo_read",
            "title": "Recherche document Odoo",
            "system": "odoo",
            "agent": "odoo_agent",
            "status": "completed" if found else "not_found",
            "risk": "low",
            "approval_status": "not_required",
            "user_message": message,
            "action": action,
            "target_model": target_model,
            "document_query": document_query,
            "message": "Recherche document consultative sans modification.",
            "data": raw_result,
        })

        return with_parser_debug({
            "intent": parsed_action.get("intent") or "odoo_document_details",
            "agent": "odoo_agent",
            "risk": "low",
            "risk_level": "low",
            "requires_approval": False,
            "approval_required": False,
            "status": "completed" if found else "not_found",
            "message": (
                focused_message
                or ("Document consulté avec succès." if found else "Document introuvable dans Odoo.")
            ),
            "response_focus": response_focus,
            "tool_used": tool_name,
            "data": raw_result,
            "result": raw_result,
        }, parsed_action, action)

    if "customer" in message.lower() or "client" in message.lower():
        raw_result = search_customer(message)

        log_request({
            "event_type": "odoo_read",
            "title": "Recherche client Odoo",
            "system": "odoo",
            "agent": "odoo_agent",
            "status": "completed",
            "risk": "low",
            "approval_status": "not_required",
            "user_message": message,
            "action": "search_customer",
            "message": "Recherche client consultative sans modification.",
        })

        return with_parser_debug({
            "intent": "odoo",
            "agent": "odoo_agent",
            "risk": "low",
            "requires_approval": False,
            "approval_required": False,
            "status": "completed",
            "message": "Recherche client exécutée.",
            "tool_used": "odoo_search_customer",
            "data": raw_result,
            "result": raw_result,
        }, parsed_action, action)

    raw_result = unwrap_tool_response(execute_tool("odoo_test_connection"))

    log_request({
        "event_type": "odoo_status",
        "title": "Vérification connexion Odoo",
        "system": "odoo",
        "agent": "odoo_agent",
        "status": "completed",
        "risk": "low",
        "approval_status": "not_required",
        "user_message": message,
        "action": "odoo_status",
        "message": "Statut de connexion Odoo consulté.",
    })

    return with_parser_debug({
        "intent": "odoo",
        "agent": "odoo_agent",
        "risk": "low",
        "requires_approval": False,
        "approval_required": False,
        "status": "completed",
        "message": "Statut Odoo consulté.",
        "tool_used": "odoo_test_connection",
        "data": raw_result,
        "result": raw_result,
    }, parsed_action, action)
