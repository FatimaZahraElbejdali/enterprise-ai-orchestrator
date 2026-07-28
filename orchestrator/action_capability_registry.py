import calendar
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable

from orchestrator.odoo_business_catalog import build_odoo_catalog_read_plan
from orchestrator.tool_registry import get_capability_metadata


def normalize_text(value: str) -> str:
    prepared = (value or "").replace("’", " ").replace("'", " ")
    normalized = unicodedata.normalize("NFKD", prepared)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().split())


def contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def has_word(text: str, terms: set[str]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in terms)


def route_domain(route: dict | None) -> str:
    if not isinstance(route, dict):
        return ""

    return str(route.get("domain") or route.get("target_system") or "").lower()


def route_action(route: dict | None) -> str:
    if not isinstance(route, dict):
        return ""

    return normalize_text(
        " ".join(
            str(route.get(key) or "")
            for key in ("action", "intent", "capability", "request_type")
        )
    )


READ_TERMS = {
    "affiche",
    "cherche",
    "combien",
    "count",
    "detail",
    "details",
    "donne",
    "etat",
    "existe",
    "information",
    "informations",
    "liste",
    "lister",
    "montre",
    "read",
    "search",
    "show",
    "statut",
    "status",
    "trouve",
    "verifie",
}

WRITE_TERMS = {
    "activer",
    "annuler",
    "changer",
    "change",
    "coche",
    "cocher",
    "create",
    "creer",
    "delete",
    "modifier",
    "mettre a jour",
    "mettre",
    "met",
    "mets",
    "supprimer",
    "toggle",
    "update",
    "valide",
    "valider",
}

ODOO_TERMS = {"odoo", "erp"}
STATUS_TERMS = {
    "accessible",
    "connecte",
    "connectee",
    "connexion",
    "connection",
    "connected",
    "disponible",
    "etat",
    "online",
    "status",
    "statut",
}
PRODUCT_TERMS = {"article", "inventory", "inventaire", "product", "produit", "stock"}
PRICE_TERMS = {"prix", "price", "tarif"}
CONTACT_TERMS = {"contact", "contacts", "partner", "partenaire", "res.partner"}
SALE_ORDER_TERMS = {
    "commande client",
    "commandes client",
    "commande du client",
    "commandes du client",
    "commande de client",
    "commandes de client",
    "commande de vente",
    "commandes de vente",
    "devis",
    "quotation",
    "sale order",
    "sale orders",
    "sales order",
    "sales orders",
}
PURCHASE_ORDER_TERMS = {
    "bon de commande",
    "bons de commande",
    "commande fournisseur",
    "commandes fournisseur",
    "purchase order",
    "purchase orders",
}
SUPPLIER_TERMS = {"fournisseur", "fournisseurs", "supplier", "suppliers", "vendor", "vendors"}
CUSTOMER_TERMS = {"client", "clients", "customer", "customers"}
INVOICE_TERMS = {"facture", "factures", "invoice", "invoices"}
SALES_INVOICE_TERMS = {
    "facture client",
    "factures client",
    "factures clients",
    "facture de vente",
    "factures de vente",
    "customer invoice",
    "customer invoices",
    "sales invoice",
    "sales invoices",
}
POSTED_STATUS_TERMS = {
    "confirmee",
    "confirmees",
    "confirme",
    "confirmes",
    "comptabilisee",
    "comptabilisees",
    "comptabilise",
    "comptabilises",
    "posted",
    "postee",
    "postees",
    "poste",
    "postes",
    "validee",
    "validees",
    "valide",
    "valides",
}
RANKING_TERMS = {
    "apparait",
    "apparaissent",
    "classement",
    "distribution",
    "frequence",
    "le plus",
    "les plus",
    "ranking",
    "repartition",
    "top",
}
ANALYTIC_TERMS = {
    "account analytic account",
    "account.analytic.account",
    "analytic account",
    "analytique",
    "compte analytique",
}
POINTAGE_TERMS = {"pointage"}
SERVER_TERMS = {"infrastructure", "server", "serveur", "serveurs"}
RAM_TERMS = {"memoire", "memory", "ram"}
SERVER_STATUS_TERMS = {"diagnostic", "etat", "health", "status", "statut", "verifie"}
SUPPORT_TERMS = {
    "imprimante",
    "lenteur",
    "ordinateur",
    "pc",
    "printer",
    "slow",
    "support",
    "vpn",
    "wifi",
    "wi-fi",
}


@dataclass(frozen=True)
class BusinessCapability:
    name: str
    capability: str
    domain: str
    action_type: str
    business_object: str
    required_permissions: tuple[str, ...]
    required_parameters: tuple[str, ...]
    resolver_rules: tuple[str, ...]
    execution_handler: str
    intent: str
    action: str
    execution_mode: str = "tool"
    parameters_factory: Callable[[str, dict | None], dict] | None = None
    matcher: Callable[[str, dict | None], bool] | None = field(default=None, compare=False)

    def matches(self, message: str, route: dict | None = None) -> bool:
        text = normalize_text(message)
        return bool(self.matcher and self.matcher(text, route))

    def route(self, message: str, route: dict | None = None) -> dict:
        metadata = get_capability_metadata(self.capability) or {}
        parameters = (
            self.parameters_factory(message, route)
            if self.parameters_factory
            else {}
        )
        risk_level = (
            "high"
            if self.action_type == "approval_required"
            else metadata.get("risk_level", "low")
        )
        requires_approval = (
            self.action_type == "approval_required"
            or bool(metadata.get("requires_approval"))
        )
        classifier_source = (
            route.get("classifier_source")
            if isinstance(route, dict) and route.get("classifier_source")
            else "capability_registry"
        )
        classifier_error = (
            route.get("classifier_error")
            if isinstance(route, dict) and "classifier_error" in route
            else None
        )

        route_action_name = str(parameters.get("action") or self.action).strip() or self.action
        route_intent_name = str(parameters.get("intent") or self.intent).strip() or self.intent

        resolved_route = {
            "intent": route_intent_name,
            "agent": f"{self.domain}_agent" if self.domain != "odoo" else "odoo_agent",
            "selected_agent": f"{self.domain}_agent" if self.domain != "odoo" else "odoo_agent",
            "action": route_action_name,
            "target_system": self.domain,
            "domain": self.domain,
            "risk_level": risk_level,
            "risk": risk_level,
            "requires_approval": requires_approval,
            "approval_required": requires_approval,
            "entities": {},
            "confidence": "high",
            "reason": "Central capability registry selected this business action.",
            "classifier_source": classifier_source,
            "classifier_error": classifier_error,
            "capability": self.capability,
            "request_type": "enterprise_action",
            "execution_mode": self.execution_mode,
            "parameters": parameters,
            "business_object": self.business_object,
            "action_type": self.action_type,
            "required_permissions": list(self.required_permissions),
            "required_parameters": list(self.required_parameters),
            "resolver_rules": list(self.resolver_rules),
            "execution_handler": self.execution_handler,
            "clarification_needed": False,
            "missing_parameters": [],
        }

        if isinstance(route, dict):
            for key in ("semantic_source", "semantic_request"):
                if key in route:
                    resolved_route[key] = route[key]

        return resolved_route


def _odoo_context(text: str, route: dict | None) -> bool:
    return contains_any(text, ODOO_TERMS) or route_domain(route) == "odoo"


def _odoo_status(text: str, route: dict | None) -> bool:
    if not _odoo_context(text, route):
        return False

    if contains_any(text, WRITE_TERMS | PRODUCT_TERMS | ANALYTIC_TERMS | POINTAGE_TERMS):
        return False

    return contains_any(text, STATUS_TERMS)


def _product_stock(text: str, route: dict | None) -> bool:
    if contains_any(text, WRITE_TERMS):
        return False

    if contains_any(text, {"above", "greater than", "superieur", "superieure", "supérieur", "supérieure", ">"}):
        return False

    if contains_any(
        text,
        {"cherche", "contient", "contiennent", "existe", "existent", "liste", "search", "trouve"},
    ):
        return False

    return contains_any(text, {"stock", "inventaire", "inventory"}) and contains_any(
        text,
        PRODUCT_TERMS,
    )


def _product_price_write(text: str, route: dict | None) -> bool:
    return contains_any(text, PRICE_TERMS) and contains_any(text, WRITE_TERMS) and (
        _odoo_context(text, route) or contains_any(text, PRODUCT_TERMS)
    )


def _product_search(text: str, route: dict | None) -> bool:
    if contains_any(text, WRITE_TERMS):
        return False

    if _product_stock(text, route) or _product_price_write(text, route):
        return False

    return contains_any(text, PRODUCT_TERMS) and contains_any(
        text,
        {"cherche", "contient", "contiennent", "existe", "liste", "search", "trouve", "verifie"},
    )


def _contact_count_or_list(text: str, route: dict | None) -> bool:
    return contains_any(text, CONTACT_TERMS) and contains_any(
        text,
        {"cite", "combien", "count", "liste", "lister", "parmi", "show"},
    )


def _sale_order_read(text: str, route: dict | None) -> bool:
    return contains_any(text, SALE_ORDER_TERMS) and contains_any(
        text,
        READ_TERMS | {"dernier", "derniers", "recent", "recents"},
    )


def _purchase_supplier_ranking(text: str, route: dict | None) -> bool:
    return (
        contains_any(text, PURCHASE_ORDER_TERMS)
        and contains_any(text, SUPPLIER_TERMS)
        and contains_any(text, RANKING_TERMS)
    )


def _purchase_document_search(text: str, route: dict | None) -> bool:
    reference_like = bool(
        re.search(
            r"\b(?=[A-Z0-9/.-]*\d)[A-Z]{1,5}[-/][A-Z0-9][A-Z0-9/.-]{3,}\b",
            message_upper(text),
        )
    )
    return contains_any(text, PURCHASE_ORDER_TERMS) and (
        contains_any(text, {"cherche", "detail", "details", "document", "search", "trouve"})
        or reference_like
    )


def _explicit_document_lookup(text: str) -> bool:
    if re.search(r"\bid\s+\d+\b", text):
        return True

    if re.search(
        r"\b(?=[A-Z0-9/.-]*\d)[A-Z]{1,8}[-/][A-Z0-9][A-Z0-9/.-]{3,}\b",
        message_upper(text),
    ):
        return True

    return False


def _customer_invoice_list(text: str, route: dict | None) -> bool:
    if _explicit_document_lookup(text):
        return False

    plan = build_odoo_catalog_read_plan(text)
    return bool(
        plan
        and plan.get("business_object") == "customer_invoices"
        and plan.get("operation") != "count"
    )


def _catalog_odoo_read(text: str, route: dict | None) -> bool:
    if _explicit_document_lookup(text):
        return False

    if not (_odoo_context(text, route) or build_odoo_catalog_read_plan(text)):
        return False

    plan = build_odoo_catalog_read_plan(text)
    if not plan:
        return False

    if plan.get("business_object") == "products" and not any(
        isinstance(item, dict)
        and item.get("field") in {"qty_available", "virtual_available", "list_price"}
        for item in plan.get("filters", [])
    ):
        return False

    if plan.get("business_object") == "contacts" and contains_any(text, RANKING_TERMS):
        return False

    status_as_read_terms = {"valide", "valides"}
    if contains_any(text, WRITE_TERMS - status_as_read_terms):
        return False

    return True


def message_upper(text: str) -> str:
    return (text or "").upper()


def _analytic_account_read(text: str, route: dict | None) -> bool:
    return contains_any(text, ANALYTIC_TERMS) and contains_any(text, READ_TERMS) and not (
        contains_any(text, WRITE_TERMS) or contains_any(text, POINTAGE_TERMS)
    )


def _analytic_account_details(text: str, route: dict | None) -> bool:
    return _analytic_account_read(text, route) and contains_any(
        text,
        {"detail", "details", "information", "informations", "fiche"},
    )


def _analytic_account_search(text: str, route: dict | None) -> bool:
    return _analytic_account_read(text, route) and not _analytic_account_details(text, route)


def _analytic_pointage_write(text: str, route: dict | None) -> bool:
    return contains_any(text, POINTAGE_TERMS) and contains_any(text, WRITE_TERMS) and (
        contains_any(text, ANALYTIC_TERMS) or _odoo_context(text, route)
    )


def _server_ram(text: str, route: dict | None) -> bool:
    return contains_any(text, SERVER_TERMS) and contains_any(text, RAM_TERMS)


def _server_status(text: str, route: dict | None) -> bool:
    return contains_any(text, SERVER_TERMS) and contains_any(text, SERVER_STATUS_TERMS)


def _support_troubleshooting(text: str, route: dict | None) -> bool:
    return contains_any(text, SUPPORT_TERMS)


def _unknown_odoo_write(text: str, route: dict | None) -> bool:
    if not _odoo_context(text, route):
        return False

    if any(
        matcher(text, route)
        for matcher in (
            _product_price_write,
            _analytic_pointage_write,
        )
    ):
        return False

    return has_word(text, WRITE_TERMS)


def _contact_parameters(message: str, route: dict | None) -> dict:
    text = normalize_text(message)
    return {
        "operation": "count" if contains_any(text, {"combien", "count"}) else "list",
        "business_object": "contacts",
        "model": "res.partner",
        "model_hint": "res.partner",
        "limit": 3 if re.search(r"\b3\b", text) else 10,
    }


def _sale_order_parameters(message: str, route: dict | None) -> dict:
    text = normalize_text(message)
    plan = build_odoo_catalog_read_plan(message)
    if plan and plan.get("business_object") == "sales_orders":
        return {
            **plan,
            "operation": "count" if contains_any(text, {"combien", "count"}) else plan.get("operation") or "list",
            "business_object": "commandes client",
            "model": "sale.order",
            "model_hint": "sale.order",
            "requested_fields": ["name", "partner_id", "state", "date_order", "amount_total", "currency_id"],
            "limit": plan.get("limit") or 10,
        }

    return {
        "operation": "count" if contains_any(text, {"combien", "count"}) else "list",
        "business_object": "commandes client",
        "model": "sale.order",
        "model_hint": "sale.order",
        "requested_fields": ["name", "partner_id", "state", "date_order"],
        "limit": 10,
    }


def _supplier_ranking_parameters(message: str, route: dict | None) -> dict:
    return {
        "operation": "aggregate",
        "business_object": "purchase_order_suppliers",
        "model": "purchase.order",
        "model_hint": "purchase.order",
        "group_by": ["partner_id"],
        "aggregate": {"operation": "count", "field": "id", "alias": "record_count"},
        "sort": [{"field": "record_count", "direction": "desc"}],
        "limit": 10,
    }


def _month_year_range(message: str) -> tuple[str, str] | None:
    text = normalize_text(message)
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)

    if not year_match:
        return None

    month_names = {
        "janvier": 1,
        "january": 1,
        "fevrier": 2,
        "february": 2,
        "mars": 3,
        "march": 3,
        "avril": 4,
        "april": 4,
        "mai": 5,
        "may": 5,
        "juin": 6,
        "june": 6,
        "juillet": 7,
        "july": 7,
        "aout": 8,
        "august": 8,
        "septembre": 9,
        "september": 9,
        "octobre": 10,
        "october": 10,
        "novembre": 11,
        "november": 11,
        "decembre": 12,
        "december": 12,
    }
    year = int(year_match.group(1))
    month = None

    for label, number in month_names.items():
        if re.search(rf"\b{label}\b", text):
            month = number
            break

    if month is None:
        month_match = re.search(r"\b(?:mois|month)\s+(\d{1,2})\b", text)
        if month_match:
            month = int(month_match.group(1))

    if not month or month < 1 or month > 12:
        return None

    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"


def _customer_invoice_parameters(message: str, route: dict | None) -> dict:
    plan = build_odoo_catalog_read_plan(message) or {}
    plan.pop("action", None)
    period = plan.get("period") if isinstance(plan.get("period"), dict) else {}
    filters = plan.get("filters") if isinstance(plan.get("filters"), list) else []
    return {
        **plan,
        "operation": "list",
        "business_object": "customer_invoices",
        "start_date": period.get("start"),
        "end_date": period.get("end"),
        "posted_only": any(
            isinstance(item, dict)
            and item.get("field") == "state"
            and item.get("value") == "posted"
            for item in filters
        ),
    }


def _catalog_read_parameters(message: str, route: dict | None) -> dict:
    return build_odoo_catalog_read_plan(message) or {}


def _analytic_record_query(message: str) -> str:
    query = re.sub(r"\bsur\s+odoo\b|\bin\s+odoo\b", " ", message or "", flags=re.IGNORECASE)
    query = re.sub(
        r"\b(?:cherche|recherche|trouve|affiche|montre|donne(?:-moi)?|details?|détails?|informations?)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(
        r"\b(?:compte\s+analytique|analytic\s+account|account\.analytic\.account|account\s+analytic\s+account)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"\b(?:le|la|les|du|de|des|d['’]|un|une)\b", " ", query, flags=re.IGNORECASE)
    query = re.sub(r"\s+", " ", query).strip(" .,:;!?\"'’")
    return query


def _analytic_read_parameters(message: str, route: dict | None) -> dict:
    return {
        "business_object": "compte analytique",
        "model": "account.analytic.account",
        "model_hint": "account.analytic.account",
        "record_query": _analytic_record_query(message),
        "limit": 10,
    }


def _analytic_pointage_parameters(message: str, route: dict | None) -> dict:
    query = _analytic_record_query(
        re.sub(r"\b(?:coche|cocher|activer|mettre|met|mets|valide|valider|pointage)\b", " ", message or "", flags=re.IGNORECASE)
    )
    return {
        "business_object": "compte analytique",
        "model": "account.analytic.account",
        "model_hint": "account.analytic.account",
        "record_query": query,
        "field_name": "x_studio_pointage",
        "new_value": True,
    }


ACTION_CAPABILITIES: tuple[BusinessCapability, ...] = (
    BusinessCapability(
        name="odoo.connection_status",
        capability="odoo.connection_status",
        domain="odoo",
        action_type="read",
        business_object="odoo_connection",
        required_permissions=("odoo_product_read",),
        required_parameters=(),
        resolver_rules=(),
        execution_handler="odoo_test_connection",
        intent="odoo_connection_status",
        action="odoo_status",
        matcher=_odoo_status,
    ),
    BusinessCapability(
        name="odoo.product_stock",
        capability="odoo.product_stock",
        domain="odoo",
        action_type="read",
        business_object="product",
        required_permissions=("odoo_product_read",),
        required_parameters=("product_name",),
        resolver_rules=("extract_product_name", "search name/default_code with ilike"),
        execution_handler="odoo_check_stock",
        intent="product_stock_check",
        action="read_product_stock",
        matcher=_product_stock,
    ),
    BusinessCapability(
        name="odoo.product_price_update",
        capability="odoo.product_price_update",
        domain="odoo",
        action_type="approval_required",
        business_object="product",
        required_permissions=("odoo_write",),
        required_parameters=("product_name", "new_price"),
        resolver_rules=("odoo_resolve_product_for_write",),
        execution_handler="odoo_update_product_price",
        intent="odoo_write_request",
        action="update_odoo_record",
        matcher=_product_price_write,
    ),
    BusinessCapability(
        name="odoo.product_search",
        capability="odoo.product_search",
        domain="odoo",
        action_type="read",
        business_object="product",
        required_permissions=("odoo_product_read",),
        required_parameters=("product_name",),
        resolver_rules=("search name/default_code/barcode with bounded ilike",),
        execution_handler="odoo_search_product",
        intent="inventory_product_lookup",
        action="inventory_product_search",
        matcher=_product_search,
    ),
    BusinessCapability(
        name="odoo.contact_read",
        capability="odoo.generic_read",
        domain="odoo",
        action_type="read",
        business_object="contact",
        required_permissions=("odoo_read",),
        required_parameters=("model",),
        resolver_rules=("res.partner safe fields only", "conversation memory for follow-up lists"),
        execution_handler="odoo_generic_read",
        intent="odoo_generic_read",
        action="odoo_generic_read",
        parameters_factory=_contact_parameters,
        matcher=_contact_count_or_list,
    ),
    BusinessCapability(
        name="odoo.sale_order_read",
        capability="odoo.generic_read",
        domain="odoo",
        action_type="read",
        business_object="sale_order",
        required_permissions=("odoo_read",),
        required_parameters=("model",),
        resolver_rules=("sale.order safe fields only",),
        execution_handler="odoo_generic_read",
        intent="odoo_generic_read",
        action="odoo_generic_read",
        parameters_factory=_sale_order_parameters,
        matcher=_sale_order_read,
    ),
    BusinessCapability(
        name="odoo.purchase_supplier_ranking",
        capability="odoo.purchase_supplier_ranking",
        domain="odoo",
        action_type="read",
        business_object="purchase_order_supplier",
        required_permissions=("odoo_document_read",),
        required_parameters=(),
        resolver_rules=("read_group purchase.order by partner_id", "fallback search_read aggregation"),
        execution_handler="odoo_rank_purchase_order_suppliers",
        intent="odoo_purchase_supplier_ranking",
        action="supplier_ranking",
        parameters_factory=_supplier_ranking_parameters,
        matcher=_purchase_supplier_ranking,
    ),
    BusinessCapability(
        name="odoo.purchase_document_search",
        capability="odoo.document_search",
        domain="odoo",
        action_type="read",
        business_object="purchase_order",
        required_permissions=("odoo_document_read",),
        required_parameters=("query",),
        resolver_rules=("purchase.order reference/name search",),
        execution_handler="odoo_search_purchase_order",
        intent="odoo_document_search",
        action="search_document",
        matcher=_purchase_document_search,
    ),
    BusinessCapability(
        name="odoo.customer_invoice_list",
        capability="odoo.customer_invoice_list",
        domain="odoo",
        action_type="read",
        business_object="customer_invoice",
        required_permissions=("odoo_read",),
        required_parameters=("model", "filters"),
        resolver_rules=("account.move safe fields only", "move_type out_invoice", "invoice_date period filters"),
        execution_handler="odoo_list_customer_invoices",
        intent="odoo_customer_invoice_list",
        action="list_customer_invoices",
        parameters_factory=_customer_invoice_parameters,
        matcher=_customer_invoice_list,
    ),
    BusinessCapability(
        name="odoo.analytic_account_details",
        capability="odoo.analytic_account_details",
        domain="odoo",
        action_type="read",
        business_object="analytic_account",
        required_permissions=("odoo_read",),
        required_parameters=("record_query",),
        resolver_rules=("resolve account.analytic.account by safe reference or name",),
        execution_handler="odoo_get_analytic_account_details",
        intent="odoo_analytic_account_details",
        action="odoo_get_analytic_account_details",
        parameters_factory=_analytic_read_parameters,
        matcher=_analytic_account_details,
    ),
    BusinessCapability(
        name="odoo.analytic_account_search",
        capability="odoo.analytic_account_search",
        domain="odoo",
        action_type="read",
        business_object="analytic_account",
        required_permissions=("odoo_read",),
        required_parameters=("record_query",),
        resolver_rules=("search account.analytic.account by safe reference or name",),
        execution_handler="odoo_search_analytic_account",
        intent="odoo_analytic_account_search",
        action="odoo_search_analytic_account",
        parameters_factory=_analytic_read_parameters,
        matcher=_analytic_account_search,
    ),
    BusinessCapability(
        name="odoo.analytic_pointage_update",
        capability="odoo.analytic_boolean_update",
        domain="odoo",
        action_type="approval_required",
        business_object="analytic_account",
        required_permissions=("odoo_write",),
        required_parameters=("record_query", "field_name", "new_value"),
        resolver_rules=("odoo_resolve_analytic_account", "odoo_list_analytic_boolean_fields"),
        execution_handler="odoo_update_analytic_boolean_field",
        intent="odoo_write_request",
        action="toggle_boolean_field",
        parameters_factory=_analytic_pointage_parameters,
        matcher=_analytic_pointage_write,
    ),
    BusinessCapability(
        name="odoo.catalog_read",
        capability="odoo.generic_read",
        domain="odoo",
        action_type="read",
        business_object="catalog_record",
        required_permissions=("odoo_read",),
        required_parameters=("model",),
        resolver_rules=(
            "business model catalog",
            "safe fields only",
            "validated filters through fields_get",
        ),
        execution_handler="odoo_generic_read",
        intent="odoo_generic_read",
        action="odoo_generic_read",
        parameters_factory=_catalog_read_parameters,
        matcher=_catalog_odoo_read,
    ),
    BusinessCapability(
        name="server.ram_usage",
        capability="server.ram_usage",
        domain="server",
        action_type="read",
        business_object="local_server",
        required_permissions=("server_diagnostics",),
        required_parameters=(),
        resolver_rules=("safe local demo diagnostics only",),
        execution_handler="check_ram_usage",
        intent="server_ram_usage",
        action="check_ram_usage",
        matcher=_server_ram,
    ),
    BusinessCapability(
        name="server.local_health",
        capability="server.local_health",
        domain="server",
        action_type="read",
        business_object="local_server",
        required_permissions=("server_diagnostics",),
        required_parameters=(),
        resolver_rules=("safe local demo diagnostics only",),
        execution_handler="server_diagnostic_summary",
        intent="server_health_check",
        action="check_server_health",
        matcher=_server_status,
    ),
    BusinessCapability(
        name="support.troubleshooting",
        capability="support.troubleshooting",
        domain="support",
        action_type="read",
        business_object="support_issue",
        required_permissions=("support_access",),
        required_parameters=("message",),
        resolver_rules=("advice-only no backend mutation",),
        execution_handler="agents.support_agent.run",
        intent="support",
        action="troubleshoot_issue",
        execution_mode="llm_direct",
        matcher=_support_troubleshooting,
    ),
)


def list_business_capabilities() -> list[dict]:
    return [
        {
            "name": item.name,
            "capability": item.capability,
            "domain": item.domain,
            "action_type": item.action_type,
            "business_object": item.business_object,
            "required_permissions": list(item.required_permissions),
            "required_parameters": list(item.required_parameters),
            "resolver_rules": list(item.resolver_rules),
            "execution_handler": item.execution_handler,
        }
        for item in ACTION_CAPABILITIES
    ]


def match_business_capability(message: str, route: dict | None = None) -> BusinessCapability | None:
    for item in ACTION_CAPABILITIES:
        if item.matches(message, route):
            return item

    return None


def unsupported_odoo_write_route(message: str, route: dict | None = None) -> dict | None:
    text = normalize_text(message)

    if not _unknown_odoo_write(text, route):
        return None

    classifier_source = (
        route.get("classifier_source")
        if isinstance(route, dict) and route.get("classifier_source")
        else "capability_registry"
    )
    classifier_error = (
        route.get("classifier_error")
        if isinstance(route, dict) and "classifier_error" in route
        else None
    )

    return {
        "intent": "unsupported_capability",
        "agent": "odoo_agent",
        "selected_agent": "odoo_agent",
        "action": "unsupported_capability",
        "target_system": "odoo",
        "domain": "odoo",
        "risk_level": "medium",
        "risk": "medium",
        "requires_approval": False,
        "approval_required": False,
        "entities": {},
        "confidence": "high",
        "reason": "Central capability registry found an Odoo write action without a registered safe capability.",
        "classifier_source": classifier_source,
        "classifier_error": classifier_error,
        "capability": "unsupported_capability",
        "request_type": "enterprise_action",
        "execution_mode": None,
        "parameters": {},
        "business_object": "odoo_unknown",
        "action_type": "unsupported",
        "required_permissions": [],
        "required_parameters": [],
        "resolver_rules": [],
        "execution_handler": None,
        "capability_validation_error": "Action non disponible. Cette demande Odoo n’est pas connectée à une capacité backend sécurisée.",
    }


def route_from_business_capability(message: str, route: dict | None = None) -> dict | None:
    capability = match_business_capability(message, route)

    if capability:
        return capability.route(message, route)

    unsupported = unsupported_odoo_write_route(message, route)

    if unsupported:
        return unsupported

    return None


def capability_contract_for_route(message: str, route: dict | None) -> BusinessCapability | None:
    if not isinstance(route, dict):
        return None

    capability_name = route.get("capability")

    if capability_name:
        matching_capabilities = [
            item for item in ACTION_CAPABILITIES if item.capability == capability_name
        ]

        for item in matching_capabilities:
            if item.matches(message, route):
                return item

        if len(matching_capabilities) == 1:
            return matching_capabilities[0]

    return match_business_capability(message, route)


def enrich_route_with_capability_contract(message: str, route: dict | None) -> dict | None:
    if not isinstance(route, dict):
        return route

    contract = capability_contract_for_route(message, route)

    if not contract:
        return route

    enriched = dict(route)
    enriched.setdefault("business_object", contract.business_object)
    enriched.setdefault("action_type", contract.action_type)
    enriched.setdefault("required_permissions", list(contract.required_permissions))
    enriched.setdefault("required_parameters", list(contract.required_parameters))
    enriched.setdefault("resolver_rules", list(contract.resolver_rules))
    enriched.setdefault("execution_handler", contract.execution_handler)
    return enriched
