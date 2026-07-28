import calendar
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date


def normalize_business_text(value: str) -> str:
    prepared = (value or "").replace("’", " ").replace("'", " ")
    normalized = unicodedata.normalize("NFKD", prepared)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().split())


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


@dataclass(frozen=True)
class OdooBusinessCatalogEntry:
    business_object: str
    keywords: tuple[str, ...]
    model: str
    safe_readable_fields: tuple[str, ...]
    default_domain_filters: tuple[dict, ...] = field(default_factory=tuple)
    date_field_candidates: tuple[str, ...] = field(default_factory=tuple)
    status_mappings: dict[str | tuple[str, ...], tuple[str, tuple[str, ...]]] = field(default_factory=dict)
    model_candidates: tuple[str, ...] = field(default_factory=tuple)


BUSINESS_MODEL_CATALOG: tuple[OdooBusinessCatalogEntry, ...] = (
    OdooBusinessCatalogEntry(
        business_object="customer_invoices",
        keywords=(
            "facture",
            "facture client",
            "factures",
            "factures client",
            "factures clients",
            "facture de vente",
            "factures de vente",
            "invoice",
            "invoices",
            "customer invoice",
            "customer invoices",
            "sales invoice",
            "sales invoices",
        ),
        model="account.move",
        safe_readable_fields=(
            "name",
            "partner_id",
            "invoice_date",
            "amount_total",
            "state",
            "payment_state",
            "currency_id",
        ),
        default_domain_filters=(
            {"field": "move_type", "operator": "=", "value": "out_invoice"},
        ),
        date_field_candidates=("invoice_date", "date", "create_date"),
        status_mappings={
            "posted": (
                "state",
                (
                    "validee",
                    "validees",
                    "valide",
                    "valides",
                    "postee",
                    "postees",
                    "poste",
                    "postes",
                    "confirmee",
                    "confirmees",
                    "confirme",
                    "confirmes",
                    "comptabilisee",
                    "comptabilisees",
                    "comptabilise",
                    "comptabilises",
                    "posted",
                    "validated",
                ),
            ),
            "draft": ("state", ("brouillon", "draft")),
            "cancel": ("state", ("annulee", "annulees", "annule", "annules", "cancelled", "canceled", "cancel")),
        },
    ),
    OdooBusinessCatalogEntry(
        business_object="vendor_bills",
        keywords=(
            "facture fournisseur",
            "factures fournisseur",
            "factures fournisseurs",
            "vendor bill",
            "vendor bills",
            "supplier invoice",
            "supplier invoices",
        ),
        model="account.move",
        safe_readable_fields=(
            "name",
            "partner_id",
            "invoice_date",
            "amount_total",
            "state",
            "payment_state",
            "currency_id",
        ),
        default_domain_filters=(
            {"field": "move_type", "operator": "=", "value": "in_invoice"},
        ),
        date_field_candidates=("invoice_date", "date", "create_date"),
        status_mappings={
            "posted": (
                "state",
                (
                    "validee",
                    "validees",
                    "valide",
                    "valides",
                    "postee",
                    "postees",
                    "poste",
                    "postes",
                    "confirmee",
                    "confirmees",
                    "confirme",
                    "confirmes",
                    "comptabilisee",
                    "comptabilisees",
                    "comptabilise",
                    "comptabilises",
                    "posted",
                    "validated",
                ),
            ),
            "draft": ("state", ("brouillon", "draft")),
            "cancel": ("state", ("annulee", "annulees", "annule", "annules", "cancelled", "canceled", "cancel")),
        },
    ),
    OdooBusinessCatalogEntry(
        business_object="sales_orders",
        keywords=(
            "commande client",
            "commandes client",
            "commande du client",
            "commandes du client",
            "commande de client",
            "commandes de client",
            "commande de vente",
            "commandes de vente",
            "devis",
            "sale order",
            "sale orders",
            "sales order",
            "sales orders",
            "quotation",
            "quotations",
        ),
        model="sale.order",
        safe_readable_fields=("name", "partner_id", "date_order", "state", "amount_total", "currency_id"),
        date_field_candidates=("date_order", "create_date"),
        status_mappings={
            "draft": ("state", ("brouillon", "draft", "devis")),
            ("sale", "done"): ("state", ("confirmee", "confirmees", "confirme", "confirmes", "confirmed")),
            "cancel": ("state", ("annulee", "annulees", "annule", "annules", "cancelled", "canceled", "cancel")),
        },
    ),
    OdooBusinessCatalogEntry(
        business_object="purchase_orders",
        keywords=(
            "bon de commande",
            "bons de commande",
            "bon de commande fournisseur",
            "bons de commande fournisseur",
            "commande fournisseur",
            "commandes fournisseur",
            "purchase order",
            "purchase orders",
        ),
        model="purchase.order",
        safe_readable_fields=("name", "partner_id", "date_order", "state", "amount_total", "currency_id"),
        date_field_candidates=("date_order", "create_date"),
        status_mappings={
            "draft": ("state", ("brouillon", "draft", "demande de prix")),
            ("purchase", "done"): ("state", ("confirmee", "confirmees", "confirme", "confirmes", "confirmed")),
            "cancel": ("state", ("annulee", "annulees", "annule", "annules", "cancelled", "canceled", "cancel")),
        },
    ),
    OdooBusinessCatalogEntry(
        business_object="employees",
        keywords=(
            "combien d'employes",
            "combien d employes",
            "combien de salaries",
            "combien de personnes travaillent",
            "combien de personnes qui travaillent",
            "effectif",
            "employe",
            "employes",
            "employee",
            "employees",
            "nombre de salaries",
            "nombre d'employes",
            "nombre d employes",
            "personnes travaillent",
            "salarie",
            "salaries",
            "staff count",
            "how many employees",
        ),
        model="hr.employee",
        model_candidates=("hr.employee", "res.users", "res.partner"),
        safe_readable_fields=("name", "work_email", "department_id", "job_title", "active"),
        default_domain_filters=(
            {"field": "active", "operator": "=", "value": True},
        ),
        date_field_candidates=("create_date", "write_date"),
    ),
    OdooBusinessCatalogEntry(
        business_object="contacts",
        keywords=("contact", "contacts", "client", "clients", "fournisseur", "fournisseurs", "partner", "partners"),
        model="res.partner",
        safe_readable_fields=("name", "email", "phone", "mobile", "company_type", "customer_rank", "supplier_rank"),
        date_field_candidates=("create_date", "write_date"),
    ),
    OdooBusinessCatalogEntry(
        business_object="analytic_accounts",
        keywords=("compte analytique", "comptes analytiques", "analytic account", "analytic accounts", "pointage"),
        model="account.analytic.account",
        safe_readable_fields=("name", "display_name", "code", "partner_id", "company_id", "amount", "balance", "currency_id", "x_studio_pointage"),
        date_field_candidates=("create_date", "write_date"),
    ),
    OdooBusinessCatalogEntry(
        business_object="products",
        keywords=("produit", "produits", "article", "articles", "product", "products", "inventory", "inventaire"),
        model="product.product",
        safe_readable_fields=("name", "display_name", "default_code", "qty_available", "virtual_available", "list_price", "uom_id"),
        date_field_candidates=("create_date", "write_date"),
    ),
)


MONTH_NAMES = {
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


REFERENCE_PATTERN = re.compile(
    r"\b(?=[A-Z0-9/.-]*\d)[A-Z]{1,8}[-/][A-Z0-9][A-Z0-9/.-]{3,}\b"
)


def match_business_catalog_entry(message: str) -> OdooBusinessCatalogEntry | None:
    text = normalize_business_text(message)
    matches = []

    for index, entry in enumerate(BUSINESS_MODEL_CATALOG):
        score = 0
        longest = 0
        for keyword in entry.keywords:
            normalized_keyword = normalize_business_text(keyword)
            if normalized_keyword and re.search(rf"\b{re.escape(normalized_keyword)}\b", text):
                score += 2 + normalized_keyword.count(" ")
                longest = max(longest, len(normalized_keyword))

        if score:
            matches.append((score, longest, -index, entry))

    if not matches:
        return None

    matches.sort(reverse=True)
    return matches[0][3]


def parse_business_period(message: str, today: date | None = None) -> dict | None:
    text = normalize_business_text(message)
    today = today or date.today()

    if re.search(r"\b(?:ce mois ci|ce mois-ci|this month)\b", text):
        start = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        end = today.replace(day=last_day)
        return {"start": start.isoformat(), "end": end.isoformat(), "period": "current_month"}

    if re.search(r"\b(?:cette annee|this year)\b", text):
        return {
            "start": f"{today.year:04d}-01-01",
            "end": f"{today.year:04d}-12-31",
            "period": "current_year",
        }

    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if not year_match:
        return None

    year = int(year_match.group(1))

    for label, value in MONTH_NAMES.items():
        day_match = re.search(
            rf"\b(?:du|le|on)?\s*(\d{{1,2}})\s+{re.escape(label)}\s+{year}\b",
            text,
        )
        if day_match:
            day = int(day_match.group(1))
            last_day = calendar.monthrange(year, value)[1]
            if 1 <= day <= last_day:
                return {
                    "start": f"{year:04d}-{value:02d}-{day:02d}",
                    "end": f"{year:04d}-{value:02d}-{day:02d}",
                    "period": "day",
                }

    month = None

    for label, value in MONTH_NAMES.items():
        if re.search(rf"\b{label}\b", text):
            month = value
            break

    if month is None:
        numeric_match = re.search(r"\b(?:mois|month)\s+(?:de\s+)?(\d{1,2})\b", text)
        if numeric_match:
            month = int(numeric_match.group(1))

    if month is None:
        return {"start": f"{year:04d}-01-01", "end": f"{year:04d}-12-31", "period": "year"}

    if month < 1 or month > 12:
        return None

    last_day = calendar.monthrange(year, month)[1]
    return {
        "start": f"{year:04d}-{month:02d}-01",
        "end": f"{year:04d}-{month:02d}-{last_day:02d}",
        "period": "month",
    }


def _operation_for_message(message: str) -> str:
    text = normalize_business_text(message)

    if _contains_any(text, {"combien", "count", "effectif", "how many", "nombre", "staff count"}):
        return "count"

    if _contains_any(text, {"detail", "details", "fiche", "information", "informations"}):
        return "details"

    if _contains_any(text, {"apparait", "apparaissent", "classement", "group by", "par ", "repartition", "top"}):
        return "aggregate"

    return "list"


def _limit_for_message(message: str, default: int = 10) -> int:
    text = normalize_business_text(message)
    text = re.sub(r"\b(?:mois|month)\s+(?:de\s+)?\d{1,2}\b", " ", text)
    text = re.sub(r"\b(?:19\d{2}|20\d{2})\b", " ", text)
    match = re.search(r"\b(\d{1,2})\b", text)
    if not match:
        return default

    value = int(match.group(1))
    if 1 <= value <= 20:
        return value

    return default


def _status_filters(entry: OdooBusinessCatalogEntry, message: str) -> list[dict]:
    text = normalize_business_text(message)
    filters = []

    for technical_value, mapping in entry.status_mappings.items():
        field_name, labels = mapping
        if any(re.search(rf"\b{re.escape(normalize_business_text(label))}\b", text) for label in labels):
            if isinstance(technical_value, (tuple, list, set)):
                filters.append({
                    "field": field_name,
                    "operator": "in",
                    "value": list(technical_value),
                })
            else:
                filters.append({"field": field_name, "operator": "=", "value": technical_value})

    return filters


def _sort_for_message(entry: OdooBusinessCatalogEntry, message: str) -> list[dict]:
    text = normalize_business_text(message)
    if not _contains_any(text, {"recent", "recents", "recente", "recentes", "dernier", "derniers", "derniere", "dernieres", "latest"}):
        return []

    sort = []
    if entry.date_field_candidates:
        sort.append({"field": entry.date_field_candidates[0], "direction": "desc"})

    sort.append({"field": "id", "direction": "desc"})
    return sort


def _comparison_filters(entry: OdooBusinessCatalogEntry, message: str) -> list[dict]:
    if entry.business_object != "products":
        return []

    text = normalize_business_text(message)
    match = re.search(
        r"\b(?:stock\s+disponible|available\s+stock|stock|quantite|quantity)\s+"
        r"(?:est\s+)?(?:superieur(?:e)?\s+a|supérieur(?:e)?\s+à|greater\s+than|above|>\s*)\s*(\d+(?:[.,]\d+)?)\b",
        text,
    )

    if not match:
        return []

    raw_value = match.group(1).replace(",", ".")
    value = float(raw_value) if "." in raw_value else int(raw_value)
    return [{"field": "qty_available", "operator": ">", "value": value}]


def _partner_filters(entry: OdooBusinessCatalogEntry, message: str) -> list[dict]:
    if "partner_id" not in entry.safe_readable_fields:
        return []

    text = normalize_business_text(message)
    match = re.search(
        r"\b(?:du|de|pour|avec|from|for)\s+"
        r"(?:client|customer|fournisseur|supplier|vendor|partenaire|partner)\s+(.+)$",
        text,
    )

    if not match:
        return []

    value = match.group(1)
    value = re.sub(
        r"\b(?:du|de|des|d|le|la|les|un|une|en|sur|dans|pour|mois|month)\b",
        " ",
        value,
    )
    value = re.sub(r"\b(?:19\d{2}|20\d{2})\b", " ", value)
    value = re.sub(r"\b\d{1,2}\b", " ", value)
    value = " ".join(value.strip(" .,:;!?\"'").split())

    if len(value) < 2:
        return []

    return [{"field": "partner_id", "operator": "ilike", "value": value}]


def _filters_to_domain(filters: list[dict]) -> list[list]:
    domain = []

    for item in filters or []:
        if not isinstance(item, dict):
            continue

        field_name = item.get("field")
        operator = item.get("operator")
        value = item.get("value")

        if field_name and operator:
            domain.append([field_name, operator, value])

    return domain


def extract_business_reference(message: str) -> str | None:
    match = REFERENCE_PATTERN.search((message or "").upper())
    return match.group(0) if match else None


def _query_for_message(entry: OdooBusinessCatalogEntry, message: str) -> str | None:
    if entry.business_object not in {
        "sales_orders",
        "purchase_orders",
        "customer_invoices",
        "vendor_bills",
    }:
        return None

    return extract_business_reference(message)


def build_odoo_query_plan(message: str, *, today: date | None = None) -> dict | None:
    entry = match_business_catalog_entry(message)
    if not entry:
        return None

    operation = _operation_for_message(message)
    filters = [dict(item) for item in entry.default_domain_filters]
    filters.extend(_status_filters(entry, message))
    filters.extend(_comparison_filters(entry, message))
    filters.extend(_partner_filters(entry, message))

    period = parse_business_period(message, today=today)
    date_field = entry.date_field_candidates[0] if entry.date_field_candidates else None

    if period and date_field:
        filters.extend([
            {"field": date_field, "operator": ">=", "value": period["start"]},
            {"field": date_field, "operator": "<=", "value": period["end"]},
        ])

    text = normalize_business_text(message)
    needs_official_headcount_clarification = (
        entry.business_object == "employees"
        and "jamain baco" in text
        and "odoo" not in text
    )

    action_by_operation = {
        "aggregate": "odoo_group_by",
        "count": "odoo_count_records",
        "details": "odoo_get_record_details",
        "list": "odoo_search_records",
        "search": "odoo_search_records",
    }
    fields = list(entry.safe_readable_fields)
    query = _query_for_message(entry, message)
    domain = _filters_to_domain(filters)

    return {
        "action": action_by_operation.get(operation, "odoo_search_records"),
        "operation": operation,
        "business_object": entry.business_object,
        "model": entry.model,
        "model_hint": entry.model,
        "model_candidates": list(entry.model_candidates or (entry.model,)),
        "filters": filters,
        "domain": domain,
        "fields": fields,
        "requested_fields": fields,
        "date_field_candidates": list(entry.date_field_candidates),
        "period": period,
        "sort": _sort_for_message(entry, message),
        "limit": _limit_for_message(message),
        "query": query,
        "catalog_entry": entry.business_object,
        "catalog_read": True,
        "needs_clarification": needs_official_headcount_clarification,
        "clarification_reason": (
            "official_or_odoo_headcount"
            if needs_official_headcount_clarification
            else None
        ),
    }


def build_odoo_catalog_read_plan(message: str, *, today: date | None = None) -> dict | None:
    return build_odoo_query_plan(message, today=today)
