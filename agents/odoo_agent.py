import os
import re
import unicodedata

from models.openai_adapter import generate_structured_response
from orchestrator.tool_executor import execute_tool
from agents.odoo_read_agent import run_odoo_read_agent
from agents.odoo_response_synthesizer import (
    normalize_odoo_read_result,
    synthesize_odoo_read_response,
)
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
    "inventory_product_search",
    "product_details",
    "inventory_summary",
    "supplier_ranking",
    "customer_ranking",
    "odoo_status",
    "list_customer_invoices",
    "odoo_search_analytic_account",
    "odoo_get_analytic_account_details",
    "odoo_search_records",
    "odoo_generic_read",
    "odoo_get_record_details",
    "odoo_check_inventory",
    "odoo_update_field_request",
    "odoo_unsupported_action",
    "clarification_required",
    "toggle_boolean_field",
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
    "inventory_product_search": "inventory_product_search",
    "product_details": "product_details",
    "inventory_summary": "inventory_summary",
    "supplier_ranking": "supplier_ranking",
    "customer_ranking": "customer_ranking",
    "odoo_status": "odoo_status",
    "list_customer_invoices": "list_customer_invoices",
    "odoo_search_analytic_account": "odoo_search_analytic_account",
    "odoo_get_analytic_account_details": "odoo_get_analytic_account_details",
    "odoo_search_records": "odoo_search_records",
    "odoo_generic_read": "odoo_generic_read",
    "odoo_get_record_details": "odoo_get_record_details",
    "odoo_check_inventory": "odoo_check_inventory",
    "odoo_update_field_request": "odoo_update_field_request",
    "odoo_unsupported_action": "unknown",
    "clarification_required": "unknown",
    "toggle_boolean_field": "toggle_boolean_field",
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
    "toggle_boolean_field": "toggle_boolean_field",
    "search_document": "document_search",
    "document_details": "document_details",
    "update_document_date": "update_document_date",
    "update_document_partner": "update_partner",
    "inventory_summary": "inventory_summary",
    "supplier_ranking": "supplier_ranking",
    "customer_ranking": "customer_ranking",
    "odoo_status": "odoo_status",
    "list_customer_invoices": "list_customer_invoices",
    "odoo_search_analytic_account": "odoo_search_analytic_account",
    "odoo_get_analytic_account_details": "odoo_get_analytic_account_details",
    "odoo_search_records": "odoo_search_records",
    "odoo_generic_read": "odoo_generic_read",
    "odoo_get_record_details": "odoo_get_record_details",
    "odoo_check_inventory": "odoo_check_inventory",
    "odoo_update_field_request": "odoo_update_field_request",
    "product_search": "product_search",
    "inventory_product_search": "inventory_product_search",
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
                    "inventory_product_search",
                    "product_details",
                    "inventory_summary",
                    "supplier_ranking",
                    "customer_ranking",
                    "odoo_status",
                    "list_customer_invoices",
                    "odoo_search_records",
                    "odoo_generic_read",
                    "odoo_get_record_details",
                    "odoo_check_inventory",
                    "odoo_update_field_request",
                    "odoo_unsupported_action",
                    "clarification_required",
                    "toggle_boolean_field",
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
                            "phone",
                            "mobile",
                            "email",
                            "list_price",
                            "standard_price",
                            "x_studio_pointage",
                            "unknown",
                            None,
                        ],
                    },
                    "new_value": {
                        "type": ["string", "number", "boolean", "null"],
                    },
                    "model": {"type": ["string", "null"]},
                    "record_id": {"type": ["integer", "null"]},
                    "record_keyword": {"type": ["string", "null"]},
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
                    "model",
                    "record_id",
                    "record_keyword",
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

    quoted_match = (
        re.search(r"[\"“”]([^\"“”]{2,})[\"“”]", text)
        or re.search(r"(?<!\w)['’]([A-Za-z0-9][^'’]{1,80})['’](?!\w)", text)
    )

    if quoted_match:
        return clean_product_name(quoted_match.group(1))

    patterns = [
        r"(?:stock|inventory|inventaire)\s+(?:for|of|du|de|pour)\s+(.+)",
        r"(?:check|show|view|verify|get|consult|search)\s+(?:the\s+)?(?:stock|inventory|product|details|information)\s+(?:for|of)?\s*(.+)",
        r"(?:donne(?:-moi)?|donner|liste(?:-moi)?|lister|montre(?:-moi)?|affiche(?:-moi)?)\s+(?:le\s+|la\s+|les\s+|des\s+)?(?:détails|details|informations?|fiche)\s+(?:du|de\s+la|de\s+l['’]?|de|pour)\s+(?:produit|product|article)?\s*(.+)",
        r"(?:donne(?:-moi)?|donner|montre(?:-moi)?|affiche(?:-moi)?)\s+(?:le\s+|la\s+|les\s+)?(?:produit|product|article)\s+(.+)",
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
        r"^(check|show|view|get|verify|consult|search|find|give|list)\s+",
        "",
        fallback,
        flags=re.IGNORECASE,
    )

    fallback = re.sub(
        r"^(donne(?:-moi)?|donner|liste(?:-moi)?|lister|montre(?:-moi)?|affiche(?:-moi)?|vérifier|verifier|afficher|voir|consulter|chercher|rechercher)\s+",
        "",
        fallback,
        flags=re.IGNORECASE,
    )

    fallback = re.sub(
        r"^(stock|inventory|inventaire|product|produit|article|details|détails|fiche|informations?)\s+(for|of|de|du|pour)?\s*",
        "",
        fallback,
        flags=re.IGNORECASE,
    )

    return clean_product_name(fallback)


def is_inventory_product_existence_request(message: str) -> bool:
    normalized = normalize_label(message)
    has_inventory_context = any(
        term in normalized
        for term in [
            "inventory",
            "inventaire",
            "stock",
            "catalogue",
            "catalog",
        ]
    )
    has_product_context = any(
        term in normalized
        for term in [
            "product",
            "products",
            "produit",
            "produits",
            "article",
            "articles",
            "reference",
            "ref",
        ]
    )
    has_existence_intent = any(
        term in normalized
        for term in [
            "integr",
            "existe",
            "existent",
            "present",
            "disponible",
            "available",
            "found",
            "search",
            "chercher",
            "rechercher",
            "trouver",
            "matching",
            "correspond",
            "contient",
            "contiennent",
            "contenant",
            "categorie",
            "category",
            "famille",
            "keyword",
            "mot cle",
        ]
    )

    return (
        (
            has_inventory_context
            or ("odoo" in normalized and has_product_context)
            or (
                has_product_context
                and any(
                    term in normalized
                    for term in {
                        "contient",
                        "contiennent",
                        "contenant",
                        "matching",
                        "correspond",
                    }
                )
            )
        )
        and has_existence_intent
        and has_product_context
    )


def extract_inventory_product_keyword(message: str) -> str:
    text = message.strip()

    context_match = re.search(
        r"Context:\s+the referenced product is\s+(.+?)(?:\.|\n|$)",
        text,
        re.IGNORECASE,
    )

    if context_match:
        return clean_product_name(context_match.group(1))

    quoted_match = (
        re.search(r"[\"“”]([^\"“”]{2,})[\"“”]", text)
        or re.search(r"(?<!\w)['’]([A-Za-z0-9][^'’]{1,80})['’](?!\w)", text)
    )

    if quoted_match:
        return clean_inventory_keyword(quoted_match.group(1))

    patterns = [
        r"(?:matching|correspond(?:ant|ants)?\s+(?:à|a|to)|contenant|contient|contiennent|avec|keyword|mot\s+cl[ée]|cat[ée]gorie|category|famille)\s+(.+?)(?:\s+(?:dans|in|sur|on|est|sont|are|is)\b|[?.!,;:]|$)",
        r"(?:produits?|products?|articles?)\s+(?:de|du|d['’]|of|type|cat[ée]gorie|category|famille)\s+(.+?)(?:\s+(?:dans|in|sur|on|est|sont|are|is)\b|[?.!,;:]|$)",
        r"(?:produit|product|article)\s+(.+?)\s+(?:est|is|existe|exists|dans|in|int[ée]gr[ée]|integrated)",
        r"(?:est-ce que|est ce que|is|are|check if|verify if|v[ée]rifie si|verifie si)\s+(.+?)\s+(?:est|sont|is|are|existe|exists|int[ée]gr[ée]|integrated|pr[ée]sent|present)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            keyword = clean_inventory_keyword(match.group(1))
            if keyword:
                return keyword

    return clean_inventory_keyword(text)


def clean_inventory_keyword(value: str) -> str:
    normalized = re.sub(r"[?.!,;:]+", " ", value or "")
    normalized = re.sub(
        r"\b([A-Za-zÀ-ÿ]+)-(?:t-)?(?:il|ils|elle|elles|on|nous|vous)\b",
        r"\1",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()

    removable_terms = {
        "a",
        "about",
        "already",
        "are",
        "article",
        "articles",
        "available",
        "avec",
        "catalog",
        "catalogue",
        "category",
        "categorie",
        "catégorie",
        "check",
        "chercher",
        "client",
        "contact",
        "contient",
        "contiennent",
        "contenant",
        "customer",
        "dans",
        "de",
        "des",
        "du",
        "est",
        "est-ce",
        "est-ce-que",
        "existe",
        "existent",
        "for",
        "found",
        "fournisseur",
        "in",
        "integrated",
        "integre",
        "integré",
        "intégré",
        "integree",
        "integrees",
        "integres",
        "intégrés",
        "inventory",
        "inventaire",
        "is",
        "keyword",
        "la",
        "le",
        "les",
        "matching",
        "mot",
        "partner",
        "partenaire",
        "cle",
        "clé",
        "odoo",
        "of",
        "present",
        "produit",
        "produits",
        "product",
        "products",
        "rechercher",
        "search",
        "si",
        "sont",
        "stock",
        "the",
        "trouver",
        "un",
        "une",
        "verify",
        "verifie",
        "vérifie",
    }
    tokens = [
        token
        for token in normalized.split()
        if normalize_label(token) not in removable_terms
    ]

    return clean_product_name(" ".join(tokens))


def clean_record_keyword(value: str) -> str:
    normalized = re.sub(r"[?!,;:]+", " ", value or "")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(
        r"\s+(?:sur|dans|in|on)\s+odoo\b.*$",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"^(?:cherche|chercher|recherche|rechercher|trouve|trouver|find|search|show|montre|affiche|donne(?:-moi)?|liste|lister)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"^(?:le|la|les|un|une|des|the|a|an)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"^(?:client|customer|fournisseur|supplier|vendor|contact|partenaire|partner|produit|product|article)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"^(?:compte\s+analytique|analytic\s+account|account\s+analytic\s+account)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )

    return clean_product_name(normalized)


def is_vague_product_keyword(value: str) -> bool:
    normalized = normalize_label(value)

    return not normalized or len(normalized) < 2 or normalized in {
        "article",
        "articles",
        "categorie",
        "famille",
        "produit",
        "produits",
        "product",
        "products",
    }


ALLOWED_GENERIC_READ_MODELS = {
    "account.analytic.account",
    "account.bank.statement",
    "account.bank.statement.line",
    "account.journal",
    "hr.employee",
    "product.product",
    "product.template",
    "res.partner",
    "sale.order",
    "purchase.order",
    "account.move",
    "account.move.line",
    "stock.picking",
}

ALLOWED_GENERIC_WRITE_FIELDS = {
    "product.template": {"list_price", "standard_price"},
    "res.partner": {"phone", "mobile", "email"},
    "account.analytic.account": {"x_studio_pointage"},
}


def normalize_odoo_model(value: str | None) -> str | None:
    normalized = normalize_label(value or "")
    aliases = {
        "product": "product.product",
        "products": "product.product",
        "produit": "product.product",
        "produits": "product.product",
        "product product": "product.product",
        "product.product": "product.product",
        "product template": "product.template",
        "product.template": "product.template",
        "article": "product.product",
        "articles": "product.product",
        "partner": "res.partner",
        "contact": "res.partner",
        "client": "res.partner",
        "customer": "res.partner",
        "fournisseur": "res.partner",
        "supplier": "res.partner",
        "vendor": "res.partner",
        "res partner": "res.partner",
        "res.partner": "res.partner",
        "sale order": "sale.order",
        "sale.order": "sale.order",
        "commande client": "sale.order",
        "purchase order": "purchase.order",
        "purchase.order": "purchase.order",
        "commande fournisseur": "purchase.order",
        "bon de commande": "purchase.order",
        "invoice": "account.move",
        "facture": "account.move",
        "account move": "account.move",
        "account.move": "account.move",
        "delivery": "stock.picking",
        "livraison": "stock.picking",
        "stock picking": "stock.picking",
        "stock.picking": "stock.picking",
        "analytic account": "account.analytic.account",
        "compte analytique": "account.analytic.account",
        "account analytic account": "account.analytic.account",
        "account.analytic.account": "account.analytic.account",
    }

    return aliases.get(normalized)


def infer_generic_model(message: str, parsed_action: dict | None = None) -> str | None:
    parsed_action = parsed_action or {}
    entities = parsed_action.get("entities") if isinstance(parsed_action.get("entities"), dict) else {}
    explicit_model = (
        parsed_action.get("target_model")
        or parsed_action.get("model")
        or entities.get("model")
    )
    model = normalize_odoo_model(explicit_model)

    if model:
        return model

    normalized = normalize_label(message)

    if "pointage" in normalized or "analytique" in normalized or "analytic" in normalized:
        return "account.analytic.account"

    if any(term in normalized for term in ["client", "customer", "fournisseur", "supplier", "vendor", "contact", "partenaire", "partner"]):
        return "res.partner"

    if any(term in normalized for term in ["facture", "invoice"]):
        return "account.move"

    if any(term in normalized for term in ["livraison", "delivery", "stock picking"]):
        return "stock.picking"

    if any(term in normalized for term in ["commande fournisseur", "purchase order", "bon de commande"]):
        return "purchase.order"

    if any(term in normalized for term in ["commande client", "sale order", "devis"]):
        return "sale.order"

    if any(term in normalized for term in ["produit", "product", "article", "stock", "inventaire", "inventory", "prix", "price", "cout", "cost"]):
        return "product.template" if any(term in normalized for term in ["prix", "price", "cout", "cost"]) else "product.product"

    return None


def is_bank_accounting_read_request(message: str) -> bool:
    normalized = normalize_label(message)
    has_bank_accounting_subject = any(
        term in normalized
        for term in [
            "releve bancaire",
            "releves bancaires",
            "bank statement",
            "bank statements",
            "transaction bancaire",
            "transactions bancaires",
            "ecriture bancaire",
            "ecritures bancaires",
            "journal bancaire",
            "journaux bancaires",
            "bank transaction",
            "bank transactions",
            "accounting transaction",
            "accounting transactions",
        ]
    )
    has_read_intent = any(
        term in normalized
        for term in [
            "donne",
            "information",
            "informations",
            "liste",
            "lister",
            "montre",
            "recherche",
            "chercher",
            "trouve",
            "search",
            "show",
            "list",
            "find",
            "details",
            "detail",
        ]
    )

    return has_bank_accounting_subject and has_read_intent


def is_purchase_supplier_ranking_request(message: str) -> bool:
    normalized = normalize_label(message)
    supplier_terms = {
        "fournisseur",
        "fournisseurs",
        "supplier",
        "suppliers",
        "vendor",
        "vendors",
    }
    purchase_order_terms = {
        "bon de commande",
        "bons de commande",
        "commande fournisseur",
        "commandes fournisseur",
        "commandes fournisseurs",
        "purchase order",
        "purchase orders",
    }
    ranking_terms = {
        "apparait",
        "apparaissent",
        "classement",
        "count",
        "distribution",
        "frequence",
        "frequency",
        "le plus",
        "les plus",
        "most",
        "nombre",
        "par",
        "ranking",
        "repartition",
        "top",
    }

    return (
        any(term in normalized for term in supplier_terms)
        and any(term in normalized for term in purchase_order_terms)
        and any(term in normalized for term in ranking_terms)
    )


def is_sale_customer_ranking_request(message: str) -> bool:
    normalized = normalize_label(message)
    customer_terms = {
        "client",
        "clients",
        "customer",
        "customers",
    }
    sale_order_terms = {
        "commande client",
        "commandes client",
        "commande de vente",
        "commandes de vente",
        "sale order",
        "sale orders",
        "sales order",
        "sales orders",
    }
    ranking_terms = {
        "apparait",
        "apparaissent",
        "classement",
        "count",
        "distribution",
        "frequence",
        "frequency",
        "le plus",
        "les plus",
        "most",
        "nombre",
        "par",
        "ranking",
        "repartition",
        "top",
    }

    return (
        any(term in normalized for term in customer_terms)
        and any(term in normalized for term in sale_order_terms)
        and any(term in normalized for term in ranking_terms)
    )


def is_odoo_status_request(message: str) -> bool:
    normalized = normalize_label(message)
    if "odoo" not in normalized:
        return False

    business_action_signal = any(
        term in normalized
        for term in {
            "activer",
            "changer",
            "cocher",
            "coche",
            "compte analytique",
            "create",
            "creer",
            "delete",
            "inventaire",
            "modifier",
            "mettre a jour",
            "pointage",
            "price",
            "prix",
            "product",
            "produit",
            "stock",
            "supprimer",
            "update",
            "valider",
        }
    )

    if business_action_signal:
        return False

    return any(
        re.search(pattern, normalized)
        for pattern in (
            r"\bconnecte(?:e|s|es)?\b",
            r"\bconnexion\b",
            r"\bconnected\b",
            r"\bconnection\b",
            r"\bdisponible\b",
            r"\betat\b",
            r"\bstatus\b",
            r"\bstatut\b",
            r"\bonline\b",
            r"\baccessible\b",
        )
    )


def normalize_generic_field(model_name: str | None, field_value: str | None, message: str = "") -> str | None:
    normalized = normalize_label(field_value or "")
    text = normalize_label(message)

    if model_name == "product.template":
        if normalized in {"list_price", "prix", "prix de vente", "sale price", "price", "tarif"} or "prix" in text or "sale price" in text:
            return "list_price"
        if normalized in {"standard_price", "cout", "coût", "cost", "cost price"} or "standard price" in text or "cout" in text:
            return "standard_price"

    if model_name == "res.partner":
        if normalized in {"phone", "telephone", "téléphone", "tel"} or "telephone" in text or "téléphone" in text:
            return "phone"
        if normalized in {"mobile", "portable"} or "mobile" in text or "portable" in text:
            return "mobile"
        if normalized in {"email", "mail", "e-mail"} or "email" in text or "mail" in text:
            return "email"

    if model_name == "account.analytic.account":
        if normalized in {"x_studio_pointage", "pointage"} or "pointage" in text:
            return "x_studio_pointage"

    return None


def extract_generic_record_id(message: str, parsed_action: dict | None = None):
    parsed_action = parsed_action or {}
    entities = parsed_action.get("entities") if isinstance(parsed_action.get("entities"), dict) else {}
    record_id = parsed_action.get("record_id") or entities.get("record_id")

    if record_id is not None:
        try:
            return int(record_id)
        except (TypeError, ValueError):
            return None

    match = re.search(r"\b(?:id|identifiant)\s+(\d+)\b", message, re.IGNORECASE)
    return int(match.group(1)) if match else None


def extract_generic_keyword(message: str, parsed_action: dict | None = None) -> str:
    parsed_action = parsed_action or {}
    entities = parsed_action.get("entities") if isinstance(parsed_action.get("entities"), dict) else {}
    keyword = (
        parsed_action.get("record_query")
        or parsed_action.get("record_keyword")
        or parsed_action.get("document_query")
        or entities.get("record_keyword")
        or entities.get("product_name")
        or entities.get("partner_name")
        or entities.get("document_reference")
    )

    if keyword:
        return clean_record_keyword(str(keyword))

    patterns = [
        r"(?:client|customer|fournisseur|supplier|vendor|contact|partenaire|partner)\s+(.+?)(?:\s+(?:dans|in|sur|on|avec|to)\b|[?!,;:]|$)",
        r"(?:factures?|invoices?|bons?\s+de\s+commande|purchase\s+orders?|commandes?\s+fournisseurs?)\s+(?:de|du|d['’]|for)\s+(.+?)(?:\s+(?:dans|in|sur|on|avec|to)\b|[?!,;:]|$)",
        r"(?:nomm[ée]|appel[ée]|named|called)\s+(.+?)(?:\s+(?:dans|in|sur|on|avec|à|a|to)\b|[?!,;:]|$)",
        r"(?:pour|for|de|du|d['’]|produit|product|article)\s+(.+?)(?:\s+(?:dans|in|sur|on|avec|à|a|to)\b|[?!,;:]|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            candidate = clean_record_keyword(match.group(1))
            if candidate:
                return candidate

    return clean_record_keyword(message)


def coerce_generic_new_value(model_name: str, field_name: str, value):
    if value is None or value == "":
        return None

    if model_name == "product.template" and field_name in {"list_price", "standard_price"}:
        if isinstance(value, (int, float)):
            return float(value)
        match = re.search(r"\d+(?:[.,]\d+)?", str(value))
        return float(match.group(0).replace(",", ".")) if match else None

    if model_name == "account.analytic.account" and field_name == "x_studio_pointage":
        if isinstance(value, bool):
            return value
        normalized = normalize_label(str(value))
        if normalized in {"true", "vrai", "oui", "yes", "activer", "cocher", "active"}:
            return True
        if normalized in {"false", "faux", "non", "no", "desactiver", "decocher", "désactiver", "décocher"}:
            return False
        return None

    return str(value).strip()


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

    if is_odoo_status_request(message):
        return "odoo_status"

    if "price" in text or "prix" in text:
        return "change_price" if has_change else "check_price"

    if has_change and infer_generic_model(message):
        field_name = normalize_generic_field(infer_generic_model(message), None, message)
        if field_name:
            return "odoo_update_field_request"

    if is_purchase_supplier_ranking_request(message):
        return "supplier_ranking"

    if is_sale_customer_ranking_request(message):
        return "customer_ranking"

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

    if is_inventory_product_existence_request(message):
        return "inventory_product_search"

    if is_bank_accounting_read_request(message):
        return "bank_accounting_search"

    if any(term in normalized for term in ["details", "detail", "détails", "détail", "fiche", "information", "informations"]):
        inferred_model = infer_generic_model(message)
        if inferred_model in {"product.product", "product.template"}:
            return "check_product_details"
        if inferred_model:
            return "odoo_get_record_details"
        return "check_product_details"

    if any(term in normalized for term in ["cherche", "chercher", "recherche", "rechercher", "trouve", "trouver", "search", "find", "liste", "lister", "montre", "show"]):
        if infer_generic_model(message):
            return "odoo_search_records"
        return "product_search"

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


def extract_document_partner_query(message: str) -> str | None:
    patterns = [
        r"(?:factures?|invoices?|bons?\s+de\s+commande|purchase\s+orders?|commandes?\s+fournisseurs?|commandes?\s+client|sale\s+orders?|livraisons?|deliveries)\s+(?:de|du|d['’]|for)\s+(.+?)(?:\s+(?:dans|in|sur|on|avec|to)\b|[?!,;:]|$)",
        r"(?:pour|for)\s+(?:le\s+|la\s+|les\s+)?(?:client|customer|fournisseur|supplier|vendor|partenaire|partner)?\s*(.+?)(?:\s+(?:dans|in|sur|on|avec|to)\b|[?!,;:]|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)

        if match:
            keyword = clean_record_keyword(match.group(1))
            if keyword:
                return keyword

    return None


def infer_document_type_from_message(message: str):
    normalized = normalize_label(message)

    if any(term in normalized for term in ["bon de commande", "commande fournisseur", "purchase order"]):
        return "purchase_order"

    if any(term in normalized for term in ["bons de commande", "commandes fournisseur", "commandes fournisseurs"]):
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
            "bons de commande",
            "commande fournisseur",
            "commandes fournisseur",
            "commandes fournisseurs",
            "bon de livraison",
            "bons de livraison",
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
            r"^(?:coche|cocher|active|activer|enable|check|tick)\s+(.+?)\s+(?:pour|for)\s+(.+)$",
            True,
        ),
        (
            r"^(?:décoche|decoche|décocher|decocher|désactive|desactive|désactiver|desactiver|disable|uncheck|untick)\s+(.+?)\s+(?:pour|for)\s+(.+)$",
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
            "record_query": clean_record_keyword(match.group(2)),
            "field_label": clean_record_keyword(match.group(1)),
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

    if action == "odoo_status":
        return {
            "intent": "odoo",
            "action": "odoo_status",
            "business_action": "odoo_status",
            "risk": "low",
            "requires_approval": False,
            "target_model": None,
            "record_query": None,
            "field_label": None,
            "field_name": None,
            "new_value": None,
            "confidence": 0.9,
            "parser_source": "local_rules",
            "parser_error": None,
        }

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

    if action == "inventory_product_search":
        return {
            "intent": "odoo",
            "action": "inventory_product_search",
            "business_action": "inventory_product_search",
            "risk": "low",
            "requires_approval": False,
            "target_model": "product.template",
            "record_query": extract_inventory_product_keyword(message),
            "field_label": None,
            "field_name": None,
            "new_value": None,
            "confidence": 0.78,
            "parser_source": "local_rules",
            "parser_error": None,
        }

    if action == "product_search":
        return {
            "intent": "odoo",
            "action": "product_search",
            "business_action": "product_search",
            "risk": "low",
            "requires_approval": False,
            "target_model": "product.template",
            "record_query": extract_generic_keyword(message),
            "field_label": None,
            "field_name": None,
            "new_value": None,
            "confidence": 0.72,
            "parser_source": "local_rules",
            "parser_error": None,
        }

    if action == "bank_accounting_search":
        return {
            "intent": "odoo",
            "action": "bank_accounting_search",
            "business_action": "bank_accounting_search",
            "risk": "low",
            "requires_approval": False,
            "target_model": "account.bank.statement",
            "model": "account.bank.statement",
            "record_query": extract_generic_keyword(message),
            "field_label": None,
            "field_name": None,
            "new_value": None,
            "confidence": 0.76,
            "parser_source": "local_rules",
            "parser_error": None,
        }

    if action == "supplier_ranking":
        return {
            "intent": "odoo",
            "action": "supplier_ranking",
            "business_action": "supplier_ranking",
            "risk": "low",
            "requires_approval": False,
            "target_model": "purchase.order",
            "model": "purchase.order",
            "record_query": None,
            "field_label": "fournisseur",
            "field_name": "partner_id",
            "new_value": None,
            "confidence": 0.82,
            "parser_source": "local_rules",
            "parser_error": None,
        }

    if action == "customer_ranking":
        return {
            "intent": "odoo",
            "action": "customer_ranking",
            "business_action": "customer_ranking",
            "risk": "low",
            "requires_approval": False,
            "target_model": "sale.order",
            "model": "sale.order",
            "record_query": None,
            "field_label": "client",
            "field_name": "partner_id",
            "new_value": None,
            "confidence": 0.82,
            "parser_source": "local_rules",
            "parser_error": None,
        }

    if action in {"odoo_search_records", "odoo_get_record_details"}:
        model_name = infer_generic_model(message)
        return {
            "intent": "odoo",
            "action": action,
            "business_action": action,
            "risk": "low",
            "requires_approval": False,
            "target_model": model_name,
            "model": model_name,
            "record_id": extract_generic_record_id(message),
            "record_query": extract_generic_keyword(message),
            "field_label": None,
            "field_name": None,
            "new_value": None,
            "confidence": 0.72,
            "parser_source": "local_rules",
            "parser_error": None,
        }

    if action == "odoo_update_field_request":
        model_name = infer_generic_model(message)
        field_name = normalize_generic_field(model_name, None, message)
        new_value = extract_requested_value(message)
        coerced_value = (
            coerce_generic_new_value(model_name, field_name, new_value)
            if model_name and field_name
            else None
        )

        return {
            "intent": "odoo",
            "action": "odoo_update_field_request",
            "business_action": "odoo_update_field_request",
            "risk": "high",
            "requires_approval": True,
            "target_model": model_name,
            "model": model_name,
            "record_id": extract_generic_record_id(message),
            "record_query": extract_generic_keyword(message),
            "field_label": field_name,
            "field_name": field_name,
            "new_value": coerced_value,
            "confidence": 0.72,
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
            "document_query": None if document_id else (
                document_reference
                or extract_document_partner_query(message)
                or extract_context_document_name(message)
                or message
            ),
            "product_query": None,
            "field_label": None,
            "field_name": None,
            "new_value": None,
            "document_type": document_type or context_document_type or MODEL_TO_DOCUMENT_TYPE.get(target_model),
            "document_reference": document_reference,
            "document_id": document_id,
            "partner_name": extract_context_document_partner(message) or extract_document_partner_query(message),
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
        "inventory_product_search",
        "product_details",
        "inventory_summary",
        "odoo_search_records",
        "odoo_get_record_details",
        "odoo_check_inventory",
        "odoo_update_field_request",
        "clarification_required",
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
        "inventory_product_search",
        "product_details",
        "odoo_search_records",
        "odoo_get_record_details",
        "odoo_check_inventory",
        "odoo_update_field_request",
        "clarification_required",
        "inventory_summary",
        "bank_accounting_search",
        "supplier_ranking",
        "customer_ranking",
        "odoo_status",
        "update_document_line",
        "update_document_partner",
        "update_document_date",
        "search_document",
        "document_details",
        "unknown",
    }:
        return None

    target_model = (
        normalize_odoo_model(parsed.get("target_model") or parsed.get("model") or entities.get("model"))
        or DOCUMENT_TYPE_TO_MODEL.get(document_type or "")
    )
    if action == "toggle_boolean_field" and not target_model:
        target_model = "account.analytic.account"
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
        "record_query": record_query or parsed.get("record_keyword") or entities.get("record_keyword"),
        "record_id": parsed.get("record_id") or entities.get("record_id"),
        "model": target_model,
        "document_query": document_query,
        "product_query": product_query,
        "field_label": parsed.get("field_label") or (
            business_field if action == "toggle_boolean_field" else None
        ),
        "field_name": (
            parsed.get("field_name")
            or (
                normalize_generic_field(target_model, business_field, message)
                if action == "toggle_boolean_field"
                else None
            )
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

    if action in {"product_search", "inventory_product_search", "product_details"}:
        result.update({
            "risk": "low",
            "requires_approval": False,
            "target_model": "product.template",
        })

    if action == "bank_accounting_search":
        result.update({
            "risk": "low",
            "requires_approval": False,
            "target_model": result.get("target_model") or "account.bank.statement",
            "model": result.get("model") or result.get("target_model") or "account.bank.statement",
            "record_query": result.get("record_query") or extract_generic_keyword(message, result),
        })

    if action == "supplier_ranking":
        result.update({
            "risk": "low",
            "requires_approval": False,
            "target_model": "purchase.order",
            "model": "purchase.order",
            "field_name": "partner_id",
        })

    if action == "customer_ranking":
        result.update({
            "risk": "low",
            "requires_approval": False,
            "target_model": "sale.order",
            "model": "sale.order",
            "field_name": "partner_id",
        })

    if action == "odoo_status":
        result.update({
            "risk": "low",
            "requires_approval": False,
            "target_model": None,
            "record_query": None,
        })

    if action in {"odoo_search_records", "odoo_get_record_details", "odoo_check_inventory"}:
        target_model = infer_generic_model(message, result)

        if target_model not in ALLOWED_GENERIC_READ_MODELS:
            return None

        result.update({
            "risk": "low",
            "requires_approval": False,
            "target_model": target_model,
            "model": target_model,
            "record_query": result.get("record_query") or extract_generic_keyword(message, result),
        })

        if action == "odoo_check_inventory":
            result["action"] = "inventory_product_search"
            result["business_action"] = "inventory_product_search"

    if action == "odoo_update_field_request":
        target_model = infer_generic_model(message, result)
        field_name = normalize_generic_field(
            target_model,
            result.get("field_name") or result.get("field"),
            message,
        )

        if target_model not in ALLOWED_GENERIC_READ_MODELS or not field_name:
            return None

        new_value = coerce_generic_new_value(target_model, field_name, result.get("new_value"))

        result.update({
            "risk": "high",
            "requires_approval": True,
            "target_model": target_model,
            "model": target_model,
            "field_name": field_name,
            "technical_field": field_name,
            "new_value": new_value,
            "record_query": result.get("record_query") or extract_generic_keyword(message, result),
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
- inventory_product_search: check whether products matching a keyword/category are integrated in Odoo inventory. Read-only.
- product_details: read product details for one named product.
- inventory_summary: broad inventory count/summary questions such as "Combien de produits j’ai dans le stock ?" or "How many products do we have in inventory?". Do not treat these as product names.
- supplier_ranking: rank suppliers/vendors by purchase order count. Read-only.
- odoo_generic_read: broad read-only Odoo business data question when no specialized safe capability applies.
- update_product_price: change the sale price of one product. Sensitive, requires approval.
- toggle_boolean_field: toggle one approved boolean field on an analytic account. Sensitive, requires approval. Example classes include pointage/dotation on account.analytic.account, but the backend resolves the real safe field.
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
- For toggle_boolean_field, set entities.model to account.analytic.account, entities.record_keyword to the analytic account reference/name, entities.field to the requested boolean label or technical field, and entities.new_value to true/false.
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
    record = raw_result.get("record") if isinstance(raw_result.get("record"), dict) else {}
    return raw_result.get(key) or metadata.get(key) or document.get(key) or record.get(key)


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


def format_document_details_message(raw_result: dict) -> str | None:
    if not isinstance(raw_result, dict):
        return None

    reference = (
        _document_value(raw_result, "document_name")
        or _document_value(raw_result, "name")
        or _document_value(raw_result, "reference")
    )
    document_id = (
        _document_value(raw_result, "document_id")
        or _document_value(raw_result, "record_id")
        or _document_value(raw_result, "id")
    )
    model_name = _document_value(raw_result, "document_model") or _document_value(raw_result, "model")
    partner_name = (
        _document_value(raw_result, "partner_name")
        or _document_value(raw_result, "partner")
    )
    state = _document_value(raw_result, "state")
    date_value = _document_value(raw_result, "date")

    lines = raw_result.get("lines")
    if not isinstance(lines, list):
        document = raw_result.get("document") if isinstance(raw_result.get("document"), dict) else {}
        record = raw_result.get("record") if isinstance(raw_result.get("record"), dict) else {}
        lines = document.get("lines") if isinstance(document.get("lines"), list) else record.get("lines")

    details = []

    if reference:
        details.append(f"Référence : {reference}")

    if document_id is not None:
        details.append(f"ID : {document_id}")

    if model_name:
        details.append(f"Type : {document_type_label(model_name)}")

    if partner_name:
        details.append(f"{document_partner_label(raw_result)} : {partner_name}")

    if state:
        details.append(f"Statut : {state}")

    if date_value:
        details.append(f"Date : {date_value}")

    if not details and not lines:
        return None

    message_parts = []

    if details:
        message_parts.append("Document Odoo consulté :\n" + "\n".join(f"- {detail}" for detail in details))

    if lines:
        message_parts.append(format_document_lines_summary(lines))

    return "\n\n".join(message_parts)


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


def format_document_candidates_message(candidates: list[dict]) -> str | None:
    if not candidates:
        return None

    lines = [
        "Plusieurs documents correspondent à votre demande. Veuillez préciser lequel utiliser :"
    ]

    for candidate in candidates[:5]:
        parts = []
        record_id = candidate.get("record_id") or candidate.get("id")
        name = candidate.get("name") or candidate.get("document_name")
        model = candidate.get("model") or candidate.get("document_model")
        partner = candidate.get("partner") or candidate.get("partner_name")
        date_value = candidate.get("date")

        if record_id is not None:
            parts.append(f"ID {record_id}")

        if name:
            parts.append(str(name))

        label = document_type_label(model) if model else None

        if label:
            parts.append(label)

        if partner:
            parts.append(f"partenaire {partner}")

        if date_value:
            parts.append(f"date {date_value}")

        if parts:
            lines.append("- " + " · ".join(parts))

    remaining_count = len(candidates) - 5

    if remaining_count > 0:
        lines.append(f"- ... (+{remaining_count} autres documents)")

    return "\n".join(lines)


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
    unsupported_message = parsed_action.get("clarification_reason")
    audit_action = parsed_action.get("action") or "unsupported"

    if parsed_action.get("understood_write") or parsed_action.get("requires_approval"):
        unsupported_message = (
            "Je comprends la modification demandée, mais cette opération n'est pas "
            "encore connectée à un outil Odoo sécurisé."
        )
        audit_action = "unsupported_odoo_write"

    log_request({
        "event_type": "unsupported_action",
        "title": "Action Odoo non prise en charge",
        "system": "odoo",
        "agent": "odoo_agent",
        "status": "unsupported",
        "risk": parsed_action.get("risk", "low"),
        "approval_status": "not_required",
        "user_message": message,
        "action": audit_action,
        "target_model": parsed_action.get("target_model"),
        "message": "Action comprise mais aucun outil Odoo sécurisé ne permet l'exécution.",
    })

    return with_parser_debug({
        "intent": "odoo",
        "agent": "odoo_agent",
        "risk": "low",
        "requires_approval": False,
        "approval_required": False,
        "status": "unsupported",
        "message": (
            unsupported_message
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
        "odoo_update_field_request",
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
        "odoo_update_field_request": "Modification d’un champ Odoo",
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
        if not product_name:
            return build_needs_clarification_response(
                message,
                parsed_action,
                ["compte analytique"],
            )

        resolved_account = unwrap_tool_response(
            execute_tool(
                "odoo_resolve_analytic_account",
                record_query=product_name,
            )
        )

        if isinstance(resolved_account, dict) and resolved_account.get("ambiguous"):
            return build_ambiguous_response(
                message,
                parsed_action,
                resolved_account.get("candidates", []),
                entity_label="comptes analytiques",
            )

        if isinstance(resolved_account, dict) and resolved_account.get("found") is False:
            return with_parser_debug({
                "intent": "odoo",
                "agent": "odoo_agent",
                "risk": "low",
                "requires_approval": False,
                "approval_required": False,
                "status": "not_found",
                "message": "Aucun compte analytique correspondant trouvé dans Odoo. Aucune validation créée.",
                "tool_used": "odoo_resolve_analytic_account",
                "data": resolved_account,
                "result": resolved_account,
            }, parsed_action, action)

        if not isinstance(resolved_account, dict) or not resolved_account.get("record_id"):
            return build_safe_unsupported_document_response(
                message,
                {
                    **parsed_action,
                    "clarification_reason": "Action non disponible. Le compte analytique n’a pas pu être résolu avec un outil Odoo sécurisé.",
                },
            )

        product_name = (
            resolved_account.get("record")
            or resolved_account.get("record_name")
            or product_name
        )
        requested_value = "true" if parsed_action.get("new_value") is True else "false"
        metadata.update({
            "tool_name": "odoo_update_analytic_boolean_field",
            "model": "account.analytic.account",
            "record_query": resolved_account.get("record_query") or parsed_action.get("record_query"),
            "record_id": resolved_account.get("record_id"),
            "record_name": resolved_account.get("record_name") or resolved_account.get("record"),
            "record_code": resolved_account.get("record_code"),
            "field_label": field_label,
            "field_name": field_name,
            "new_value": parsed_action.get("new_value") is True,
        })

    if action == "odoo_update_field_request":
        target_model = parsed_action.get("target_model") or parsed_action.get("model")
        field_name = parsed_action.get("field_name") or parsed_action.get("technical_field")
        record_id = parsed_action.get("record_id")
        product_name = parsed_action.get("record_query") or extract_generic_keyword(message, parsed_action)
        requested_value = parsed_action.get("new_value")

        if target_model not in ALLOWED_GENERIC_READ_MODELS or field_name not in ALLOWED_GENERIC_WRITE_FIELDS.get(target_model, set()):
            return build_safe_unsupported_document_response(
                message,
                {
                    **parsed_action,
                    "clarification_reason": (
                        "Action non disponible. Cette modification Odoo n’est pas dans les champs autorisés."
                    ),
                },
            )

        if requested_value in {None, ""}:
            return build_needs_clarification_response(
                message,
                parsed_action,
                ["nouvelle valeur"],
            )

        prepared = unwrap_tool_response(
            execute_tool(
                "odoo_prepare_update_field",
                model_name=target_model,
                field_name=field_name,
                new_value=requested_value,
                record_id=record_id,
                keyword=product_name,
            )
        )

        if isinstance(prepared, dict) and prepared.get("ambiguous"):
            return build_ambiguous_response(
                message,
                parsed_action,
                prepared.get("candidates", []),
                entity_label="enregistrements",
            )

        if isinstance(prepared, dict) and prepared.get("found") is False:
            return with_parser_debug({
                "intent": "odoo",
                "agent": "odoo_agent",
                "risk": "low",
                "requires_approval": False,
                "approval_required": False,
                "status": "not_found",
                "message": "Aucun enregistrement correspondant trouvé dans Odoo.",
                "tool_used": "odoo_prepare_update_field",
                "data": prepared,
                "result": prepared,
            }, parsed_action, action)

        if not isinstance(prepared, dict) or not prepared.get("success"):
            return build_safe_unsupported_document_response(
                message,
                {
                    **parsed_action,
                    "clarification_reason": "Action non disponible. Cette demande n’a pas pu être préparée avec un outil Odoo sécurisé.",
                },
            )

        product_name = prepared.get("record_name") or product_name
        requested_value = prepared.get("new_value")
        metadata.update({
            "tool_name": "odoo_update_field",
            "target_model": target_model,
            "record_id": prepared.get("record_id"),
            "record_query": parsed_action.get("record_query"),
            "field_name": field_name,
            "old_value": prepared.get("old_value"),
            "new_value": requested_value,
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
            "record_id": metadata.get("record_id"),
            "field": metadata.get("field"),
            "technical_field": metadata.get("technical_field"),
            "source": "approval_simulation",
            "executed": False,
        },
        "result": {
            "approval": approval,
        },
    }, parsed_action, action)


def _semantic_read_values(classification: dict | None):
    if not isinstance(classification, dict):
        return {}

    values = {}
    semantic = classification.get("semantic_request")

    if isinstance(semantic, dict):
        entities = semantic.get("entities") if isinstance(semantic.get("entities"), dict) else {}
        parameters = semantic.get("parameters") if isinstance(semantic.get("parameters"), dict) else {}
        values.update(entities)
        values.update(parameters)

    entities = classification.get("entities") if isinstance(classification.get("entities"), dict) else {}
    parameters = classification.get("parameters") if isinstance(classification.get("parameters"), dict) else {}
    values.update(entities)
    values.update(parameters)
    return values


def build_odoo_read_plan(message: str, classification: dict | None = None):
    values = _semantic_read_values(classification)
    operation = values.get("operation") or "list"
    query = (
        values.get("query")
        or values.get("record_keyword")
        or values.get("keyword")
        or values.get("document_reference")
    )
    business_object = (
        values.get("business_object")
        or values.get("target")
        or values.get("model")
        or values.get("record_keyword")
        or message
    )
    semantic_model_hint = values.get("model_hint") or values.get("model_name") or values.get("model")

    if semantic_model_hint and "." not in str(semantic_model_hint):
        semantic_model_hint = None

    return {
        "operation": str(operation or "list").lower(),
        "business_object": str(business_object or "").strip(),
        "model_hint": semantic_model_hint,
        "model_candidates": values.get("model_candidates") or [],
        "filters": values.get("filters") or [],
        "requested_fields": values.get("requested_fields") or [],
        "sort": values.get("sort") or [],
        "limit": values.get("limit") or 10,
        "aggregate": values.get("aggregate") if isinstance(values.get("aggregate"), dict) else None,
        "record_id": values.get("record_id"),
        "query": query,
        "memory_followup": values.get("memory_followup") is True,
        "catalog_read": values.get("catalog_read") is True,
        "catalog_entry": values.get("catalog_entry"),
        "period": values.get("period") if isinstance(values.get("period"), dict) else None,
        "date_field_candidates": values.get("date_field_candidates") or [],
        "needs_clarification": values.get("needs_clarification") is True,
        "clarification_reason": values.get("clarification_reason"),
    }


def should_use_agentic_broad_read(message: str, classification: dict | None, parsed_action: dict):
    if not isinstance(classification, dict):
        return False

    is_odoo_target = (
        classification.get("domain") == "odoo"
        or classification.get("target_system") == "odoo"
        or classification.get("selected_agent") == "odoo_agent"
        or classification.get("agent") == "odoo_agent"
    )

    if not is_odoo_target:
        return False

    values = _semantic_read_values(classification)
    operation = str(values.get("operation") or "").lower()
    action = str(parsed_action.get("action") or "").lower()
    business_action = str(parsed_action.get("business_action") or "").lower()
    document_search_actions = {"search_document", "document_search"}
    stable_specialized_read_actions = {
        "check_product_stock",
        "check_stock",
        "document_details",
        "inventory_product_search",
        "product_details",
        "product_search",
        "read_document",
    }
    write_operations = {
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
        "write",
    }

    if parsed_action.get("requires_approval") or parsed_action.get("new_value") not in {None, ""}:
        return False

    if parsed_action.get("understood_write"):
        return False

    if action in document_search_actions or business_action in document_search_actions:
        if _has_specific_document_search_target(parsed_action, values, message, operation):
            return False

    if action in stable_specialized_read_actions or business_action in stable_specialized_read_actions:
        return False

    if operation in write_operations or action in write_operations:
        return False

    if values.get("field") or values.get("new_value") or values.get("new_price"):
        return False

    if values.get("partner_name") or values.get("document_reference") or values.get("document_id") or values.get("record_id"):
        return False

    read_operations = {
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

    if operation in read_operations:
        return True

    if values.get("business_object") or values.get("query") or values.get("record_keyword") or values.get("target"):
        return True

    return (
        parsed_action.get("parser_source") == "fallback"
        and parsed_action.get("record_query") == message
    )


def _has_specific_document_search_target(
    parsed_action: dict,
    semantic_values: dict,
    message: str,
    operation: str,
) -> bool:
    if parsed_action.get("document_id") or parsed_action.get("record_id"):
        return True

    if semantic_values.get("document_id") or semantic_values.get("record_id"):
        return True

    if (
        parsed_action.get("document_reference")
        or semantic_values.get("document_reference")
        or extract_document_reference(message)
    ):
        return True

    query = (
        parsed_action.get("document_query")
        or parsed_action.get("record_query")
        or semantic_values.get("query")
        or semantic_values.get("record_keyword")
    )
    normalized_query = normalize_label(str(query or ""))
    normalized_message = normalize_label(message)

    if not normalized_query or normalized_query == normalized_message:
        return False

    broad_document_labels = {
        normalize_label(str(value or ""))
        for value in (
            semantic_values.get("business_object"),
            semantic_values.get("document_type"),
            parsed_action.get("document_type"),
            parsed_action.get("target_model"),
        )
        if value
    }
    if normalized_query in broad_document_labels:
        return False

    if " " in normalized_query:
        return False

    broad_operations = {"count", "describe", "inspect", "list", "summary", "view"}
    if operation in broad_operations:
        return False

    return True


def _format_dynamic_field_label(field_name: str):
    labels = {
        "amount_total": "Montant",
        "code": "Code",
        "currency_id": "Devise",
        "date": "Date",
        "date_order": "Date",
        "display_name": "Nom",
        "end_date": "Fin",
        "name": "Nom",
        "partner_id": "Client/Fournisseur",
        "recurring_next_date": "Prochaine date",
        "recurring_total": "Récurrent",
        "stage_id": "Étape",
        "start_date": "Début",
        "state": "Statut",
        "status": "Statut",
    }
    return labels.get(field_name, field_name.replace("_", " ").title())


def _format_dynamic_record(record: dict):
    parts = []
    primary = record.get("display_name") or record.get("name") or record.get("reference") or record.get("ref")

    if primary:
        parts.append(str(primary))

    for field_name, value in record.items():
        if field_name in {"id", "model", "display_name", "name"}:
            continue
        if value is None or value == "" or value is False or value == []:
            continue

        parts.append(f"{_format_dynamic_field_label(field_name)}: {value}")

        if len(parts) >= 5:
            break

    if not parts:
        parts.append(f"ID {record.get('id')}")

    return " - ".join(parts)


def _synthesize_read_message(
    message: str,
    parsed_action: dict,
    raw_result: dict,
    *,
    operation: str | None = None,
    query_context: dict | None = None,
):
    normalized_result = normalize_odoo_read_result(
        raw_result if isinstance(raw_result, dict) else {"status": "failed", "error": "invalid_result"},
        operation=operation,
        query_context=query_context or {},
    )
    synthesis = synthesize_odoo_read_response(
        user_message=message,
        semantic_request=parsed_action,
        normalized_result=normalized_result,
    )
    return synthesis.get("response"), normalized_result, synthesis


def build_dynamic_read_response(message: str, parsed_action: dict, raw_result: dict):
    status = raw_result.get("status")
    read_plan = raw_result.get("read_plan") if isinstance(raw_result.get("read_plan"), dict) else {}
    business_object = (
        parsed_action.get("business_object")
        or (parsed_action.get("entities") or {}).get("business_object")
        or read_plan.get("business_object")
    )

    if business_object == "employees":
        operation = read_plan.get("operation") or parsed_action.get("operation")
        count = raw_result.get("record_count") or 0
        model_name = raw_result.get("model")

        if operation == "count" and raw_result.get("success") and model_name == "hr.employee":
            return with_parser_debug({
                "intent": "odoo",
                "agent": "odoo_agent",
                "risk": "low",
                "risk_level": "low",
                "requires_approval": False,
                "approval_required": False,
                "status": "completed",
                "message": f"Il y a {count} employés actifs enregistrés dans Odoo.",
                "tool_used": "odoo_generic_read",
                "target_system": "odoo",
                "odoo_model": "hr.employee",
                "record_count": count,
                "data": raw_result,
                "result": raw_result,
            }, parsed_action, "odoo_count_records")

        if operation == "count" and raw_result.get("success") and model_name == "res.partner":
            return with_parser_debug({
                "intent": "odoo",
                "agent": "odoo_agent",
                "risk": "low",
                "risk_level": "low",
                "requires_approval": False,
                "approval_required": False,
                "status": "completed",
                "message": (
                    "Je n’ai pas accès au module Employés dans Odoo. "
                    f"Le comptage disponible porte sur les contacts Odoo: {count} contacts. "
                    "Ce n’est pas forcément l’effectif réel."
                ),
                "tool_used": "odoo_generic_read",
                "target_system": "odoo",
                "odoo_model": "res.partner",
                "record_count": count,
                "data": raw_result,
                "result": raw_result,
            }, parsed_action, "odoo_count_records")

        if status in {"not_found", "rejected", "failed"} and not raw_result.get("model"):
            return with_parser_debug({
                "intent": "odoo",
                "agent": "odoo_agent",
                "risk": "low",
                "risk_level": "low",
                "requires_approval": False,
                "approval_required": False,
                "status": "needs_clarification",
                "message": (
                    "Je n’ai pas accès au module Employés dans Odoo. "
                    "Je peux vérifier les utilisateurs ou les contacts, mais ce ne sera pas forcément l’effectif réel."
                ),
                "tool_used": "odoo_generic_read",
                "target_system": "odoo",
                "odoo_model": None,
                "record_count": 0,
                "data": raw_result,
                "result": raw_result,
            }, parsed_action, "odoo_count_records")

    if status == "ambiguous":
        return build_ambiguous_response(
            message,
            parsed_action,
            raw_result.get("candidates", []),
            entity_label="types d’enregistrements Odoo",
        )

    if status in {"not_found", "rejected", "failed"} and not raw_result.get("model"):
        return with_parser_debug({
            "intent": "odoo",
            "agent": "odoo_agent",
            "risk": "low",
            "risk_level": "low",
            "requires_approval": False,
            "approval_required": False,
            "status": "unsupported" if status == "rejected" else "not_found",
            "message": "Je n’ai pas trouvé de modèle Odoo sécurisé correspondant à cette demande.",
            "tool_used": "odoo_generic_read",
            "target_system": "odoo",
            "odoo_model": None,
            "record_count": 0,
            "data": raw_result,
            "result": raw_result,
        }, parsed_action, "odoo_generic_read")

    operation = (raw_result.get("read_plan") or {}).get("operation")
    count = raw_result.get("record_count") or 0
    message_text, normalized_read, synthesis = _synthesize_read_message(
        message,
        parsed_action,
        raw_result,
        operation=operation,
        query_context=raw_result.get("read_plan") or {},
    )

    return with_parser_debug({
        "intent": "odoo",
        "agent": "odoo_agent",
        "risk": "low",
        "risk_level": "low",
        "requires_approval": False,
        "approval_required": False,
        "status": "completed" if raw_result.get("success") else "not_found",
        "message": message_text,
        "tool_used": "odoo_generic_read",
        "target_system": "odoo",
        "odoo_model": raw_result.get("model"),
        "record_count": count,
        "normalized_read_result": normalized_read,
        "response_synthesis": synthesis,
        "data": raw_result,
        "result": raw_result,
    }, parsed_action, "odoo_generic_read")


def execute_analytic_account_read(message: str, parsed_action: dict):
    action = parsed_action.get("action")
    record_query = (
        parsed_action.get("record_query")
        or parsed_action.get("query")
        or extract_generic_keyword(message, parsed_action)
    )

    if not record_query:
        return build_needs_clarification_response(
            message,
            parsed_action,
            ["référence ou nom du compte analytique"],
        )

    tool_name = (
        "odoo_get_analytic_account_details"
        if action == "odoo_get_analytic_account_details"
        else "odoo_search_analytic_account"
    )
    operation = "read" if tool_name == "odoo_get_analytic_account_details" else "search"
    raw_result = unwrap_tool_response(
        execute_tool(
            tool_name,
            record_query=record_query,
            record_id=parsed_action.get("record_id"),
            limit=6,
        )
    )
    found = bool(isinstance(raw_result, dict) and raw_result.get("found"))
    ambiguous = bool(isinstance(raw_result, dict) and raw_result.get("ambiguous"))
    message_text, normalized_read, synthesis = _synthesize_read_message(
        message,
        parsed_action,
        raw_result if isinstance(raw_result, dict) else {},
        operation=operation,
        query_context={
            "operation": operation,
            "model": "account.analytic.account",
            "query": record_query,
            "business_object": "compte analytique",
        },
    )

    log_request({
        "event_type": "odoo_read",
        "title": "Lecture compte analytique Odoo",
        "system": "odoo",
        "agent": "odoo_agent",
        "status": "completed" if found and not ambiguous else "not_found",
        "risk": "low",
        "approval_status": "not_required",
        "user_message": message,
        "action": action,
        "target_model": "account.analytic.account",
        "message": "Compte analytique consulté sans modification.",
        "data": raw_result,
    })

    return with_parser_debug({
        "intent": parsed_action.get("intent") or "odoo_analytic_account_search",
        "agent": "odoo_agent",
        "risk": "low",
        "risk_level": "low",
        "requires_approval": False,
        "approval_required": False,
        "status": "needs_clarification" if ambiguous else ("completed" if found else "not_found"),
        "message": (
            "Plusieurs comptes analytiques correspondent à votre demande. Veuillez préciser lequel choisir."
            if ambiguous
            else message_text
        ),
        "tool_used": tool_name,
        "capability": (
            "odoo.analytic_account_details"
            if tool_name == "odoo_get_analytic_account_details"
            else "odoo.analytic_account_search"
        ),
        "target_system": "odoo",
        "odoo_model": "account.analytic.account",
        "record_query": record_query,
        "normalized_read_result": normalized_read,
        "response_synthesis": synthesis,
        "data": raw_result,
        "result": raw_result,
        "candidates": raw_result.get("candidates", []) if isinstance(raw_result, dict) else [],
    }, parsed_action, action)


def _customer_invoice_period_text(filters: list) -> str:
    start_date = None
    end_date = None

    for item in filters or []:
        if not isinstance(item, dict):
            continue
        if item.get("field") != "invoice_date":
            continue
        if item.get("operator") == ">=":
            start_date = item.get("value")
        if item.get("operator") == "<=":
            end_date = item.get("value")

    if start_date and end_date:
        month_label = _whole_month_label(start_date, end_date)
        if month_label:
            return month_label
        return f"du {start_date} au {end_date}"

    return "sur la période demandée"


def _whole_month_label(start_date: str, end_date: str) -> str | None:
    month_names = {
        1: "janvier",
        2: "février",
        3: "mars",
        4: "avril",
        5: "mai",
        6: "juin",
        7: "juillet",
        8: "août",
        9: "septembre",
        10: "octobre",
        11: "novembre",
        12: "décembre",
    }
    start_match = re.fullmatch(r"(\d{4})-(\d{2})-01", str(start_date))
    end_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(end_date))

    if not start_match or not end_match:
        return None

    year = int(start_match.group(1))
    month = int(start_match.group(2))
    end_year = int(end_match.group(1))
    end_month = int(end_match.group(2))
    end_day = int(end_match.group(3))

    if year != end_year or month != end_month or month not in month_names:
        return None

    expected_last_day = {
        1: 31,
        2: 29 if (year % 400 == 0 or (year % 4 == 0 and year % 100 != 0)) else 28,
        3: 31,
        4: 30,
        5: 31,
        6: 30,
        7: 31,
        8: 31,
        9: 30,
        10: 31,
        11: 30,
        12: 31,
    }[month]

    if end_day != expected_last_day:
        return None

    return f"{month_names[month]} {year}"


def _format_customer_invoice_summary(raw_result: dict, filters: list) -> str:
    records = raw_result.get("records") if isinstance(raw_result.get("records"), list) else []
    posted_requested = any(
        isinstance(item, dict)
        and item.get("field") == "state"
        and item.get("value") == "posted"
        for item in filters or []
    )
    status_text = " validée" if posted_requested else ""
    period_text = _customer_invoice_period_text(filters)

    if not records:
        return f"Aucune facture client{status_text} trouvée pour {period_text}."

    title = "Factures clients validées" if posted_requested else "Factures clients"
    lines = [f"{title} trouvées {period_text}:"]

    for record in records[:10]:
        reference = record.get("reference") or record.get("document") or record.get("name") or f"ID {record.get('id')}"
        partner = record.get("partner") or "client non renseigné"
        date = record.get("date") or "date non renseignée"
        amount = record.get("amount_total")
        currency = record.get("currency") or ""
        status = record.get("status") or "statut non renseigné"
        payment_state = record.get("payment_state") or ""
        amount_text = (
            f"{amount} {currency}".strip()
            if amount not in (None, "")
            else "montant non renseigné"
        )
        payment_text = f", paiement: {payment_state}" if payment_state else ""
        lines.append(f"- {reference} — {partner} — {date} — {amount_text} — statut: {status}{payment_text}")

    return "\n".join(lines)


def execute_customer_invoice_list(message: str, parsed_action: dict):
    filters = parsed_action.get("filters") if isinstance(parsed_action.get("filters"), list) else []
    raw_result = unwrap_tool_response(
        execute_tool(
            "odoo_list_customer_invoices",
            filters=filters,
            limit=parsed_action.get("limit") or 10,
        )
    )
    found = bool(isinstance(raw_result, dict) and raw_result.get("found"))
    message_text = _format_customer_invoice_summary(
        raw_result if isinstance(raw_result, dict) else {},
        filters,
    )

    log_request({
        "event_type": "odoo_read",
        "title": "Lecture factures clients Odoo",
        "system": "odoo",
        "agent": "odoo_agent",
        "status": "completed" if found else "not_found",
        "risk": "low",
        "approval_status": "not_required",
        "user_message": message,
        "action": "list_customer_invoices",
        "target_model": "account.move",
        "message": "Factures clients consultées sans modification.",
        "data": raw_result,
    })

    return with_parser_debug({
        "intent": "odoo_customer_invoice_list",
        "agent": "odoo_agent",
        "risk": "low",
        "risk_level": "low",
        "requires_approval": False,
        "approval_required": False,
        "status": "completed" if found else "not_found",
        "message": message_text,
        "tool_used": "odoo_list_customer_invoices",
        "capability": "odoo.customer_invoice_list",
        "target_system": "odoo",
        "odoo_model": "account.move",
        "selected_model": "account.move",
        "filters": filters,
        "domain_used": raw_result.get("domain_used") if isinstance(raw_result, dict) else [],
        "fields_used": raw_result.get("fields_used") if isinstance(raw_result, dict) else [],
        "count_returned": raw_result.get("record_count") if isinstance(raw_result, dict) else 0,
        "failure_reason": raw_result.get("failure_reason") if isinstance(raw_result, dict) else "invalid_result",
        "data": raw_result,
        "result": raw_result,
    }, parsed_action, "list_customer_invoices")


def format_bank_accounting_summary(raw_result: dict, keyword: str) -> str:
    failure_reason = raw_result.get("failure_reason")

    if failure_reason in {"missing_model", "unsupported_by_policy"}:
        return raw_result.get("message") or (
            "Odoo est connecté, mais le modèle nécessaire aux relevés bancaires "
            "n’est pas disponible dans cette base ou n’est pas autorisé par la politique de lecture."
        )

    if failure_reason == "missing_field":
        return raw_result.get("message") or (
            "Le modèle existe, mais les champs nécessaires pour filtrer par banque/date "
            "ne sont pas disponibles."
        )

    if failure_reason == "odoo_unavailable":
        return "Odoo n’est pas disponible pour cette recherche pour le moment."

    if failure_reason == "no_records" or not raw_result.get("found"):
        return raw_result.get("message") or (
            f"Aucun relevé ou transaction bancaire correspondant à {keyword} "
            "sur la période demandée n’a été trouvé."
        )

    records = raw_result.get("records") if isinstance(raw_result.get("records"), list) else []
    lines = [
        (
            f"{raw_result.get('record_count', len(records))} relevé(s)/transaction(s) "
            f"trouvé(s) dans Odoo"
            f" via {raw_result.get('selected_model') or raw_result.get('model')}."
        )
    ]

    for record in records[:10]:
        if not isinstance(record, dict):
            continue

        parts = [
            str(record.get("document") or record.get("reference") or f"ID {record.get('id')}").strip(),
        ]

        for label, key in [
            ("date", "date"),
            ("journal", "journal"),
            ("partenaire", "partner"),
            ("montant", "amount"),
            ("solde", "balance"),
            ("statut", "status"),
        ]:
            value = record.get(key)

            if value not in {None, ""}:
                parts.append(f"{label}: {value}")

        lines.append("- " + " | ".join(parts))

    return "\n".join(lines)


def execute_bank_accounting_search(message: str, parsed_action: dict):
    keyword = parsed_action.get("record_query") or extract_generic_keyword(message, parsed_action)
    raw_result = unwrap_tool_response(
        execute_tool(
            "odoo_search_bank_accounting",
            keyword=keyword,
            message=message,
            limit=10,
        )
    )

    if not isinstance(raw_result, dict):
        raw_result = {
            "success": False,
            "status": "failed",
            "found": False,
            "records": [],
            "record_count": 0,
            "failure_reason": "failed",
            "message": "Odoo search is unavailable for this request.",
        }

    message_text = format_bank_accounting_summary(raw_result, keyword)
    status = raw_result.get("status") or (
        "completed" if raw_result.get("found") else "not_found"
    )

    log_request({
        "event_type": "odoo_read",
        "title": "Consultation comptable bancaire Odoo",
        "system": "odoo",
        "agent": "odoo_agent",
        "status": status,
        "risk": "low",
        "approval_status": "not_required",
        "user_message": message,
        "action": "bank_accounting_search",
        "model": raw_result.get("selected_model") or raw_result.get("model"),
        "message": "Données comptables bancaires consultées dans Odoo sans modification.",
        "data": {
            "selected_model": raw_result.get("selected_model") or raw_result.get("model"),
            "candidate_models": raw_result.get("candidate_models") or [],
            "fields_used": raw_result.get("fields_used") or [],
            "domain_used": raw_result.get("domain_used") or [],
            "count_returned": raw_result.get("count_returned") or raw_result.get("record_count") or 0,
            "failure_reason": raw_result.get("failure_reason"),
        },
    })

    return with_parser_debug({
        "intent": "odoo",
        "agent": "odoo_agent",
        "risk": "low",
        "risk_level": "low",
        "requires_approval": False,
        "approval_required": False,
        "status": status,
        "message": message_text,
        "tool_used": "odoo_search_bank_accounting",
        "target_system": "odoo",
        "capability": "odoo.accounting_bank_read",
        "target_model": raw_result.get("selected_model") or raw_result.get("model"),
        "odoo_model": raw_result.get("selected_model") or raw_result.get("model"),
        "record_count": raw_result.get("record_count") or 0,
            "selected_model_name": raw_result.get("selected_model") or raw_result.get("model"),
            "candidate_models": raw_result.get("candidate_models") or [],
            "fields_used": raw_result.get("fields_used") or [],
        "domain_used": raw_result.get("domain_used") or [],
        "count_returned": raw_result.get("count_returned") or raw_result.get("record_count") or 0,
        "failure_reason": raw_result.get("failure_reason"),
        "data": raw_result,
        "result": raw_result,
    }, parsed_action, "bank_accounting_search")


def format_supplier_ranking_summary(raw_result: dict) -> str:
    records = raw_result.get("records") if isinstance(raw_result.get("records"), list) else []

    if raw_result.get("failure_reason") == "no_records" or not raw_result.get("found"):
        return raw_result.get("message") or (
            "Aucun fournisseur n'a été trouvé dans les bons de commande."
        )

    lines = ["Fournisseurs les plus présents dans les bons de commande :"]

    for index, record in enumerate(records[:10], start=1):
        if not isinstance(record, dict):
            continue

        supplier = record.get("supplier")
        count = record.get("count")

        if supplier and count is not None:
            lines.append(f"{index}. {supplier} : {count} bon(s) de commande")

    if len(lines) == 1:
        return "Aucun fournisseur n'a été trouvé dans les bons de commande."

    return "\n".join(lines)


def execute_supplier_ranking(message: str, parsed_action: dict):
    raw_result = unwrap_tool_response(
        execute_tool(
            "odoo_rank_purchase_order_suppliers",
            limit=10,
        )
    )

    if not isinstance(raw_result, dict):
        raw_result = {
            "success": False,
            "status": "failed",
            "found": False,
            "records": [],
            "record_count": 0,
            "failure_reason": "failed",
            "message": "Le classement des fournisseurs n'a pas pu être lu dans Odoo.",
        }

    message_text = format_supplier_ranking_summary(raw_result)
    status = raw_result.get("status") or (
        "completed" if raw_result.get("found") else "not_found"
    )

    log_request({
        "event_type": "odoo_read",
        "title": "Classement fournisseurs bons de commande",
        "system": "odoo",
        "agent": "odoo_agent",
        "status": status,
        "risk": "low",
        "approval_status": "not_required",
        "user_message": message,
        "action": "supplier_ranking",
        "model": raw_result.get("selected_model") or "purchase.order",
        "message": "Classement fournisseur lu depuis les bons de commande sans modification.",
        "data": {
            "selected_model": raw_result.get("selected_model") or "purchase.order",
            "aggregation_field": raw_result.get("aggregation_field"),
            "odoo_method": raw_result.get("odoo_method"),
            "count_returned": raw_result.get("count_returned") or raw_result.get("record_count") or 0,
            "failure_reason": raw_result.get("failure_reason"),
        },
    })

    return with_parser_debug({
        "intent": "odoo",
        "agent": "odoo_agent",
        "risk": "low",
        "risk_level": "low",
        "requires_approval": False,
        "approval_required": False,
        "status": status,
        "message": message_text,
        "tool_used": "odoo_rank_purchase_order_suppliers",
        "target_system": "odoo",
        "capability": "odoo.purchase_supplier_ranking",
        "target_model": raw_result.get("selected_model") or "purchase.order",
        "odoo_model": raw_result.get("selected_model") or "purchase.order",
        "selected_model_name": raw_result.get("selected_model") or "purchase.order",
        "aggregation_field": raw_result.get("aggregation_field"),
        "odoo_method": raw_result.get("odoo_method"),
        "domain_used": raw_result.get("domain_used") or [],
        "fields_used": raw_result.get("fields_used") or [],
        "count_returned": raw_result.get("count_returned") or raw_result.get("record_count") or 0,
        "record_count": raw_result.get("record_count") or 0,
        "failure_reason": raw_result.get("failure_reason"),
        "data": raw_result,
        "result": raw_result,
    }, parsed_action, "supplier_ranking")


def format_customer_ranking_summary(raw_result: dict) -> str:
    records = raw_result.get("records") if isinstance(raw_result.get("records"), list) else []

    if raw_result.get("failure_reason") == "no_records" or not raw_result.get("found"):
        return raw_result.get("message") or (
            "Aucun client n'a été trouvé dans les commandes client."
        )

    lines = ["Clients les plus présents dans les commandes client :"]

    for index, record in enumerate(records[:10], start=1):
        if not isinstance(record, dict):
            continue

        customer = record.get("customer")
        count = record.get("count")

        if customer and count is not None:
            lines.append(f"{index}. {customer} : {count} commande(s) client")

    if len(lines) == 1:
        return "Aucun client n'a été trouvé dans les commandes client."

    return "\n".join(lines)


def execute_customer_ranking(message: str, parsed_action: dict):
    raw_result = unwrap_tool_response(
        execute_tool(
            "odoo_rank_sale_order_customers",
            limit=10,
        )
    )

    if not isinstance(raw_result, dict):
        raw_result = {
            "success": False,
            "status": "failed",
            "found": False,
            "records": [],
            "record_count": 0,
            "failure_reason": "failed",
            "message": "Le classement des clients n'a pas pu être lu dans Odoo.",
        }

    message_text = format_customer_ranking_summary(raw_result)
    status = raw_result.get("status") or (
        "completed" if raw_result.get("found") else "not_found"
    )

    log_request({
        "event_type": "odoo_read",
        "title": "Classement clients commandes client",
        "system": "odoo",
        "agent": "odoo_agent",
        "status": status,
        "risk": "low",
        "approval_status": "not_required",
        "user_message": message,
        "action": "customer_ranking",
        "model": raw_result.get("selected_model") or "sale.order",
        "message": "Classement client lu depuis les commandes client sans modification.",
        "data": {
            "selected_model": raw_result.get("selected_model") or "sale.order",
            "aggregation_field": raw_result.get("aggregation_field"),
            "odoo_method": raw_result.get("odoo_method"),
            "count_returned": raw_result.get("count_returned") or raw_result.get("record_count") or 0,
            "failure_reason": raw_result.get("failure_reason"),
        },
    })

    return with_parser_debug({
        "intent": "odoo",
        "agent": "odoo_agent",
        "risk": "low",
        "risk_level": "low",
        "requires_approval": False,
        "approval_required": False,
        "status": status,
        "message": message_text,
        "tool_used": "odoo_rank_sale_order_customers",
        "target_system": "odoo",
        "capability": "odoo.sale_customer_ranking",
        "target_model": raw_result.get("selected_model") or "sale.order",
        "odoo_model": raw_result.get("selected_model") or "sale.order",
        "selected_model_name": raw_result.get("selected_model") or "sale.order",
        "aggregation_field": raw_result.get("aggregation_field"),
        "odoo_method": raw_result.get("odoo_method"),
        "domain_used": raw_result.get("domain_used") or [],
        "fields_used": raw_result.get("fields_used") or [],
        "count_returned": raw_result.get("count_returned") or raw_result.get("record_count") or 0,
        "record_count": raw_result.get("record_count") or 0,
        "failure_reason": raw_result.get("failure_reason"),
        "data": raw_result,
        "result": raw_result,
    }, parsed_action, "customer_ranking")


def build_agentic_read_response(message: str, parsed_action: dict, read_plan: dict):
    raw_result = run_odoo_read_agent(
        message,
        read_plan=read_plan,
    )

    if raw_result.get("stop_reason") == "provider_error":
        raw_result = unwrap_tool_response(
            execute_tool("odoo_generic_read", read_plan=read_plan)
        )
        return build_dynamic_read_response(message, parsed_action, raw_result)

    response = with_parser_debug({
        "intent": "odoo",
        "agent": "odoo_agent",
        "risk": "low",
        "risk_level": "low",
        "requires_approval": False,
        "approval_required": False,
        "status": raw_result.get("status", "completed"),
        "message": raw_result.get("message") or "Lecture Odoo terminée.",
        "tool_used": "odoo_read_agent",
        "target_system": "odoo",
        "odoo_model": next(iter(raw_result.get("models_used", [])), None),
        "record_count": raw_result.get("record_count") or 0,
        "business_scope_status": raw_result.get("business_scope_status"),
        "provider": raw_result.get("provider"),
        "model": raw_result.get("model"),
        "llm_success": raw_result.get("llm_success"),
        "llm_error": raw_result.get("llm_error"),
        "data": {
            "tool_sequence": raw_result.get("tool_sequence", []),
            "models_used": raw_result.get("models_used", []),
            "record_count": raw_result.get("record_count") or 0,
            "business_scope_status": raw_result.get("business_scope_status"),
            "stop_reason": raw_result.get("stop_reason"),
        },
        "result": raw_result,
    }, parsed_action, "odoo_generic_read")

    log_request({
        "event_type": "odoo_read",
        "title": "Lecture Odoo générique",
        "system": "odoo",
        "agent": "odoo_agent",
        "status": response.get("status", "completed"),
        "risk": "low",
        "approval_status": "not_required",
        "user_message": message,
        "action": "odoo_generic_read",
        "target_model": response.get("odoo_model"),
        "record_count": response.get("record_count"),
        "business_scope_status": response.get("business_scope_status"),
        "tool_sequence": [
            {
                "tool": item.get("tool"),
                "model": item.get("model"),
                "record_count": item.get("record_count"),
                "group_by": item.get("group_by"),
                "group_count": item.get("group_count"),
                "business_scope_status": item.get("business_scope_status"),
                "status": item.get("status"),
                "validation_allowed": item.get("validation_allowed"),
            }
            for item in raw_result.get("tool_sequence", [])
            if isinstance(item, dict)
        ],
        "message": "Lecture Odoo consultative via agent de lecture borné.",
    })

    return response


def run(message: str, classification: dict | None = None):
    if (
        isinstance(classification, dict)
        and classification.get("capability") == "odoo.connection_status"
    ):
        parsed_action = {
            "intent": "odoo",
            "action": "odoo_status",
            "business_action": "odoo_status",
            "risk": "low",
            "requires_approval": False,
            "confidence": 0.95,
            "parser_source": classification.get("semantic_source") or classification.get("classifier_source") or "semantic_route",
            "parser_error": classification.get("classifier_error"),
            "entities": _semantic_read_values(classification),
        }
        raw_result = unwrap_tool_response(execute_tool("odoo_test_connection"))
        connected = bool(raw_result.get("connected") or raw_result.get("success"))
        status = "completed" if connected else "failed"
        message_text = (
            "Odoo est connecté."
            if connected
            else "Odoo n'est pas connecté ou ne répond pas pour le moment."
        )
        return with_parser_debug({
            "intent": "odoo",
            "agent": "odoo_agent",
            "risk": "low",
            "risk_level": "low",
            "requires_approval": False,
            "approval_required": False,
            "status": status,
            "message": message_text,
            "tool_used": "odoo_test_connection",
            "target_system": "odoo",
            "capability": "odoo.connection_status",
            "data": raw_result,
            "result": raw_result,
        }, parsed_action, "odoo_status")

    if (
        isinstance(classification, dict)
        and classification.get("capability") == "odoo.purchase_supplier_ranking"
    ):
        parsed_action = {
            "intent": "odoo",
            "action": "supplier_ranking",
            "business_action": "supplier_ranking",
            "risk": "low",
            "requires_approval": False,
            "target_model": "purchase.order",
            "model": "purchase.order",
            "field_name": "partner_id",
            "confidence": 0.9,
            "parser_source": classification.get("semantic_source") or classification.get("classifier_source") or "semantic_route",
            "parser_error": classification.get("classifier_error"),
            "entities": _semantic_read_values(classification),
        }
        return execute_supplier_ranking(message, parsed_action)

    if (
        isinstance(classification, dict)
        and classification.get("capability") == "odoo.sale_customer_ranking"
    ):
        parsed_action = {
            "intent": "odoo",
            "action": "customer_ranking",
            "business_action": "customer_ranking",
            "risk": "low",
            "requires_approval": False,
            "target_model": "sale.order",
            "model": "sale.order",
            "field_name": "partner_id",
            "confidence": 0.9,
            "parser_source": classification.get("semantic_source") or classification.get("classifier_source") or "semantic_route",
            "parser_error": classification.get("classifier_error"),
            "entities": _semantic_read_values(classification),
        }
        return execute_customer_ranking(message, parsed_action)

    if (
        isinstance(classification, dict)
        and classification.get("capability") == "odoo.accounting_bank_read"
    ):
        parsed_action = {
            "intent": "odoo",
            "action": "bank_accounting_search",
            "business_action": "bank_accounting_search",
            "risk": "low",
            "requires_approval": False,
            "target_model": "account.bank.statement",
            "model": "account.bank.statement",
            "record_query": (
                _semantic_read_values(classification).get("query")
                or _semantic_read_values(classification).get("record_query")
                or extract_generic_keyword(message)
            ),
            "confidence": 0.9,
            "parser_source": classification.get("semantic_source") or classification.get("classifier_source") or "semantic_route",
            "parser_error": classification.get("classifier_error"),
            "entities": _semantic_read_values(classification),
        }
        return execute_bank_accounting_search(message, parsed_action)

    if (
        isinstance(classification, dict)
        and classification.get("capability") == "odoo.customer_invoice_list"
    ):
        values = _semantic_read_values(classification)
        parsed_action = {
            "intent": "odoo_customer_invoice_list",
            "action": "list_customer_invoices",
            "business_action": "list_customer_invoices",
            "risk": "low",
            "requires_approval": False,
            "target_model": "account.move",
            "model": "account.move",
            "filters": values.get("filters") if isinstance(values.get("filters"), list) else [],
            "requested_fields": values.get("requested_fields") if isinstance(values.get("requested_fields"), list) else [],
            "limit": values.get("limit") or 10,
            "confidence": 0.9,
            "parser_source": classification.get("semantic_source") or classification.get("classifier_source") or "semantic_route",
            "parser_error": classification.get("classifier_error"),
            "entities": values,
        }
        return execute_customer_invoice_list(message, parsed_action)

    if (
        isinstance(classification, dict)
        and classification.get("capability") in {
            "odoo.analytic_account_search",
            "odoo.analytic_account_details",
        }
    ):
        values = _semantic_read_values(classification)
        is_details = classification.get("capability") == "odoo.analytic_account_details"
        parsed_action = {
            "intent": (
                "odoo_analytic_account_details"
                if is_details
                else "odoo_analytic_account_search"
            ),
            "action": (
                "odoo_get_analytic_account_details"
                if is_details
                else "odoo_search_analytic_account"
            ),
            "business_action": (
                "odoo_get_analytic_account_details"
                if is_details
                else "odoo_search_analytic_account"
            ),
            "risk": "low",
            "requires_approval": False,
            "target_model": "account.analytic.account",
            "model": "account.analytic.account",
            "record_query": (
                values.get("record_query")
                or values.get("query")
                or extract_generic_keyword(message)
            ),
            "confidence": 0.9,
            "parser_source": classification.get("semantic_source") or classification.get("classifier_source") or "semantic_route",
            "parser_error": classification.get("classifier_error"),
            "entities": values,
        }
        return execute_analytic_account_read(message, parsed_action)

    if (
        isinstance(classification, dict)
        and classification.get("capability") == "odoo.analytic_boolean_update"
    ):
        values = _semantic_read_values(classification)
        parsed_action = {
            "intent": "odoo_write_request",
            "action": "toggle_boolean_field",
            "business_action": "toggle_boolean_field",
            "risk": "medium",
            "requires_approval": True,
            "target_model": "account.analytic.account",
            "model": "account.analytic.account",
            "record_query": (
                values.get("record_query")
                or values.get("query")
                or extract_generic_keyword(message)
            ),
            "field_label": values.get("field_label") or "Pointage",
            "field_name": values.get("field_name"),
            "new_value": values.get("new_value") if "new_value" in values else True,
            "confidence": 0.9,
            "parser_source": classification.get("semantic_source") or classification.get("classifier_source") or "semantic_route",
            "parser_error": classification.get("classifier_error"),
            "entities": values,
        }
        return build_sensitive_approval_response(message, "toggle_boolean_field", parsed_action)

    if (
        isinstance(classification, dict)
        and classification.get("capability") == "odoo.generic_read"
    ):
        values = _semantic_read_values(classification)
        read_plan = build_odoo_read_plan(message, classification)
        parsed_action = {
            "intent": "odoo",
            "action": values.get("action") or classification.get("action") or "odoo_generic_read",
            "business_action": values.get("action") or classification.get("action") or "odoo_generic_read",
            "operation": read_plan.get("operation"),
            "business_object": read_plan.get("business_object"),
            "risk": "low",
            "requires_approval": False,
            "target_model": read_plan.get("model_hint"),
            "record_query": read_plan.get("query") or read_plan.get("business_object"),
            "confidence": 0.9,
            "parser_source": classification.get("semantic_source") or classification.get("classifier_source") or "semantic_route",
            "parser_error": classification.get("classifier_error"),
            "entities": _semantic_read_values(classification),
        }

        if read_plan.get("needs_clarification") and read_plan.get("clarification_reason") == "official_or_odoo_headcount":
            return with_parser_debug({
                "intent": "odoo",
                "agent": "odoo_agent",
                "risk": "low",
                "risk_level": "low",
                "requires_approval": False,
                "approval_required": False,
                "status": "needs_clarification",
                "message": "Voulez-vous l’effectif officiel de l’entreprise ou le nombre d’employés enregistrés dans Odoo ?",
                "tool_used": None,
                "target_system": "odoo",
                "odoo_model": read_plan.get("model_hint"),
                "record_count": 0,
                "data": {"executed": False, "read_plan": read_plan},
                "result": {"executed": False, "read_plan": read_plan},
            }, parsed_action, "odoo_count_records")

        if read_plan.get("memory_followup") or read_plan.get("catalog_read"):
            raw_result = unwrap_tool_response(
                execute_tool("odoo_generic_read", read_plan=read_plan)
            )
            result = build_dynamic_read_response(message, parsed_action, raw_result)
            result["memory_context_used"] = bool(read_plan.get("memory_followup"))
            result["catalog_read_used"] = bool(read_plan.get("catalog_read"))
            result["resolved_from_previous_model"] = read_plan.get("model_hint")
            result["resolved_business_object"] = read_plan.get("business_object")
            result["follow_up_limit"] = read_plan.get("limit")
            return result

        result = build_agentic_read_response(message, parsed_action, read_plan)

        return result

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
        if should_use_agentic_broad_read(message, classification, parsed_action):
            read_plan = build_odoo_read_plan(message, classification)
            read_plan["operation"] = read_plan.get("operation") or "list"
            read_plan["business_object"] = read_plan.get("business_object") or message
            return build_agentic_read_response(message, parsed_action, read_plan)

        if action in {"search_document", "odoo_search_records"} and not parsed_action.get("understood_write"):
            read_plan = build_odoo_read_plan(message, classification)
            read_plan["operation"] = read_plan.get("operation") or "list"
            read_plan["business_object"] = read_plan.get("business_object") or message
            return build_agentic_read_response(message, parsed_action, read_plan)

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

    if should_use_agentic_broad_read(message, classification, parsed_action):
        read_plan = build_odoo_read_plan(message, classification)
        read_plan["business_object"] = read_plan.get("business_object") or message
        return build_agentic_read_response(message, parsed_action, read_plan)

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
        "odoo_update_field_request",
    }

    if action in sensitive_actions or requires_approval(message):
        return build_sensitive_approval_response(message, action, parsed_action)

    if (
        action in {"check_stock", "product_search", "inventory_product_search", "product_details"}
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

    if action in {"odoo_search_records", "odoo_get_record_details"}:
        target_model = parsed_action.get("target_model") or parsed_action.get("model")
        record_id = parsed_action.get("record_id")
        keyword = parsed_action.get("record_query") or extract_generic_keyword(message, parsed_action)

        if should_use_agentic_broad_read(message, classification, parsed_action):
            read_plan = build_odoo_read_plan(message, classification)
            read_plan["operation"] = read_plan.get("operation") or "list"
            read_plan["business_object"] = read_plan.get("business_object") or message
            read_plan["model_hint"] = read_plan.get("model_hint") or target_model
            return build_agentic_read_response(message, parsed_action, read_plan)

        if target_model not in ALLOWED_GENERIC_READ_MODELS:
            return build_needs_clarification_response(
                message,
                parsed_action,
                ["type d’enregistrement Odoo"],
            )

        if action == "odoo_search_records" and not keyword:
            read_plan = build_odoo_read_plan(message, classification)
            read_plan["operation"] = "list"
            read_plan["business_object"] = read_plan.get("business_object") or message
            read_plan["model_hint"] = read_plan.get("model_hint") or target_model
            return build_agentic_read_response(message, parsed_action, read_plan)

        if action == "odoo_get_record_details" and record_id is None and not keyword:
            return build_needs_clarification_response(
                message,
                parsed_action,
                ["identifiant ou mot-clé"],
            )

        if action == "odoo_get_record_details":
            raw_result = unwrap_tool_response(
                execute_tool(
                    "odoo_get_record_details",
                    model_name=target_model,
                    record_id=record_id,
                    keyword=keyword,
                )
            )
        else:
            raw_result = unwrap_tool_response(
                execute_tool(
                    "odoo_search_records",
                    model_name=target_model,
                    keyword=keyword,
                    limit=6,
                )
            )

        found = bool(isinstance(raw_result, dict) and raw_result.get("found"))
        ambiguous = bool(isinstance(raw_result, dict) and raw_result.get("ambiguous"))
        message_text, normalized_read, synthesis = _synthesize_read_message(
            message,
            parsed_action,
            raw_result if isinstance(raw_result, dict) else {},
            operation="read" if action == "odoo_get_record_details" else "search",
            query_context={
                "operation": "read" if action == "odoo_get_record_details" else "search",
                "model": target_model,
                "record_id": record_id,
                "query": keyword,
            },
        )

        log_request({
            "event_type": "odoo_read",
            "title": "Recherche Odoo générique",
            "system": "odoo",
            "agent": "odoo_agent",
            "status": "completed" if found and not ambiguous else "not_found",
            "risk": "low",
            "approval_status": "not_required",
            "user_message": message,
            "action": action,
            "target_model": target_model,
            "message": "Lecture Odoo consultative sans modification.",
            "data": raw_result,
        })

        return with_parser_debug({
            "intent": "odoo",
            "agent": "odoo_agent",
            "risk": "low",
            "risk_level": "low",
            "requires_approval": False,
            "approval_required": False,
            "status": "needs_clarification" if ambiguous else ("completed" if found else "not_found"),
            "message": (
                "Plusieurs enregistrements correspondent à votre demande. Veuillez préciser lequel choisir."
                if ambiguous
                else message_text
            ),
            "tool_used": "odoo_get_record_details" if action == "odoo_get_record_details" else "odoo_search_records",
            "normalized_read_result": normalized_read,
            "response_synthesis": synthesis,
            "data": raw_result,
            "result": raw_result,
            "candidates": raw_result.get("candidates", []) if isinstance(raw_result, dict) else [],
        }, parsed_action, action)

    if action == "bank_accounting_search":
        return execute_bank_accounting_search(message, parsed_action)

    if action == "supplier_ranking":
        return execute_supplier_ranking(message, parsed_action)

    if action == "customer_ranking":
        return execute_customer_ranking(message, parsed_action)

    if action == "odoo_status":
        raw_result = unwrap_tool_response(execute_tool("odoo_test_connection"))
        connected = bool(raw_result.get("connected") or raw_result.get("success"))
        status = "completed" if connected else "failed"
        message_text = (
            "Odoo est connecté."
            if connected
            else "Odoo n'est pas connecté ou ne répond pas pour le moment."
        )
        return with_parser_debug({
            "intent": "odoo",
            "agent": "odoo_agent",
            "risk": "low",
            "risk_level": "low",
            "requires_approval": False,
            "approval_required": False,
            "status": status,
            "message": message_text,
            "tool_used": "odoo_test_connection",
            "target_system": "odoo",
            "capability": "odoo.connection_status",
            "data": raw_result,
            "result": raw_result,
        }, parsed_action, "odoo_status")

    if action in ["check_stock", "check_price", "check_unit", "check_product_details", "product_details"]:
        product_name = parsed_action.get("record_query") or extract_product_name(message)
        raw_result = check_stock(product_name)
        data = normalize_stock_result(raw_result, action)

        found = bool(data.get("found"))
        connector_error = (
            isinstance(raw_result, dict)
            and raw_result.get("source") == "real_odoo_error"
        )

        if connector_error:
            message_text = (
                "La connexion Odoo est indisponible pour le moment. "
                "Je ne peux pas vérifier le stock de ce produit."
            )
            normalized_read = {
                "status": "failed",
                "operation": "read",
                "model": raw_result.get("model"),
                "record_count": 0,
                "records": [],
                "groups": [],
                "query_context": {
                    "requested_entity": product_name,
                    "operation": "read",
                },
                "business_scope_status": "not_required",
                "business_scope_evidence": [],
                "truncated": False,
                "error": "odoo_unavailable",
            }
            synthesis = {
                "response": message_text,
                "used_llm": False,
                "provider": None,
                "model": None,
                "llm_error": None,
            }
        else:
            message_text, normalized_read, synthesis = _synthesize_read_message(
                message,
                parsed_action,
                {
                    **(raw_result if isinstance(raw_result, dict) else {}),
                    "found": found,
                    "success": found,
                    "record": data,
                    "records": [data] if found else [],
                },
                operation="read",
                query_context={
                    "requested_entity": product_name,
                    "operation": "read",
                },
            )

        status = "failed" if connector_error else ("completed" if found else "not_found")

        log_request({
            "event_type": "odoo_read",
            "title": "Consultation produit Odoo",
            "system": "odoo",
            "agent": "odoo_agent",
            "status": status,
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
            "status": status,
            "message": message_text,
            "tool_used": "odoo_check_stock",
            "normalized_read_result": normalized_read,
            "response_synthesis": synthesis,
            "data": data,
            "result": raw_result,
        }, parsed_action, action)

    if action in {"product_search", "inventory_product_search"}:
        product_name = (
            parsed_action.get("record_query")
            or parsed_action.get("product_query")
            or (
                extract_inventory_product_keyword(message)
                if action == "inventory_product_search"
                else extract_product_name(message)
            )
        )

        if is_vague_product_keyword(product_name):
            return build_needs_clarification_response(
                message,
                parsed_action,
                ["mot-clé produit"],
            )

        raw_result = search_product(product_name)
        found = bool(isinstance(raw_result, dict) and raw_result.get("found"))
        message_text, normalized_read, synthesis = _synthesize_read_message(
            message,
            parsed_action,
            raw_result if isinstance(raw_result, dict) else {},
            operation="search",
            query_context={
                "requested_entity": product_name,
                "operation": "search",
            },
        )

        log_request({
            "event_type": "odoo_read",
            "title": (
                "Vérification intégration inventaire Odoo"
                if action == "inventory_product_search"
                else "Recherche produit Odoo"
            ),
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
            "intent": parsed_action.get("intent") or "odoo",
            "agent": "odoo_agent",
            "risk": "low",
            "risk_level": "low",
            "requires_approval": False,
            "approval_required": False,
            "status": "completed" if found else "not_found",
            "message": message_text,
            "tool_used": "odoo_search_product",
            "normalized_read_result": normalized_read,
            "response_synthesis": synthesis,
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
        candidates = raw_result.get("candidates", []) if isinstance(raw_result, dict) else []
        candidates_message = (
            format_document_candidates_message(candidates)
            if ambiguous or len(candidates) > 1
            else None
        )
        focused_message, response_focus = (
            focused_document_response_message(message, raw_result)
            if found and not ambiguous and not candidates_message
            else (None, None)
        )
        details_message = (
            format_document_details_message(raw_result)
            if found and not ambiguous and not candidates_message and not focused_message
            else None
        )
        synthesized_document_message, normalized_read, synthesis = _synthesize_read_message(
            message,
            parsed_action,
            raw_result if isinstance(raw_result, dict) else {},
            operation="read" if action == "document_details" or document_id is not None else "search",
            query_context={
                "operation": "read" if action == "document_details" or document_id is not None else "search",
                "model": target_model,
                "record_id": document_id,
                "query": document_query,
            },
        )
        if candidates_message:
            document_message = candidates_message
        else:
            document_message = (
                focused_message
                or details_message
                or synthesized_document_message
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
            "status": "needs_clarification" if candidates_message else ("completed" if found else "not_found"),
            "message": document_message,
            "response_focus": response_focus,
            "tool_used": tool_name,
            "normalized_read_result": normalized_read,
            "response_synthesis": synthesis,
            "data": raw_result,
            "result": raw_result,
            "candidates": candidates,
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
