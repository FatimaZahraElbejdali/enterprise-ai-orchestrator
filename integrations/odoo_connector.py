import os
import re
import time
import unicodedata
import xmlrpc.client
from dataclasses import dataclass, field

from dotenv import load_dotenv
from orchestrator.temporal import resolve_relative_period

load_dotenv()


PRODUCT_SEARCH_MODELS = {"product.product", "product.template"}

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

ACCOUNTING_BANK_READ_MODELS = (
    "account.bank.statement",
    "account.bank.statement.line",
    "account.move",
    "account.move.line",
    "account.journal",
)

SAFE_ACCOUNTING_BANK_FIELDS = {
    "account.bank.statement": [
        "id",
        "name",
        "display_name",
        "date",
        "journal_id",
        "balance",
        "balance_start",
        "balance_end_real",
        "ref",
    ],
    "account.bank.statement.line": [
        "id",
        "name",
        "display_name",
        "date",
        "journal_id",
        "partner_id",
        "amount",
        "balance",
        "ref",
        "payment_ref",
        "move_id",
        "statement_id",
    ],
    "account.move": [
        "id",
        "name",
        "display_name",
        "date",
        "invoice_date",
        "journal_id",
        "partner_id",
        "amount_total",
        "state",
        "payment_state",
        "currency_id",
        "move_type",
        "ref",
        "payment_ref",
    ],
    "account.move.line": [
        "id",
        "name",
        "display_name",
        "date",
        "journal_id",
        "partner_id",
        "balance",
        "amount_currency",
        "debit",
        "credit",
        "ref",
        "payment_ref",
        "move_id",
    ],
    "account.journal": [
        "id",
        "name",
        "display_name",
        "code",
        "type",
    ],
}

ALLOWED_GENERIC_WRITE_FIELDS = {
    "product.template": {"list_price", "standard_price"},
    "res.partner": {"phone", "mobile", "email"},
    "account.analytic.account": {"x_studio_pointage"},
}

DOCUMENT_MODELS = {
    "sale.order",
    "purchase.order",
    "account.move",
    "stock.picking",
}

DYNAMIC_READ_BUSINESS_BASE_MODELS = set(ALLOWED_GENERIC_READ_MODELS) | {
    "account.analytic.account",
}

DYNAMIC_READ_CACHE_TTL_SECONDS = 300
DYNAMIC_READ_DEFAULT_LIMIT = 10
DYNAMIC_READ_MAX_LIMIT = 20
DYNAMIC_READ_AGENT_MODEL_LIMIT = 8
DYNAMIC_READ_AGENT_FIELD_LIMIT = 40
DYNAMIC_READ_AGGREGATE_MAX_GROUPS = 50

DENIED_DYNAMIC_READ_MODELS = {
    "ir.config_parameter",
    "ir.model.access",
    "ir.rule",
    "ir.cron",
    "ir.mail_server",
    "res.config.settings",
    "res.users",
    "res.groups",
    "res.users.apikeys",
    "auth.oauth.provider",
    "auth.oauth.token",
    "payment.provider",
    "payment.token",
    "fetchmail.server",
}

DENIED_DYNAMIC_READ_PREFIXES = (
    "ir.",
    "auth.",
)

DENIED_DYNAMIC_READ_MODEL_TOKENS = {
    "apikey",
    "api_key",
    "credential",
    "handler",
    "password",
    "report",
    "secret",
    "session",
    "token",
    "transient",
    "wizard",
}

SECRET_FIELD_TOKENS = {
    "api_key",
    "apikey",
    "client_secret",
    "credential",
    "key",
    "oauth",
    "passwd",
    "password",
    "private",
    "secret",
    "session",
    "signature",
    "token",
}

SAFE_DYNAMIC_FIELD_TYPES = {
    "boolean",
    "char",
    "date",
    "datetime",
    "float",
    "html",
    "integer",
    "many2one",
    "monetary",
    "selection",
    "text",
}

MODEL_MATCH_STOPWORDS = {
    "a",
    "an",
    "app",
    "business",
    "de",
    "des",
    "du",
    "for",
    "in",
    "la",
    "le",
    "les",
    "list",
    "model",
    "models",
    "odoo",
    "record",
    "records",
    "related",
    "the",
    "to",
}


@dataclass(frozen=True)
class OdooReadPlan:
    operation: str
    business_object: str
    model_hint: str | None = None
    model_candidates: list[str] = field(default_factory=list)
    filters: list = field(default_factory=list)
    requested_fields: list[str] = field(default_factory=list)
    sort: list = field(default_factory=list)
    limit: int = DYNAMIC_READ_DEFAULT_LIMIT
    aggregate: dict | None = None
    record_id: int | None = None
    query: str | None = None

    @classmethod
    def from_mapping(cls, values: dict | None):
        values = values or {}
        operation = str(values.get("operation") or "list").strip().lower()
        if operation not in {"list", "search", "details", "count", "aggregate"}:
            operation = "list"

        try:
            limit = int(values.get("limit") or DYNAMIC_READ_DEFAULT_LIMIT)
        except (TypeError, ValueError):
            limit = DYNAMIC_READ_DEFAULT_LIMIT

        limit = max(1, min(limit, DYNAMIC_READ_MAX_LIMIT))

        record_id = values.get("record_id")
        try:
            record_id = int(record_id) if record_id not in {None, ""} else None
        except (TypeError, ValueError):
            record_id = None

        def list_value(key):
            value = values.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, str) and value.strip():
                return [
                    item.strip()
                    for item in value.split(",")
                    if item.strip()
                ]
            return []

        return cls(
            operation=operation,
            business_object=str(values.get("business_object") or "").strip(),
            model_hint=str(values.get("model_hint") or values.get("model") or "").strip() or None,
            model_candidates=list_value("model_candidates"),
            filters=list_value("filters"),
            requested_fields=list_value("requested_fields"),
            sort=list_value("sort"),
            limit=limit,
            aggregate=values.get("aggregate") if isinstance(values.get("aggregate"), dict) else None,
            record_id=record_id,
            query=str(values.get("query") or values.get("record_keyword") or "").strip() or None,
        )

    def to_dict(self):
        return {
            "operation": self.operation,
            "business_object": self.business_object,
            "model_hint": self.model_hint,
            "model_candidates": self.model_candidates,
            "filters": self.filters,
            "requested_fields": self.requested_fields,
            "sort": self.sort,
            "limit": self.limit,
            "aggregate": self.aggregate,
            "record_id": self.record_id,
            "query": self.query,
        }


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().split())


def _match_tokens(value: str) -> set[str]:
    tokens = set()

    for token in _normalize_label(value).replace(".", " ").replace("_", " ").replace("-", " ").split():
        if len(token) <= 2 or token in MODEL_MATCH_STOPWORDS:
            continue

        tokens.add(token)

        if token.endswith("ies") and len(token) > 4:
            tokens.add(token[:-3] + "y")
        if token.endswith("s") and len(token) > 4:
            tokens.add(token[:-1])
        if token.endswith("es") and len(token) > 4:
            tokens.add(token[:-2])

    return tokens


def _parse_month_year_period(value: str) -> tuple[str, str] | None:
    normalized = _normalize_label(value)
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
    year_match = re.search(r"\b(20\d{2}|19\d{2})\b", normalized)

    if not year_match:
        return None

    year = int(year_match.group(1))
    month = None

    for name, number in month_names.items():
        if re.search(rf"\b{name}\b", normalized):
            month = number
            break

    if month is None:
        numeric_match = re.search(r"\b(?:mois|month)\s+(\d{1,2})\b", normalized)
        if numeric_match:
            month = int(numeric_match.group(1))

    if month is None or month < 1 or month > 12:
        return None

    if month == 12:
        end_year = year + 1
        end_month = 1
    else:
        end_year = year
        end_month = month + 1

    return f"{year:04d}-{month:02d}-01", f"{end_year:04d}-{end_month:02d}-01"


def _accounting_period_label(date_metadata: dict | None) -> str:
    if not isinstance(date_metadata, dict):
        return ""

    start = str(date_metadata.get("start") or "")
    end = str(date_metadata.get("end") or "")
    month_labels = {
        "01": "janvier",
        "02": "février",
        "03": "mars",
        "04": "avril",
        "05": "mai",
        "06": "juin",
        "07": "juillet",
        "08": "août",
        "09": "septembre",
        "10": "octobre",
        "11": "novembre",
        "12": "décembre",
    }

    if re.match(r"^\d{4}-\d{2}-01$", start) and re.match(r"^\d{4}-\d{2}-01$", end):
        year = start[:4]
        month = start[5:7]
        next_month = int(month) + 1
        end_year = int(year)

        if next_month == 13:
            next_month = 1
            end_year += 1

        expected_end = f"{end_year:04d}-{next_month:02d}-01"

        if end == expected_end and month in month_labels:
            return f"en {month_labels[month]} {year}"

    if start and end:
        return f"entre {start} et {end}"

    return ""


def _contains_secret_token(value: str) -> bool:
    normalized = _normalize_label(value).replace(" ", "_")
    return any(token in normalized for token in SECRET_FIELD_TOKENS)


DOCUMENT_CONFIGS = {
    "sale.order": {
        "line_field": "order_line",
        "line_model": "sale.order.line",
        "date_field": "date_order",
        "reference_fields": ["name", "client_order_ref", "origin"],
        "blocked_states": {"cancel"},
        "line_fields": ["id", "product_id", "name", "product_uom_qty", "price_unit"],
        "allowed_line_fields": {"price_unit", "product_uom_qty"},
    },
    "purchase.order": {
        "line_field": "order_line",
        "line_model": "purchase.order.line",
        "date_field": "date_order",
        "reference_fields": ["name", "partner_ref", "origin"],
        "blocked_states": {"cancel"},
        "line_fields": ["id", "product_id", "name", "product_qty", "price_unit", "date_planned"],
        "allowed_line_fields": {"price_unit", "product_qty"},
    },
    "account.move": {
        "line_field": "invoice_line_ids",
        "line_model": "account.move.line",
        "date_field": "invoice_date",
        "reference_fields": ["name", "ref", "payment_reference"],
        "blocked_states": {"cancel", "posted"},
        "line_fields": ["id", "product_id", "name", "quantity", "price_unit"],
        "allowed_line_fields": {"price_unit", "quantity"},
    },
    "stock.picking": {
        "line_field": "move_ids_without_package",
        "line_model": "stock.move",
        "date_field": "scheduled_date",
        "reference_fields": ["name", "origin"],
        "blocked_states": {"cancel", "done"},
        "line_fields": ["id", "product_id", "name", "product_uom_qty"],
        "allowed_line_fields": {"product_uom_qty"},
    },
}

DOCUMENT_DATE_FIELDS = {
    "sale.order": {"date_order"},
    "purchase.order": {"date_order", "date_planned"},
    "account.move": {"invoice_date"},
    "stock.picking": {"scheduled_date"},
}


DOCUMENT_MODEL_TO_TYPE = {
    "sale.order": "sale_order",
    "purchase.order": "purchase_order",
    "account.move": "invoice",
    "stock.picking": "delivery",
}


class OdooConnector:
    def __init__(self):
        configured_url = (os.getenv("ODOO_URL") or "").strip().rstrip("/")
        self.url = configured_url or None
        self.database = os.getenv("ODOO_DB")
        self.username = os.getenv("ODOO_USERNAME")
        self.password = os.getenv("ODOO_PASSWORD")
        self.api_key = os.getenv("ODOO_API_KEY")

        self.auth_secret = self.api_key or self.password

        self.mock_mode = not (
            self.url
            and self.database
            and self.username
            and self.auth_secret
        )

        self.uid = None
        self._fields_cache = {}
        self._model_catalog_cache = None
        self._model_catalog_cached_at = 0.0

    def test_connection(self):
        if self.mock_mode:
            return {
                "connected": False,
                "mode": "mock",
                "url": self.url,
                "database_configured": bool(self.database),
                "username_configured": bool(self.username),
                "password_or_api_key_configured": bool(self.auth_secret),
                "message": "Odoo credentials are missing.",
            }

        try:
            uid = self.authenticate()

            return {
                "connected": True,
                "mode": "real_odoo",
                "url": self.url,
                "database": self.database,
                "username": self.username,
                "uid": uid,
                "database_configured": bool(self.database),
                "username_configured": bool(self.username),
                "password_or_api_key_configured": bool(self.auth_secret),
                "message": "Successfully connected to Odoo.",
            }

        except Exception as error:
            return {
                "connected": False,
                "mode": "real_odoo_error",
                "url": self.url,
                "database": self.database,
                "username": self.username,
                "database_configured": bool(self.database),
                "username_configured": bool(self.username),
                "password_or_api_key_configured": bool(self.auth_secret),
                "message": str(error),
            }

    def authenticate(self):
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")

        uid = common.authenticate(
            self.database,
            self.username,
            self.auth_secret,
            {},
        )

        if not uid:
            raise Exception(
                "Odoo authentication failed. Check database, username, and API key/password."
            )

        self.uid = uid
        return uid

    def _models(self):
        if not self.uid:
            self.authenticate()

        return xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def _product_search_domain(self, product_name: str):
        return self._or_domain([
            ["name", "ilike", product_name],
            ["default_code", "ilike", product_name],
        ])

    def _product_search_domain_for_model(self, model_name: str, product_name: str):
        if model_name not in PRODUCT_SEARCH_MODELS:
            raise ValueError("Unsupported Odoo product search model.")

        fields = self._existing_fields(
            model_name,
            ["name", "default_code", "barcode", "product_tmpl_id"],
        )
        conditions = []

        for field in ["name", "default_code", "barcode"]:
            if field in fields:
                conditions.append([field, "ilike", product_name])

        if model_name == "product.product" and "product_tmpl_id" in fields:
            conditions.append(["product_tmpl_id.name", "ilike", product_name])

        return self._or_domain(conditions)

    def _product_fields(self):
        return [
            "id",
            "name",
            "default_code",
            "qty_available",
            "virtual_available",
            "uom_id",
            "list_price",
            "currency_id",
            "sale_ok",
            "active",
        ]

    def _format_product_candidate(self, product: dict):
        unit = product.get("uom_id")
        template = product.get("product_tmpl_id")

        return {
            "id": product.get("id"),
            "name": product.get("name") or "",
            "default_code": product.get("default_code") or "",
            "barcode": product.get("barcode") or "",
            "template_name": (
                template[1]
                if isinstance(template, list) and len(template) > 1
                else ""
            ),
            "list_price": product.get("list_price"),
            "currency": self._m2o_name(product.get("currency_id")) or "MAD",
            "qty_available": product.get("qty_available"),
            "virtual_available": product.get("virtual_available"),
            "sale_ok": bool(product.get("sale_ok")),
            "active": bool(product.get("active", True)),
            "uom_id": unit[1] if isinstance(unit, list) and len(unit) > 1 else unit or "",
        }

    def _product_candidate_matches_query(self, candidate: dict, product_name: str) -> bool:
        normalized_query = _normalize_label(product_name)
        compact_query = normalized_query.replace(" ", "")

        if not normalized_query:
            return False

        for field in ("name", "default_code", "barcode", "template_name"):
            normalized_value = _normalize_label(candidate.get(field) or "")
            compact_value = normalized_value.replace(" ", "")

            if normalized_query in normalized_value:
                return True

            if compact_query and compact_query in compact_value:
                return True

        return False

    def _search_product_templates(self, domain, limit: int = 20):
        models = self._models()

        return models.execute_kw(
            self.database,
            self.uid,
            self.auth_secret,
            "product.template",
            "search_read",
            [domain],
            {
                "fields": self._product_fields(),
                "limit": limit,
                "context": {
                    "active_test": False,
                },
            },
        )

    def _search_products_for_inventory(self, product_name: str, limit: int = 5):
        models = self._models()
        remaining = limit
        results = []
        seen = set()

        for model_name in ["product.product", "product.template"]:
            domain = self._product_search_domain_for_model(model_name, product_name)

            if not domain or remaining <= 0:
                continue

            fields = self._existing_fields(
                model_name,
                self._product_fields() + ["barcode", "product_tmpl_id"],
            )
            products = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                model_name,
                "search_read",
                [domain],
                {
                    "fields": fields,
                    "limit": remaining,
                    "context": {
                        "active_test": False,
                    },
                },
            )

            for product in products:
                key = (model_name, product.get("id"))

                if key in seen:
                    continue

                formatted = self._format_product_candidate(product)

                if not self._product_candidate_matches_query(formatted, product_name):
                    continue

                formatted["model"] = model_name
                results.append(formatted)
                seen.add(key)
                remaining -= 1

                if remaining <= 0:
                    break

        return results

    def _resolve_single_candidate(
        self,
        products,
        resolution_strategy,
        product_query,
    ):
        candidates = [
            self._format_product_candidate(product)
            for product in products
        ]

        if len(candidates) == 1:
            return {
                "success": True,
                "found": True,
                "ambiguous": False,
                "product_query": product_query,
                "resolution_strategy": resolution_strategy,
                "product": candidates[0],
                "product_id": candidates[0]["id"],
                "candidates": candidates,
                "message": "Product resolved for write.",
            }

        if len(candidates) > 1:
            return {
                "success": False,
                "found": True,
                "ambiguous": True,
                "product_query": product_query,
                "resolution_strategy": resolution_strategy,
                "product": None,
                "product_id": None,
                "candidates": candidates,
                "message": "Produit ambigu — aucune modification exécutée.",
            }

        return None

    def _resolve_product_for_stock_read(self, product_query: str) -> dict:
        products = self._search_products_for_inventory(product_query, limit=20)

        if not products:
            return {
                "success": False,
                "found": False,
                "ambiguous": False,
                "product_query": product_query,
                "product": None,
                "product_id": None,
                "candidates": [],
                "message": "No product found in Odoo.",
            }

        normalized_query = _normalize_label(product_query)

        def candidate_labels(product):
            return {
                _normalize_label(str(product.get("name") or "")),
                _normalize_label(str(product.get("default_code") or "")),
                _normalize_label(str(product.get("barcode") or "")),
                _normalize_label(str(product.get("template_name") or "")),
            }

        exact_products = [
            product
            for product in products
            if normalized_query and normalized_query in candidate_labels(product)
        ]
        candidate_pool = exact_products or products
        variant_candidates = [
            product
            for product in candidate_pool
            if product.get("model") == "product.product"
        ]

        if variant_candidates:
            candidate_pool = variant_candidates

        deduped = []
        seen = set()

        for product in candidate_pool:
            identity = (
                _normalize_label(str(product.get("default_code") or "")),
                _normalize_label(str(product.get("barcode") or "")),
                _normalize_label(str(product.get("name") or "")),
                _normalize_label(str(product.get("template_name") or "")),
            )

            if identity in seen:
                continue

            seen.add(identity)
            deduped.append(product)

        if len(deduped) == 1:
            return {
                "success": True,
                "found": True,
                "ambiguous": False,
                "product_query": product_query,
                "resolution_strategy": "inventory_read_search",
                "product": deduped[0],
                "product_id": deduped[0].get("id"),
                "candidates": deduped,
                "message": "Product resolved for stock read.",
            }

        return {
            "success": False,
            "found": True,
            "ambiguous": True,
            "product_query": product_query,
            "resolution_strategy": "inventory_read_search",
            "product": None,
            "product_id": None,
            "candidates": deduped[:5],
            "message": "Produit ambigu — aucune consultation unique exécutée.",
        }

    def resolve_product_template_for_write(self, product_query: str) -> dict:
        if self.mock_mode:
            return {
                "success": False,
                "source": "mock_odoo",
                "model": "product.template",
                "found": False,
                "ambiguous": False,
                "product_query": product_query,
                "product": None,
                "product_id": None,
                "candidates": [],
                "message": "Odoo credentials are missing.",
            }

        try:
            prioritized_domains = [
                ("exact_name_sale_ok", [
                    ["name", "=ilike", product_query],
                    ["sale_ok", "=", True],
                ]),
                ("exact_default_code_sale_ok", [
                    ["default_code", "=ilike", product_query],
                    ["sale_ok", "=", True],
                ]),
                ("exact_name", [
                    ["name", "=ilike", product_query],
                ]),
                ("exact_default_code", [
                    ["default_code", "=ilike", product_query],
                ]),
            ]

            for resolution_strategy, domain in prioritized_domains:
                products = self._search_product_templates(domain, limit=20)
                result = self._resolve_single_candidate(
                    products,
                    resolution_strategy,
                    product_query,
                )

                if result:
                    result["source"] = "real_odoo"
                    result["model"] = "product.template"
                    return result

            fallback_products = self._search_product_templates(
                self._product_search_domain(product_query),
                limit=50,
            )
            result = self._resolve_single_candidate(
                fallback_products,
                "fallback_ilike",
                product_query,
            )

            if result:
                result["source"] = "real_odoo"
                result["model"] = "product.template"
                return result

            return {
                "success": False,
                "source": "real_odoo",
                "model": "product.template",
                "found": False,
                "ambiguous": False,
                "product_query": product_query,
                "product": None,
                "product_id": None,
                "candidates": [],
                "message": "No product found in Odoo. Price was not changed.",
            }

        except Exception as error:
            return {
                "success": False,
                "source": "real_odoo_error",
                "model": "product.template",
                "found": False,
                "ambiguous": False,
                "product_query": product_query,
                "product": None,
                "product_id": None,
                "candidates": [],
                "message": str(error),
            }

    def search_product_templates_for_debug(self, product_query: str):
        if self.mock_mode:
            return {
                "success": False,
                "source": "mock_odoo",
                "model": "product.template",
                "query": product_query,
                "found": False,
                "candidates": [],
                "message": "Odoo credentials are missing.",
            }

        try:
            products = self._search_product_templates(
                self._product_search_domain(product_query),
                limit=50,
            )
            candidates = [
                self._format_product_candidate(product)
                for product in products
            ]

            return {
                "success": True,
                "source": "real_odoo",
                "model": "product.template",
                "query": product_query,
                "found": len(candidates) > 0,
                "candidates": candidates,
            }

        except Exception as error:
            return {
                "success": False,
                "source": "real_odoo_error",
                "model": "product.template",
                "query": product_query,
                "found": False,
                "candidates": [],
                "message": str(error),
            }

    def get_product_template_by_id(self, product_id: int):
        if self.mock_mode:
            return {
                "success": False,
                "source": "mock_odoo",
                "model": "product.template",
                "found": False,
                "product_id": product_id,
                "product": None,
                "message": "Odoo credentials are missing.",
            }

        try:
            parsed_product_id = int(product_id)
            models = self._models()
            products = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "product.template",
                "read",
                [[parsed_product_id]],
                {
                    "fields": self._product_fields(),
                    "context": {
                        "active_test": False,
                    },
                },
            )

            if not products:
                return {
                    "success": False,
                    "source": "real_odoo",
                    "model": "product.template",
                    "found": False,
                    "product_id": parsed_product_id,
                    "product": None,
                    "message": "No product.template found for this ID.",
                }

            return {
                "success": True,
                "source": "real_odoo",
                "model": "product.template",
                "found": True,
                "product_id": parsed_product_id,
                "product": self._format_product_candidate(products[0]),
            }

        except Exception as error:
            return {
                "success": False,
                "source": "real_odoo_error",
                "model": "product.template",
                "found": False,
                "product_id": product_id,
                "product": None,
                "message": str(error),
            }

    def search_product(self, product_name: str):
        if self.mock_mode:
            return {
                "success": True,
                "source": "mock_odoo",
                "model": "product.product",
                "product": product_name,
                "found": True,
                "results": [
                    {
                        "id": "MOCK-PROD-001",
                        "name": product_name,
                        "default_code": "MOCK-REF",
                        "barcode": "",
                        "template_name": product_name,
                        "qty_available": 42,
                        "virtual_available": 42,
                        "list_price": 1.0,
                        "uom_id": [1, "Unité(s)"],
                    }
                ],
                "message": "Mock product result.",
            }

        try:
            products = self._search_products_for_inventory(
                product_name,
                limit=5,
            )

            return {
                "success": True,
                "source": "real_odoo",
                "model": "product.product",
                "product": product_name,
                "found": len(products) > 0,
                "results": products,
                "message": (
                    "Matching products found in Odoo inventory."
                    if products
                    else "No matching product found in Odoo inventory."
                ),
            }

        except Exception as error:
            return {
                "success": False,
                "source": "real_odoo_error",
                "model": "product.product",
                "product": product_name,
                "found": False,
                "results": [],
                "message": "Odoo product search is unavailable.",
            }

    def check_stock(self, product_name: str):
        if self.mock_mode:
            return {
                "source": "mock_odoo",
                "product": product_name,
                "product_name": product_name,
                "product_id": "MOCK-PROD-001",
                "metadata": {
                    "product_name": product_name,
                    "product_id": "MOCK-PROD-001",
                    "source": "mock_odoo",
                },
                "internal_reference": "MOCK-REF",
                "stock_quantity": 42,
                "forecast_quantity": 42,
                "sale_price": 1.0,
                "currency": "MAD",
                "unit": "Unité(s)",
                "warehouse": "Mock Warehouse",
                "found": True,
                "message": "Mock stock result.",
            }

        try:
            resolved = self._resolve_product_for_stock_read(product_name)

            if not resolved.get("product"):
                return {
                    "source": resolved.get("source", "real_odoo"),
                    "product": product_name,
                    "candidates": resolved.get("candidates", []),
                    "ambiguous": resolved.get("ambiguous", False),
                    "found": False,
                    "message": resolved.get("message", "No product found in Odoo."),
                }

            product = resolved["product"]
            product_name = product.get("name")
            product_id = product.get("id")

            return {
                "source": "real_odoo",
                "product": product_name,
                "product_name": product_name,
                "product_id": product_id,
                "metadata": {
                    "product_name": product_name,
                    "product_id": product_id,
                    "source": "real_odoo",
                },
                "internal_reference": product.get("default_code") or "-",
                "stock_quantity": product.get("qty_available"),
                "forecast_quantity": product.get("virtual_available"),
                "sale_price": product.get("list_price"),
                "currency": self._m2o_name(product.get("currency_id")) or "MAD",
                "sale_ok": product.get("sale_ok"),
                "active": product.get("active"),
                "unit": product.get("uom_id") or "-",
                "warehouse": "-",
                "found": True,
            }

        except Exception as error:
            return {
                "source": "real_odoo_error",
                "product": product_name,
                "found": False,
                "message": str(error),
            }

    def inventory_summary(self):
        if self.mock_mode:
            return {
                "success": True,
                "source": "mock_odoo",
                "model": "product.template",
                "product_count": 1,
                "sale_product_count": 1,
                "stockable_product_count": 1,
                "products_with_stock_count": 1,
                "products_without_stock_count": 0,
                "total_qty_available": 42,
                "total_virtual_available": 42,
                "message": "Mock inventory summary.",
            }

        try:
            models = self._models()
            product_count = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "product.template",
                "search_count",
                [[["active", "=", True]]],
            )
            sale_product_count = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "product.template",
                "search_count",
                [[["active", "=", True], ["sale_ok", "=", True]]],
            )
            stockable_product_count = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "product.product",
                "search_count",
                [[["active", "=", True], ["type", "=", "product"]]],
            )
            products_with_stock_count = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "product.product",
                "search_count",
                [[["active", "=", True], ["qty_available", ">", 0]]],
            )
            products_without_stock_count = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "product.product",
                "search_count",
                [[["active", "=", True], ["qty_available", "<=", 0]]],
            )
            grouped = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "product.product",
                "read_group",
                [[["active", "=", True]], ["qty_available", "virtual_available"], []],
            )
            totals = grouped[0] if grouped else {}

            return {
                "success": True,
                "source": "real_odoo",
                "model": "product.template",
                "product_count": product_count,
                "sale_product_count": sale_product_count,
                "stockable_product_count": stockable_product_count,
                "products_with_stock_count": products_with_stock_count,
                "products_without_stock_count": products_without_stock_count,
                "total_qty_available": totals.get("qty_available", 0),
                "total_virtual_available": totals.get("virtual_available", 0),
                "message": "Inventory summary read from Odoo.",
            }

        except Exception as error:
            return {
                "success": False,
                "source": "real_odoo_error",
                "model": "product.template",
                "found": False,
                "message": str(error),
            }

    def update_product_price(self, product_name: str, new_price: float) -> dict:
        try:
            parsed_price = float(new_price)
        except (TypeError, ValueError):
            return {
                "success": False,
                "source": "real_odoo",
                "model": "product.template",
                "action": "change_price",
                "product": product_name,
                "product_id": None,
                "old_price": None,
                "requested_price": new_price,
                "new_price": None,
                "executed": False,
                "verified": False,
                "found": False,
                "message": "Invalid product price.",
            }

        if self.mock_mode:
            return {
                "success": False,
                "source": "mock_odoo",
                "model": "product.template",
                "action": "change_price",
                "product": product_name,
                "product_id": None,
                "old_price": None,
                "requested_price": parsed_price,
                "new_price": None,
                "executed": False,
                "verified": False,
                "found": False,
                "message": "Odoo credentials are missing. Real price update was not executed.",
            }

        try:
            models = self._models()
            resolved = self.resolve_product_template_for_write(product_name)

            if resolved.get("ambiguous"):
                return {
                    "success": False,
                    "source": resolved.get("source", "real_odoo"),
                    "model": "product.template",
                    "action": "change_price",
                    "product": product_name,
                    "product_id": None,
                    "old_price": None,
                    "requested_price": parsed_price,
                    "new_price": None,
                    "executed": False,
                    "verified": False,
                    "found": True,
                    "ambiguous": True,
                    "candidates": resolved.get("candidates", []),
                    "message": "Produit ambigu — aucune modification exécutée.",
                }

            if not resolved.get("product_id"):
                return {
                    "success": False,
                    "source": resolved.get("source", "real_odoo"),
                    "model": "product.template",
                    "action": "change_price",
                    "product": product_name,
                    "product_id": None,
                    "old_price": None,
                    "requested_price": parsed_price,
                    "new_price": None,
                    "executed": False,
                    "verified": False,
                    "found": False,
                    "ambiguous": False,
                    "candidates": resolved.get("candidates", []),
                    "message": resolved.get("message", "No product found in Odoo. Price was not changed."),
                }

            product_id = resolved["product_id"]
            before_read = self.get_product_template_by_id(product_id)
            before_product = before_read.get("product") or {}
            old_price = before_product.get("list_price")

            write_success = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "product.template",
                "write",
                [[product_id], {"list_price": parsed_price}],
            )

            after_read = self.get_product_template_by_id(product_id)
            updated_product = after_read.get("product") or before_product
            updated_price = updated_product.get("list_price")
            verified = (
                bool(write_success)
                and updated_price is not None
                and abs(float(updated_price) - parsed_price) < 0.00001
            )

            return {
                "success": verified,
                "source": "real_odoo",
                "model": "product.template",
                "action": "change_price",
                "product": updated_product.get("name") or product_name,
                "product_id": product_id,
                "old_price": old_price,
                "requested_price": parsed_price,
                "new_price": updated_price,
                "executed": verified,
                "verified": verified,
                "found": True,
                "ambiguous": False,
                "candidates": resolved.get("candidates", []),
                "message": (
                    "Product price updated and verified in Odoo."
                    if verified
                    else "Odoo write returned but product.template list_price did not verify against requested price."
                ),
            }

        except Exception as error:
            return {
                "success": False,
                "source": "real_odoo_error",
                "model": "product.template",
                "action": "change_price",
                "product": product_name,
                "product_id": None,
                "old_price": None,
                "requested_price": parsed_price,
                "new_price": None,
                "executed": False,
                "verified": False,
                "found": False,
                "message": str(error),
            }

    def _model_fields(self, model_name: str):
        if model_name not in self._fields_cache:
            models = self._models()
            self._fields_cache[model_name] = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                model_name,
                "fields_get",
                [],
                {"attributes": ["string", "type"]},
            )

        return self._fields_cache[model_name]

    def _existing_fields(self, model_name: str, fields: list[str]):
        available = self._model_fields(model_name)
        return [field for field in fields if field in available]

    def _or_domain(self, conditions):
        if not conditions:
            return []

        if len(conditions) == 1:
            return conditions

        return ["|"] * (len(conditions) - 1) + conditions

    def _read_records(self, model_name: str, record_ids, fields: list[str]):
        if not record_ids:
            return []

        models = self._models()
        safe_fields = self._existing_fields(model_name, fields)

        return models.execute_kw(
            self.database,
            self.uid,
            self.auth_secret,
            model_name,
            "read",
            [record_ids],
            {"fields": safe_fields},
        )

    def _validate_generic_read_model(self, model_name: str):
        if model_name not in ALLOWED_GENERIC_READ_MODELS:
            raise ValueError("Unsupported Odoo model for generic read.")

    def _is_dynamic_read_model_allowed(self, model_name: str, display_name: str = "") -> bool:
        normalized_model = (model_name or "").strip().lower()
        normalized_display = _normalize_label(display_name)

        if not normalized_model:
            return False

        if normalized_model in DENIED_DYNAMIC_READ_MODELS:
            return False

        if any(normalized_model.startswith(prefix) for prefix in DENIED_DYNAMIC_READ_PREFIXES):
            return False

        policy_text = f"{normalized_model} {normalized_display}".replace(".", "_")

        if any(token in policy_text for token in DENIED_DYNAMIC_READ_MODEL_TOKENS):
            return False

        return True

    def refresh_model_catalog(self):
        self._model_catalog_cache = None
        self._model_catalog_cached_at = 0.0
        return self.get_model_catalog(force_refresh=True)

    def get_model_catalog(self, force_refresh: bool = False):
        if self.mock_mode:
            return []

        now = time.time()

        if (
            not force_refresh
            and self._model_catalog_cache is not None
            and now - self._model_catalog_cached_at < DYNAMIC_READ_CACHE_TTL_SECONDS
        ):
            return list(self._model_catalog_cache)

        models = self._models()
        raw_models = models.execute_kw(
            self.database,
            self.uid,
            self.auth_secret,
            "ir.model",
            "search_read",
            [[]],
            {
                "fields": ["model", "name"],
                "limit": 5000,
                "context": {"active_test": False},
            },
        )

        catalog = []

        for item in raw_models:
            model_name = item.get("model")
            display_name = item.get("name") or model_name
            allowed = self._is_dynamic_read_model_allowed(model_name, display_name)
            catalog.append({
                "model": model_name,
                "name": display_name,
                "allowed": allowed,
            })

        self._model_catalog_cache = catalog
        self._model_catalog_cached_at = now
        return list(catalog)

    def _dynamic_fields_get(self, model_name: str):
        cached_fields = self._fields_cache.get(model_name)
        needs_selection_metadata = bool(cached_fields) and any(
            metadata.get("type") == "selection" and "selection" not in metadata
            for metadata in cached_fields.values()
            if isinstance(metadata, dict)
        )

        if model_name not in self._fields_cache or needs_selection_metadata:
            models = self._models()
            self._fields_cache[model_name] = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                model_name,
                "fields_get",
                [],
                {"attributes": ["string", "type", "relation", "readonly", "store", "selection"]},
            )

        return self._fields_cache[model_name]

    def safe_dynamic_fields(self, model_name: str):
        fields = self._dynamic_fields_get(model_name)
        safe_fields = {}

        for field_name, metadata in fields.items():
            field_type = metadata.get("type")
            label = metadata.get("string") or field_name

            if field_type not in SAFE_DYNAMIC_FIELD_TYPES:
                continue

            if _contains_secret_token(field_name) or _contains_secret_token(label):
                continue

            safe_fields[field_name] = {
                "name": field_name,
                "label": label,
                "type": field_type,
                "relation": metadata.get("relation"),
                "readonly": bool(metadata.get("readonly", False)),
                "store": metadata.get("store", True) is not False,
            }

            if field_type == "selection" and isinstance(metadata.get("selection"), list):
                safe_fields[field_name]["selection"] = [
                    [option[0], option[1]]
                    for option in metadata.get("selection", [])
                    if isinstance(option, (list, tuple)) and len(option) >= 2
                ]

        return safe_fields

    def _resolve_dynamic_filter_field(self, safe_fields: dict, field_value):
        if not isinstance(field_value, str) or not field_value.strip():
            return None

        requested = field_value.strip()

        if requested in safe_fields:
            return requested

        normalized_requested = _normalize_label(requested)

        for field_name, metadata in safe_fields.items():
            candidates = {
                _normalize_label(field_name),
                _normalize_label(field_name.replace("_", " ")),
                _normalize_label(metadata.get("label") or ""),
            }

            if normalized_requested in candidates:
                return field_name

        return None

    def _selection_label_match(self, metadata: dict, value):
        if not isinstance(value, str):
            return None

        normalized_value = _normalize_label(value)

        for technical_value, display_label in metadata.get("selection") or []:
            if normalized_value == _normalize_label(str(technical_value)):
                return technical_value, display_label

            if normalized_value == _normalize_label(str(display_label)):
                return technical_value, display_label

        return None

    def _resolve_selection_filter_value(self, metadata: dict, value):
        if isinstance(value, list):
            resolved_values = []
            matched_labels = []

            for item in value:
                match = self._selection_label_match(metadata, item)

                if match:
                    resolved_values.append(match[0])
                    matched_labels.append(match[1])
                else:
                    resolved_values.append(item)

            return resolved_values, matched_labels

        match = self._selection_label_match(metadata, value)

        if match:
            return match[0], [match[1]]

        return value, []

    def _infer_selection_filter_field(self, safe_fields: dict, value):
        matches = []

        for field_name, metadata in safe_fields.items():
            if metadata.get("type") != "selection":
                continue

            if self._selection_label_match(metadata, value):
                matches.append(field_name)

        if len(matches) == 1:
            return matches[0]

        return None

    def _format_temporal_boundary(self, metadata: dict, value):
        if metadata.get("type") == "date":
            return value.date().isoformat()

        return value.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")

    def _resolve_temporal_filter_domain(self, field_name: str, metadata: dict, operator: str, value):
        if operator not in {"in_period", "relative_period"}:
            return None

        if metadata.get("type") not in {"date", "datetime"}:
            raise ValueError(f"invalid_temporal_field:{field_name}")

        interval = resolve_relative_period(value)
        start_value = self._format_temporal_boundary(metadata, interval["start"])
        end_value = self._format_temporal_boundary(metadata, interval["end"])

        return {
            "domain": [
                [field_name, ">=", start_value],
                [field_name, "<", end_value],
            ],
            "validated_filter": {
                "field": field_name,
                "operator": "relative_period",
                "value": {
                    "start": start_value,
                    "end": end_value,
                    "period": interval["period"],
                    "offset": interval["offset"],
                },
                "input_value": value,
                "field_type": metadata.get("type"),
                "matched_selection_labels": [],
            },
        }

    def _parse_dynamic_filter(self, filter_value):
        if isinstance(filter_value, dict):
            field_name = (
                filter_value.get("field")
                or filter_value.get("field_name")
                or filter_value.get("name")
                or filter_value.get("field_label")
                or filter_value.get("label")
            )
            operator = filter_value.get("operator") or filter_value.get("op") or "="
            value = (
                filter_value.get("value")
                if "value" in filter_value
                else filter_value.get("display_value")
            )
            return field_name, operator, value

        if isinstance(filter_value, (list, tuple)) and len(filter_value) >= 3:
            return filter_value[0], filter_value[1], filter_value[2]

        return None, None, None

    def _validated_dynamic_filter_domain(self, model_name: str, filters: list):
        if not filters:
            return [], []

        safe_fields = self.safe_dynamic_fields(model_name)
        allowed_operators = {
            "=",
            "!=",
            "in",
            "not in",
            "ilike",
            "not ilike",
            ">",
            ">=",
            "<",
            "<=",
        }
        domain = []
        validated_filters = []

        for raw_filter in filters:
            field_value, operator, value = self._parse_dynamic_filter(raw_filter)
            field_name = self._resolve_dynamic_filter_field(safe_fields, field_value)

            if not field_name:
                field_name = self._infer_selection_filter_field(safe_fields, value)

            if not field_name:
                continue

            metadata = safe_fields.get(field_name) or {}

            if metadata.get("store") is False:
                continue

            operator = str(operator or "=").strip().lower()

            temporal_filter = self._resolve_temporal_filter_domain(
                field_name,
                metadata,
                operator,
                value,
            )

            if temporal_filter:
                domain.extend(temporal_filter["domain"])
                validated_filters.append(temporal_filter["validated_filter"])
                continue

            if operator not in allowed_operators:
                operator = "="

            resolved_value = value
            matched_selection_labels = []

            if metadata.get("type") == "selection":
                resolved_value, matched_selection_labels = self._resolve_selection_filter_value(
                    metadata,
                    value,
                )

            if operator in {"in", "not in"} and not isinstance(resolved_value, list):
                resolved_value = [resolved_value]

            condition = [field_name, operator, resolved_value]
            domain.append(condition)
            validated_filters.append({
                "field": field_name,
                "operator": operator,
                "value": resolved_value,
                "input_value": value,
                "field_type": metadata.get("type"),
                "matched_selection_labels": matched_selection_labels,
            })

        return domain, validated_filters

    def _score_model_candidate(self, business_object: str, model_info: dict, model_hint: str | None = None):
        model_name = model_info.get("model") or ""
        display_name = model_info.get("name") or model_name
        query_tokens = _match_tokens(" ".join([business_object or "", model_hint or ""]))
        candidate_tokens = _match_tokens(f"{model_name} {display_name}")
        score = 0

        if model_hint and model_name == model_hint:
            score += 100

        score += 10 * len(query_tokens & candidate_tokens)

        for query_token in query_tokens:
            if query_token in _normalize_label(model_name).replace(".", " "):
                score += 4
            if query_token in _normalize_label(display_name):
                score += 4

        if model_name in DYNAMIC_READ_BUSINESS_BASE_MODELS or score > 0:
            try:
                field_score = 0

                for field_name, metadata in self.safe_dynamic_fields(model_name).items():
                    field_tokens = (
                        _match_tokens(field_name)
                        | _match_tokens(metadata.get("label") or "")
                    )
                    field_score += 15 * len(query_tokens & field_tokens)

                score += field_score
            except Exception:
                pass

        return score

    def discover_dynamic_read_model(self, business_object: str, model_hint: str | None = None):
        try:
            catalog = self.get_model_catalog()
        except Exception as error:
            return {
                "status": "failed",
                "model": None,
                "message": str(error),
                "candidates": [],
            }

        allowed_catalog = [
            item
            for item in catalog
            if item.get("allowed")
        ]
        model_names = {item.get("model") for item in catalog}

        if model_hint:
            if model_hint not in model_names:
                return {
                    "status": "rejected",
                    "model": None,
                    "message": "The proposed Odoo model is not installed.",
                    "candidates": [],
                }

            hinted = next((item for item in catalog if item.get("model") == model_hint), None)

            if not hinted or not hinted.get("allowed"):
                return {
                    "status": "rejected",
                    "model": None,
                    "message": "The proposed Odoo model is not allowed by dynamic read policy.",
                    "candidates": [],
                }

            return {
                "status": "found",
                "model": hinted.get("model"),
                "display_name": hinted.get("name") or hinted.get("model"),
                "score": 100,
                "candidates": [hinted],
            }

        scored = []

        for item in allowed_catalog:
            score = self._score_model_candidate(business_object, item)

            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda value: (-value[0], value[1].get("model") or ""))

        if not scored:
            return {
                "status": "not_found",
                "model": None,
                "message": "No safe installed Odoo model matches this business object.",
                "candidates": [],
            }

        top_score = scored[0][0]
        top_candidates = [
            item
            for score, item in scored
            if score == top_score
        ]

        if len(top_candidates) > 1:
            return {
                "status": "ambiguous",
                "model": None,
                "message": "Several safe installed Odoo models match this business object.",
                "candidates": [
                    {
                        "model": item.get("model"),
                        "label": item.get("name") or item.get("model"),
                    }
                    for item in top_candidates[:5]
                ],
            }

        best = top_candidates[0]
        return {
            "status": "found",
            "model": best.get("model"),
            "display_name": best.get("name") or best.get("model"),
            "score": top_score,
            "candidates": [
                {
                    "model": item.get("model"),
                    "label": item.get("name") or item.get("model"),
                    "score": score,
                }
                for score, item in scored[:5]
            ],
        }

    def agent_search_models(self, query: str, limit: int = DYNAMIC_READ_AGENT_MODEL_LIMIT):
        try:
            catalog = self.get_model_catalog()
        except Exception as error:
            return {
                "status": "failed",
                "tool": "odoo.search_models",
                "models": [],
                "message": str(error),
            }

        scored = []

        for item in catalog:
            if not item.get("allowed"):
                continue

            score = self._score_model_candidate(query, item)

            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda value: (-value[0], value[1].get("model") or ""))
        bounded_limit = max(1, min(int(limit or DYNAMIC_READ_AGENT_MODEL_LIMIT), DYNAMIC_READ_AGENT_MODEL_LIMIT))

        return {
            "status": "completed",
            "tool": "odoo.search_models",
            "query": query,
            "models": [
                {
                    "model": item.get("model"),
                    "label": item.get("name") or item.get("model"),
                    "score": score,
                    "available": True,
                }
                for score, item in scored[:bounded_limit]
            ],
        }

    def _agent_model_catalog_item(self, model_name: str):
        catalog = self.get_model_catalog()

        return next(
            (
                item
                for item in catalog
                if item.get("model") == model_name
            ),
            None,
        )

    def _validate_agent_model(self, model_name: str):
        item = self._agent_model_catalog_item(model_name)

        if not item:
            raise ValueError("unknown_model")

        if not item.get("allowed"):
            raise ValueError("denied_model")

        return item

    def agent_describe_model(self, model_name: str):
        try:
            item = self._validate_agent_model(model_name)
            safe_fields = self.safe_dynamic_fields(model_name)
        except ValueError as error:
            return {
                "status": "denied",
                "tool": "odoo.describe_model",
                "model": model_name,
                "message": str(error),
            }
        except Exception as error:
            return {
                "status": "failed",
                "tool": "odoo.describe_model",
                "model": model_name,
                "message": str(error),
            }

        fields = []

        for field_name, metadata in safe_fields.items():
            field = {
                "name": field_name,
                "label": metadata.get("label"),
                "type": metadata.get("type"),
                "relation": metadata.get("relation"),
                "store": metadata.get("store", True),
            }

            if metadata.get("type") == "selection":
                field["selection"] = metadata.get("selection") or []

            fields.append(field)

        fields.sort(key=lambda value: (value.get("name") not in {"display_name", "name", "state", "status"}, value.get("name") or ""))

        return {
            "status": "completed",
            "tool": "odoo.describe_model",
            "model": model_name,
            "label": item.get("name") or model_name,
            "fields": fields[:DYNAMIC_READ_AGENT_FIELD_LIMIT],
            "field_count": len(fields),
            "truncated": len(fields) > DYNAMIC_READ_AGENT_FIELD_LIMIT,
        }

    def _validate_agent_fields(self, model_name: str, requested_fields: list[str] | None):
        requested_fields = requested_fields or []
        safe_fields = self.safe_dynamic_fields(model_name)
        selected = []

        if not requested_fields:
            return self._dynamic_summary_fields(model_name)

        for field_name in requested_fields:
            if field_name == "id":
                if field_name not in selected:
                    selected.append(field_name)
                continue

            if field_name not in safe_fields:
                raise ValueError(f"unsafe_field:{field_name}")

            if field_name not in selected:
                selected.append(field_name)

        return selected[:DYNAMIC_READ_AGENT_FIELD_LIMIT] or ["id"]

    def _validate_agent_domain(self, model_name: str, domain: list | None):
        if not domain:
            return [], []

        if not isinstance(domain, list):
            raise ValueError("invalid_domain")

        if any(isinstance(item, str) and item in {"|", "&", "!"} for item in domain):
            raise ValueError("complex_domain_not_supported")

        for condition in domain:
            if not isinstance(condition, (list, tuple, dict)):
                raise ValueError("invalid_domain_condition")

        validated_domain, validated_filters = self._validated_dynamic_filter_domain(
            model_name,
            domain,
        )

        if len(validated_filters) != len(domain):
            raise ValueError("invalid_domain_field")

        return validated_domain, validated_filters

    def _validate_agent_order(self, model_name: str, order: str | None):
        if not order:
            return None

        safe_fields = self.safe_dynamic_fields(model_name)
        order_parts = []

        for raw_part in str(order).split(","):
            tokens = raw_part.strip().split()

            if not tokens:
                continue

            field_name = tokens[0]
            direction = tokens[1].lower() if len(tokens) > 1 else "asc"

            if field_name not in safe_fields and field_name != "id":
                raise ValueError(f"unsafe_order_field:{field_name}")

            if direction not in {"asc", "desc"}:
                direction = "asc"

            order_parts.append(f"{field_name} {direction}")

        return ", ".join(order_parts[:3]) or None

    def _validate_dynamic_sort(self, model_name: str, sort: list | None):
        if not sort:
            return None

        order_parts = []
        for item in sort[:3]:
            if isinstance(item, dict):
                field_name = item.get("field")
                direction = item.get("direction") or "asc"
            elif isinstance(item, str):
                tokens = item.split()
                field_name = tokens[0] if tokens else None
                direction = tokens[1] if len(tokens) > 1 else "asc"
            else:
                continue

            if not field_name:
                continue

            order_parts.append(f"{field_name} {direction}")

        return self._validate_agent_order(model_name, ", ".join(order_parts))

    def _validate_agent_group_by(self, model_name: str, group_by: list[str] | None):
        if not isinstance(group_by, list) or len(group_by) != 1:
            raise ValueError("invalid_group_by")

        safe_fields = self.safe_dynamic_fields(model_name)
        raw_field = group_by[0]
        field_name = self._resolve_dynamic_filter_field(safe_fields, raw_field)

        if not field_name:
            raise ValueError(f"unsafe_group_by_field:{raw_field}")

        metadata = safe_fields.get(field_name) or {}

        if metadata.get("store") is False:
            raise ValueError(f"nonstored_group_by_field:{field_name}")

        if metadata.get("type") not in {"boolean", "char", "date", "datetime", "integer", "many2one", "selection"}:
            raise ValueError(f"unsupported_group_by_type:{field_name}")

        return [field_name], {
            "field": field_name,
            "label": metadata.get("label"),
            "type": metadata.get("type"),
            "relation": metadata.get("relation"),
        }

    def _validate_agent_aggregates(self, model_name: str, aggregates: list[dict] | None):
        if not isinstance(aggregates, list) or not aggregates:
            aggregates = [{"operation": "count", "field": "id", "alias": "record_count"}]

        safe_fields = self.safe_dynamic_fields(model_name)
        validated = []

        for raw_aggregate in aggregates[:1]:
            if not isinstance(raw_aggregate, dict):
                raise ValueError("invalid_aggregate")

            operation = str(raw_aggregate.get("operation") or "").strip().lower()
            field_name = str(raw_aggregate.get("field") or "id").strip()
            alias = str(raw_aggregate.get("alias") or "record_count").strip() or "record_count"

            if operation != "count":
                raise ValueError(f"unsupported_aggregate_operation:{operation}")

            if field_name != "id":
                resolved_field = self._resolve_dynamic_filter_field(safe_fields, field_name)

                if not resolved_field:
                    raise ValueError(f"unsafe_aggregate_field:{field_name}")

                metadata = safe_fields.get(resolved_field) or {}

                if metadata.get("store") is False:
                    raise ValueError(f"nonstored_aggregate_field:{resolved_field}")

                field_name = resolved_field

            if not alias.replace("_", "").isalnum():
                alias = "record_count"

            validated.append({
                "operation": operation,
                "field": field_name,
                "alias": alias,
            })

        return validated

    def _validate_agent_aggregate_order(self, order_by: list[dict] | None, group_field: str, aggregate_aliases: set[str]):
        if not isinstance(order_by, list):
            return [{"field": "record_count", "direction": "desc"}]

        validated = []

        for raw_order in order_by[:2]:
            if not isinstance(raw_order, dict):
                continue

            field_name = str(raw_order.get("field") or "").strip()
            direction = str(raw_order.get("direction") or "asc").strip().lower()

            if field_name not in aggregate_aliases and field_name != group_field:
                raise ValueError(f"unsafe_aggregate_order_field:{field_name}")

            if direction not in {"asc", "desc"}:
                direction = "asc"

            validated.append({"field": field_name, "direction": direction})

        return validated or [{"field": "record_count", "direction": "desc"}]

    def _normalize_group_value(self, value):
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return {
                "id": value[0],
                "display_name": value[1],
            }

        return value

    def agent_aggregate_records(
        self,
        model_name: str,
        domain: list | None = None,
        group_by: list[str] | None = None,
        aggregates: list[dict] | None = None,
        order_by: list[dict] | None = None,
        limit: int = DYNAMIC_READ_DEFAULT_LIMIT,
    ):
        try:
            self._validate_agent_model(model_name)
            safe_domain, validated_filters = self._validate_agent_domain(model_name, domain)
            safe_group_by, group_metadata = self._validate_agent_group_by(model_name, group_by)
            safe_aggregates = self._validate_agent_aggregates(model_name, aggregates)
            aggregate_aliases = {item["alias"] for item in safe_aggregates}
            safe_order_by = self._validate_agent_aggregate_order(
                order_by,
                safe_group_by[0],
                aggregate_aliases,
            )
            bounded_limit = max(1, min(int(limit or DYNAMIC_READ_DEFAULT_LIMIT), DYNAMIC_READ_MAX_LIMIT))
            fetch_limit = min(DYNAMIC_READ_AGGREGATE_MAX_GROUPS, max(bounded_limit, DYNAMIC_READ_MAX_LIMIT))

            raw_groups = self._models().execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                model_name,
                "read_group",
                [safe_domain, safe_group_by, safe_group_by],
                {
                    "context": {"active_test": False},
                    "lazy": False,
                    "limit": fetch_limit,
                },
            )

            group_field = safe_group_by[0]
            count_alias = safe_aggregates[0]["alias"]
            normalized_groups = []

            for raw_group in raw_groups or []:
                if not isinstance(raw_group, dict):
                    continue

                group_value = self._normalize_group_value(raw_group.get(group_field))
                record_count = raw_group.get("__count")

                if record_count is None:
                    record_count = raw_group.get(f"{group_field}_count")

                if record_count is None:
                    record_count = raw_group.get(count_alias, 0)

                normalized_groups.append({
                    "group": {
                        "field": group_field,
                        "label": group_metadata.get("label"),
                        "type": group_metadata.get("type"),
                        "relation": group_metadata.get("relation"),
                        "value": group_value,
                    },
                    "metrics": {
                        count_alias: int(record_count or 0),
                    },
                })

            for order in reversed(safe_order_by):
                field_name = order["field"]
                reverse = order["direction"] == "desc"

                def sort_key(item):
                    if field_name in aggregate_aliases:
                        return item.get("metrics", {}).get(field_name, 0)

                    value = item.get("group", {}).get("value")

                    if isinstance(value, dict):
                        return str(value.get("display_name") or value.get("id") or "")

                    return str(value or "")

                normalized_groups.sort(key=sort_key, reverse=reverse)

            returned_groups = normalized_groups[:bounded_limit]

            return {
                "status": "completed",
                "tool": "odoo.aggregate_records",
                "model": model_name,
                "domain": safe_domain,
                "validated_filters": validated_filters,
                "group_by": safe_group_by,
                "aggregates": safe_aggregates,
                "order_by": safe_order_by,
                "group_count": len(returned_groups),
                "groups": returned_groups,
                "truncated": len(raw_groups or []) > bounded_limit,
                "error": None,
            }
        except Exception as error:
            return {
                "status": "denied" if isinstance(error, ValueError) else "failed",
                "tool": "odoo.aggregate_records",
                "model": model_name,
                "domain": [],
                "group_by": group_by or [],
                "group_count": 0,
                "groups": [],
                "message": str(error),
                "error": str(error),
            }

    def rank_purchase_order_suppliers(self, limit: int = 10):
        model_name = "purchase.order"
        aggregation_field = "partner_id"
        bounded_limit = max(1, min(int(limit or 10), DYNAMIC_READ_MAX_LIMIT))
        domain = []

        if model_name not in ALLOWED_GENERIC_READ_MODELS:
            return {
                "success": False,
                "source": "real_odoo",
                "status": "unsupported",
                "found": False,
                "selected_model": model_name,
                "aggregation_field": aggregation_field,
                "odoo_method": None,
                "domain_used": domain,
                "fields_used": [],
                "count_returned": 0,
                "records": [],
                "record_count": 0,
                "failure_reason": "unsupported_by_policy",
                "message": "La lecture des fournisseurs de bons de commande n'est pas autorisée par la politique actuelle.",
            }

        try:
            fields = self._existing_fields(model_name, ["id", aggregation_field])
        except Exception as error:
            return {
                "success": False,
                "source": "real_odoo_error",
                "status": "unsupported",
                "found": False,
                "selected_model": model_name,
                "aggregation_field": aggregation_field,
                "odoo_method": None,
                "domain_used": domain,
                "fields_used": [],
                "count_returned": 0,
                "records": [],
                "record_count": 0,
                "failure_reason": "missing_model",
                "message": "Le modèle purchase.order n'est pas disponible pour cette lecture.",
                "error": str(error),
            }

        if aggregation_field not in fields:
            return {
                "success": False,
                "source": "real_odoo",
                "status": "unsupported",
                "found": False,
                "selected_model": model_name,
                "aggregation_field": aggregation_field,
                "odoo_method": None,
                "domain_used": domain,
                "fields_used": fields,
                "count_returned": 0,
                "records": [],
                "record_count": 0,
                "failure_reason": "missing_field",
                "message": "Le champ fournisseur partner_id n'est pas disponible sur les bons de commande.",
            }

        try:
            raw_groups = self._models().execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                model_name,
                "read_group",
                [domain, [aggregation_field], [aggregation_field]],
                {
                    "context": {"active_test": False},
                    "lazy": False,
                    "limit": min(DYNAMIC_READ_AGGREGATE_MAX_GROUPS, max(bounded_limit, 10)),
                },
            )
            records = []

            for raw_group in raw_groups or []:
                group_value = self._normalize_group_value(raw_group.get(aggregation_field))

                if not isinstance(group_value, dict):
                    continue

                count = raw_group.get("__count")

                if count is None:
                    count = raw_group.get(f"{aggregation_field}_count", 0)

                records.append({
                    "supplier_id": group_value.get("id"),
                    "supplier": group_value.get("display_name"),
                    "count": int(count or 0),
                })

            records = [
                record
                for record in records
                if record.get("supplier") and record.get("count", 0) > 0
            ]
            records.sort(key=lambda item: item["count"], reverse=True)
            records = records[:bounded_limit]

            if records:
                return {
                    "success": True,
                    "source": "real_odoo",
                    "status": "completed",
                    "found": True,
                    "selected_model": model_name,
                    "aggregation_field": aggregation_field,
                    "odoo_method": "read_group",
                    "domain_used": domain,
                    "fields_used": [aggregation_field],
                    "count_returned": len(records),
                    "records": records,
                    "record_count": len(records),
                    "failure_reason": None,
                    "message": "Supplier ranking read from purchase orders.",
                }

            return {
                "success": False,
                "source": "real_odoo",
                "status": "not_found",
                "found": False,
                "selected_model": model_name,
                "aggregation_field": aggregation_field,
                "odoo_method": "read_group",
                "domain_used": domain,
                "fields_used": [aggregation_field],
                "count_returned": 0,
                "records": [],
                "record_count": 0,
                "failure_reason": "no_records",
                "message": "Aucun fournisseur n'a été trouvé dans les bons de commande.",
            }
        except Exception as read_group_error:
            try:
                raw_records = self._models().execute_kw(
                    self.database,
                    self.uid,
                    self.auth_secret,
                    model_name,
                    "search_read",
                    [domain],
                    {
                        "fields": ["id", aggregation_field],
                        "limit": min(DYNAMIC_READ_AGGREGATE_MAX_GROUPS, max(bounded_limit, 10)),
                        "context": {"active_test": False},
                    },
                )
            except Exception as fallback_error:
                return {
                    "success": False,
                    "source": "real_odoo_error",
                    "status": "failed",
                    "found": False,
                    "selected_model": model_name,
                    "aggregation_field": aggregation_field,
                    "odoo_method": "read_group",
                    "domain_used": domain,
                    "fields_used": [aggregation_field],
                    "count_returned": 0,
                    "records": [],
                    "record_count": 0,
                    "failure_reason": "read_group_failed",
                    "message": "Le classement des fournisseurs n'a pas pu être lu dans Odoo.",
                    "error": str(fallback_error),
                    "read_group_error": str(read_group_error),
                }

            counts = {}

            for record in raw_records or []:
                partner = record.get(aggregation_field)
                supplier_name = self._m2o_name(partner)
                supplier_id = self._m2o_id(partner)

                if not supplier_name:
                    continue

                key = (supplier_id, supplier_name)
                counts[key] = counts.get(key, 0) + 1

            records = [
                {
                    "supplier_id": supplier_id,
                    "supplier": supplier_name,
                    "count": count,
                }
                for (supplier_id, supplier_name), count in counts.items()
            ]
            records.sort(key=lambda item: item["count"], reverse=True)
            records = records[:bounded_limit]

            if records:
                return {
                    "success": True,
                    "source": "real_odoo",
                    "status": "completed",
                    "found": True,
                    "selected_model": model_name,
                    "aggregation_field": aggregation_field,
                    "odoo_method": "search_read_fallback",
                    "domain_used": domain,
                    "fields_used": ["id", aggregation_field],
                    "count_returned": len(records),
                    "records": records,
                    "record_count": len(records),
                    "failure_reason": None,
                    "message": "Supplier ranking read from bounded purchase order search.",
                    "read_group_error": str(read_group_error),
                }

            return {
                "success": False,
                "source": "real_odoo",
                "status": "not_found",
                "found": False,
                "selected_model": model_name,
                "aggregation_field": aggregation_field,
                "odoo_method": "search_read_fallback",
                "domain_used": domain,
                "fields_used": ["id", aggregation_field],
                "count_returned": 0,
                "records": [],
                "record_count": 0,
                "failure_reason": "no_records",
                "message": "Aucun fournisseur n'a été trouvé dans les bons de commande.",
                "read_group_error": str(read_group_error),
            }

    def rank_sale_order_customers(self, limit: int = 10):
        model_name = "sale.order"
        aggregation_field = "partner_id"
        bounded_limit = max(1, min(int(limit or 10), DYNAMIC_READ_MAX_LIMIT))
        domain = []

        if model_name not in ALLOWED_GENERIC_READ_MODELS:
            return {
                "success": False,
                "source": "real_odoo",
                "status": "unsupported",
                "found": False,
                "selected_model": model_name,
                "aggregation_field": aggregation_field,
                "odoo_method": None,
                "domain_used": domain,
                "fields_used": [],
                "count_returned": 0,
                "records": [],
                "record_count": 0,
                "failure_reason": "unsupported_by_policy",
                "message": "La lecture des clients de commandes client n'est pas autorisée par la politique actuelle.",
            }

        try:
            fields = self._existing_fields(model_name, ["id", aggregation_field])
        except Exception as error:
            return {
                "success": False,
                "source": "real_odoo_error",
                "status": "unsupported",
                "found": False,
                "selected_model": model_name,
                "aggregation_field": aggregation_field,
                "odoo_method": None,
                "domain_used": domain,
                "fields_used": [],
                "count_returned": 0,
                "records": [],
                "record_count": 0,
                "failure_reason": "missing_model",
                "message": "Le modèle sale.order n'est pas disponible pour cette lecture.",
                "error": str(error),
            }

        if aggregation_field not in fields:
            return {
                "success": False,
                "source": "real_odoo",
                "status": "unsupported",
                "found": False,
                "selected_model": model_name,
                "aggregation_field": aggregation_field,
                "odoo_method": None,
                "domain_used": domain,
                "fields_used": fields,
                "count_returned": 0,
                "records": [],
                "record_count": 0,
                "failure_reason": "missing_field",
                "message": "Le champ client partner_id n'est pas disponible sur les commandes client.",
            }

        try:
            raw_groups = self._models().execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                model_name,
                "read_group",
                [domain, [aggregation_field], [aggregation_field]],
                {
                    "context": {"active_test": False},
                    "lazy": False,
                    "limit": min(DYNAMIC_READ_AGGREGATE_MAX_GROUPS, max(bounded_limit, 10)),
                },
            )
            records = []

            for raw_group in raw_groups or []:
                group_value = self._normalize_group_value(raw_group.get(aggregation_field))

                if not isinstance(group_value, dict):
                    continue

                count = raw_group.get("__count")

                if count is None:
                    count = raw_group.get(f"{aggregation_field}_count", 0)

                records.append({
                    "customer_id": group_value.get("id"),
                    "customer": group_value.get("display_name"),
                    "count": int(count or 0),
                })

            records = [
                record
                for record in records
                if record.get("customer") and record.get("count", 0) > 0
            ]
            records.sort(key=lambda item: item["count"], reverse=True)
            records = records[:bounded_limit]

            if records:
                return {
                    "success": True,
                    "source": "real_odoo",
                    "status": "completed",
                    "found": True,
                    "selected_model": model_name,
                    "aggregation_field": aggregation_field,
                    "odoo_method": "read_group",
                    "domain_used": domain,
                    "fields_used": [aggregation_field],
                    "count_returned": len(records),
                    "records": records,
                    "record_count": len(records),
                    "failure_reason": None,
                    "message": "Customer ranking read from sale orders.",
                }

            return {
                "success": False,
                "source": "real_odoo",
                "status": "not_found",
                "found": False,
                "selected_model": model_name,
                "aggregation_field": aggregation_field,
                "odoo_method": "read_group",
                "domain_used": domain,
                "fields_used": [aggregation_field],
                "count_returned": 0,
                "records": [],
                "record_count": 0,
                "failure_reason": "no_records",
                "message": "Aucun client n'a été trouvé dans les commandes client.",
            }
        except Exception as read_group_error:
            try:
                raw_records = self._models().execute_kw(
                    self.database,
                    self.uid,
                    self.auth_secret,
                    model_name,
                    "search_read",
                    [domain],
                    {
                        "fields": ["id", aggregation_field],
                        "limit": min(DYNAMIC_READ_AGGREGATE_MAX_GROUPS, max(bounded_limit, 10)),
                        "context": {"active_test": False},
                    },
                )
            except Exception as fallback_error:
                return {
                    "success": False,
                    "source": "real_odoo_error",
                    "status": "failed",
                    "found": False,
                    "selected_model": model_name,
                    "aggregation_field": aggregation_field,
                    "odoo_method": "read_group",
                    "domain_used": domain,
                    "fields_used": [aggregation_field],
                    "count_returned": 0,
                    "records": [],
                    "record_count": 0,
                    "failure_reason": "read_group_failed",
                    "message": "Le classement des clients n'a pas pu être lu dans Odoo.",
                    "error": str(fallback_error),
                    "read_group_error": str(read_group_error),
                }

            counts = {}

            for record in raw_records or []:
                partner = record.get(aggregation_field)
                customer_name = self._m2o_name(partner)
                customer_id = self._m2o_id(partner)

                if not customer_name:
                    continue

                key = (customer_id, customer_name)
                counts[key] = counts.get(key, 0) + 1

            records = [
                {
                    "customer_id": customer_id,
                    "customer": customer_name,
                    "count": count,
                }
                for (customer_id, customer_name), count in counts.items()
            ]
            records.sort(key=lambda item: item["count"], reverse=True)
            records = records[:bounded_limit]

            if records:
                return {
                    "success": True,
                    "source": "real_odoo",
                    "status": "completed",
                    "found": True,
                    "selected_model": model_name,
                    "aggregation_field": aggregation_field,
                    "odoo_method": "search_read_fallback",
                    "domain_used": domain,
                    "fields_used": ["id", aggregation_field],
                    "count_returned": len(records),
                    "records": records,
                    "record_count": len(records),
                    "failure_reason": None,
                    "message": "Customer ranking read from bounded sale order search.",
                    "read_group_error": str(read_group_error),
                }

            return {
                "success": False,
                "source": "real_odoo",
                "status": "not_found",
                "found": False,
                "selected_model": model_name,
                "aggregation_field": aggregation_field,
                "odoo_method": "search_read_fallback",
                "domain_used": domain,
                "fields_used": ["id", aggregation_field],
                "count_returned": 0,
                "records": [],
                "record_count": 0,
                "failure_reason": "no_records",
                "message": "Aucun client n'a été trouvé dans les commandes client.",
                "read_group_error": str(read_group_error),
            }

    def agent_search_records(
        self,
        model_name: str,
        domain: list | None = None,
        fields: list[str] | None = None,
        limit: int = DYNAMIC_READ_DEFAULT_LIMIT,
        order: str | None = None,
    ):
        try:
            self._validate_agent_model(model_name)
            safe_domain, validated_filters = self._validate_agent_domain(model_name, domain)
            safe_fields = self._validate_agent_fields(model_name, fields)
            safe_order = self._validate_agent_order(model_name, order)
            bounded_limit = max(1, min(int(limit or DYNAMIC_READ_DEFAULT_LIMIT), DYNAMIC_READ_MAX_LIMIT))

            kwargs = {
                "fields": safe_fields,
                "limit": bounded_limit + 1,
                "context": {"active_test": False},
            }

            if safe_order:
                kwargs["order"] = safe_order

            raw_records = self._models().execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                model_name,
                "search_read",
                [safe_domain],
                kwargs,
            )
            records = [
                self._normalize_dynamic_record(model_name, record)
                for record in raw_records[:bounded_limit]
            ]

            return {
                "status": "completed",
                "tool": "odoo.search_records",
                "model": model_name,
                "domain": safe_domain,
                "validated_filters": validated_filters,
                "fields": safe_fields,
                "record_count": len(records),
                "records": records,
                "truncated": len(raw_records) > bounded_limit,
            }
        except Exception as error:
            return {
                "status": "denied" if isinstance(error, ValueError) else "failed",
                "tool": "odoo.search_records",
                "model": model_name,
                "record_count": 0,
                "records": [],
                "message": str(error),
            }

    def agent_count_records(self, model_name: str, domain: list | None = None):
        try:
            self._validate_agent_model(model_name)
            safe_domain, validated_filters = self._validate_agent_domain(model_name, domain)
            count = self._models().execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                model_name,
                "search_count",
                [safe_domain],
                {"context": {"active_test": False}},
            )

            return {
                "status": "completed",
                "tool": "odoo.count_records",
                "model": model_name,
                "domain": safe_domain,
                "validated_filters": validated_filters,
                "record_count": count,
            }
        except Exception as error:
            return {
                "status": "denied" if isinstance(error, ValueError) else "failed",
                "tool": "odoo.count_records",
                "model": model_name,
                "record_count": 0,
                "message": str(error),
            }

    def agent_read_record(self, model_name: str, record_id, fields: list[str] | None = None):
        try:
            self._validate_agent_model(model_name)
            safe_fields = self._validate_agent_fields(model_name, fields)
            record_id = int(record_id)
            raw_records = self._models().execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                model_name,
                "read",
                [[record_id]],
                {"fields": safe_fields},
            )
            records = [
                self._normalize_dynamic_record(model_name, record)
                for record in raw_records[:1]
            ]

            return {
                "status": "completed" if records else "not_found",
                "tool": "odoo.read_record",
                "model": model_name,
                "record_id": record_id,
                "record": records[0] if records else None,
            }
        except Exception as error:
            return {
                "status": "denied" if isinstance(error, ValueError) else "failed",
                "tool": "odoo.read_record",
                "model": model_name,
                "record_id": record_id,
                "record": None,
                "message": str(error),
            }

    def _dynamic_summary_fields(self, model_name: str, requested_fields: list[str] | None = None):
        safe_fields = self.safe_dynamic_fields(model_name)
        selected = ["id"]

        def add(field_name):
            if field_name == "id" and field_name not in selected:
                selected.append(field_name)
            elif field_name in safe_fields and field_name not in selected:
                selected.append(field_name)

        for field_name in requested_fields or []:
            add(field_name)

        priority_names = [
            "display_name",
            "name",
            "code",
            "reference",
            "ref",
            "partner_id",
            "customer_id",
            "client_id",
            "commercial_partner_id",
            "stage_id",
            "state",
            "status",
            "date",
            "date_order",
            "start_date",
            "end_date",
            "recurring_next_date",
            "amount_total",
            "recurring_total",
            "currency_id",
        ]

        for field_name in priority_names:
            add(field_name)

        if len(selected) < 6:
            for field_name, metadata in safe_fields.items():
                if metadata.get("type") in {"char", "selection", "date", "datetime", "many2one", "float", "monetary", "integer", "boolean"}:
                    add(field_name)
                if len(selected) >= 8:
                    break

        return selected[:8] or ["id"]

    def _dynamic_search_domain(self, model_name: str, query: str):
        if not query:
            return []

        fields = self.safe_dynamic_fields(model_name)
        searchable = [
            field_name
            for field_name, metadata in fields.items()
            if metadata.get("type") in {"char", "text", "html"}
            and field_name in {"name", "display_name", "code", "ref", "reference", "description"}
        ]

        conditions = [[field_name, "ilike", query] for field_name in searchable[:5]]
        return self._or_domain(conditions)

    def _dynamic_business_domain(self, model_name: str, business_text: str):
        query_tokens = _match_tokens(business_text)

        if not query_tokens:
            return []

        fields = self.safe_dynamic_fields(model_name)
        conditions = []

        for field_name, metadata in fields.items():
            if metadata.get("type") != "boolean":
                continue
            if metadata.get("store") is False:
                continue

            field_tokens = (
                _match_tokens(field_name)
                | _match_tokens(metadata.get("label") or "")
            )

            if query_tokens & field_tokens:
                conditions.append([field_name, "=", True])

        return conditions[:1]

    def _is_redundant_dynamic_query(self, query: str | None, business_object: str, model_hint: str | None):
        query_tokens = _match_tokens(query or "")

        if not query_tokens:
            return True

        scope_tokens = _match_tokens(" ".join([business_object or "", model_hint or ""]))

        return bool(scope_tokens) and query_tokens <= scope_tokens

    def _dynamic_executable_domain(self, model_name: str, plan: OdooReadPlan):
        business_domain = self._dynamic_business_domain(
            model_name,
            f"{plan.business_object} {plan.model_hint or ''}",
        )
        query_domain = []

        if not self._is_redundant_dynamic_query(
            plan.query,
            plan.business_object,
            plan.model_hint,
        ):
            query_domain = self._dynamic_search_domain(model_name, plan.query or "")

        filter_domain, validated_filters = self._validated_dynamic_filter_domain(
            model_name,
            plan.filters,
        )

        return {
            "domain": business_domain + query_domain + filter_domain,
            "business_scope_domain": business_domain,
            "query_domain": query_domain,
            "filter_domain": filter_domain,
            "validated_filters": validated_filters,
        }

    def _normalize_dynamic_record(self, model_name: str, record: dict):
        normalized = {}

        for key, value in record.items():
            if isinstance(value, list) and len(value) >= 2:
                normalized[key] = value[1]
            elif isinstance(value, tuple) and len(value) >= 2:
                normalized[key] = value[1]
            else:
                normalized[key] = value

        normalized["model"] = model_name
        return normalized

    def dynamic_read(self, read_plan: dict | OdooReadPlan):
        plan = read_plan if isinstance(read_plan, OdooReadPlan) else OdooReadPlan.from_mapping(read_plan)

        if self.mock_mode:
            return {
                "success": False,
                "source": "mock_odoo",
                "found": False,
                "status": "failed",
                "read_plan": plan.to_dict(),
                "records": [],
                "record_count": 0,
                "message": "Odoo credentials are missing.",
            }

        discovery = self.discover_dynamic_read_model(
            business_object=plan.business_object,
            model_hint=plan.model_hint,
        )

        if discovery.get("status") != "found" and plan.model_candidates:
            tried_models = {plan.model_hint} if plan.model_hint else set()

            for candidate_model in plan.model_candidates:
                if not candidate_model or candidate_model in tried_models:
                    continue

                tried_models.add(candidate_model)
                candidate_discovery = self.discover_dynamic_read_model(
                    business_object=plan.business_object,
                    model_hint=candidate_model,
                )

                if candidate_discovery.get("status") == "found":
                    discovery = candidate_discovery
                    break

        if (
            discovery.get("status") == "rejected"
            and plan.model_hint
            and plan.business_object
        ):
            discovery = self.discover_dynamic_read_model(
                business_object=f"{plan.business_object} {plan.model_hint}",
                model_hint=None,
            )

        if discovery.get("status") != "found":
            return {
                "success": False,
                "source": "real_odoo",
                "found": False,
                "status": discovery.get("status"),
                "read_plan": plan.to_dict(),
                "model": None,
                "display_name": None,
                "records": [],
                "record_count": 0,
                "candidates": discovery.get("candidates", []),
                "message": discovery.get("message") or "No safe Odoo model resolved.",
            }

        model_name = discovery["model"]
        fields = self._dynamic_summary_fields(model_name, plan.requested_fields)
        models = self._models()
        executable = self._dynamic_executable_domain(model_name, plan)
        domain = executable["domain"]
        business_scope_domain = executable["business_scope_domain"]
        query_domain = executable["query_domain"]
        validated_filters = executable["validated_filters"]
        order = self._validate_dynamic_sort(model_name, plan.sort)

        try:
            if plan.operation == "aggregate":
                return {
                    "success": False,
                    "source": "real_odoo",
                    "found": False,
                    "status": "unsupported_operation",
                    "read_plan": plan.to_dict(),
                    "model": model_name,
                    "display_name": discovery.get("display_name"),
                    "model_discovery": discovery,
                    "business_scope_domain": business_scope_domain,
                    "query_domain": query_domain,
                    "validated_filters": validated_filters,
                    "search_domain": domain,
                    "records": [],
                    "record_count": 0,
                    "message": "Aggregates are not enabled for generic Odoo reads yet.",
                }

            if plan.operation == "details" and plan.record_id is not None:
                raw_records = models.execute_kw(
                    self.database,
                    self.uid,
                    self.auth_secret,
                    model_name,
                    "read",
                    [[plan.record_id]],
                    {"fields": fields},
                )
            elif plan.operation == "count":
                count = models.execute_kw(
                    self.database,
                    self.uid,
                    self.auth_secret,
                    model_name,
                    "search_count",
                    [domain],
                    {"context": {"active_test": False}},
                )
                return {
                    "success": True,
                    "source": "real_odoo",
                    "found": True,
                    "status": "completed",
                    "read_plan": plan.to_dict(),
                    "model": model_name,
                    "display_name": discovery.get("display_name"),
                    "model_discovery": discovery,
                    "business_scope_domain": business_scope_domain,
                    "query_domain": query_domain,
                    "validated_filters": validated_filters,
                    "search_domain": domain,
                    "records": [],
                    "record_count": count,
                    "message": "Odoo records counted.",
                }
            else:
                search_kwargs = {
                    "fields": fields,
                    "limit": plan.limit,
                    "context": {"active_test": False},
                }

                if order:
                    search_kwargs["order"] = order

                raw_records = models.execute_kw(
                    self.database,
                    self.uid,
                    self.auth_secret,
                    model_name,
                    "search_read",
                    [domain],
                    search_kwargs,
                )
        except Exception as error:
            return {
                "success": False,
                "source": "real_odoo_error",
                "found": False,
                "status": "failed",
                "read_plan": plan.to_dict(),
                "model": model_name,
                "display_name": discovery.get("display_name"),
                "model_discovery": discovery,
                "business_scope_domain": business_scope_domain,
                "query_domain": query_domain,
                "validated_filters": validated_filters,
                "search_domain": domain,
                "records": [],
                "record_count": 0,
                "message": str(error),
            }

        records = [
            self._normalize_dynamic_record(model_name, record)
            for record in raw_records
        ]

        return {
            "success": True,
            "source": "real_odoo",
            "found": bool(records),
            "status": "completed" if records else "not_found",
            "read_plan": plan.to_dict(),
            "model": model_name,
            "display_name": discovery.get("display_name"),
            "model_discovery": discovery,
            "fields": fields,
            "business_scope_domain": business_scope_domain,
            "query_domain": query_domain,
            "validated_filters": validated_filters,
            "search_domain": domain,
            "order": order,
            "records": records,
            "record_count": len(records),
            "message": "Odoo records read safely.",
        }

    def _validate_generic_write_field(self, model_name: str, field_name: str):
        allowed_fields = ALLOWED_GENERIC_WRITE_FIELDS.get(model_name, set())

        if field_name not in allowed_fields:
            raise ValueError("Unsupported Odoo field for generic write.")

    def _generic_search_fields(self, model_name: str):
        self._validate_generic_read_model(model_name)
        candidate_fields = ["name", "display_name", "default_code", "ref", "barcode", "partner_id"]
        if model_name == "account.analytic.account":
            candidate_fields = ["name", "display_name", "code", "partner_id", "company_id"]

        fields = self._existing_fields(model_name, candidate_fields)
        conditions = [
            [field, "ilike", "{keyword}"]
            for field in ["name", "display_name", "default_code", "ref", "barcode", "code"]
            if field in fields
        ]

        if model_name in DOCUMENT_MODELS and "partner_id" in fields:
            conditions.append(["partner_id.name", "ilike", "{keyword}"])

        if model_name == "account.analytic.account":
            for relation_field in ["partner_id", "company_id"]:
                if relation_field in fields:
                    conditions.append([f"{relation_field}.name", "ilike", "{keyword}"])

        return conditions

    def _generic_summary_fields(self, model_name: str):
        base_fields = {
            "product.product": [
                "id",
                "name",
                "display_name",
                "default_code",
                "barcode",
                "qty_available",
                "virtual_available",
                "list_price",
                "currency_id",
            ],
            "product.template": [
                "id",
                "name",
                "display_name",
                "default_code",
                "barcode",
                "qty_available",
                "virtual_available",
                "list_price",
                "standard_price",
                "currency_id",
            ],
            "res.partner": [
                "id",
                "name",
                "display_name",
                "phone",
                "mobile",
                "email",
                "customer_rank",
                "supplier_rank",
                "is_company",
            ],
            "sale.order": ["id", "name", "display_name", "partner_id", "state", "date_order"],
            "purchase.order": ["id", "name", "display_name", "partner_id", "state", "date_order"],
            "account.bank.statement": SAFE_ACCOUNTING_BANK_FIELDS["account.bank.statement"],
            "account.bank.statement.line": SAFE_ACCOUNTING_BANK_FIELDS["account.bank.statement.line"],
            "account.journal": SAFE_ACCOUNTING_BANK_FIELDS["account.journal"],
            "account.move": SAFE_ACCOUNTING_BANK_FIELDS["account.move"],
            "account.move.line": SAFE_ACCOUNTING_BANK_FIELDS["account.move.line"],
            "stock.picking": ["id", "name", "display_name", "partner_id", "state", "scheduled_date", "origin"],
            "account.analytic.account": [
                "id",
                "name",
                "display_name",
                "code",
                "partner_id",
                "company_id",
                "amount",
                "balance",
                "currency_id",
                "x_studio_pointage",
            ],
        }

        return self._existing_fields(model_name, base_fields.get(model_name, ["id", "name"]))

    def _format_generic_record(self, model_name: str, record: dict):
        partner = self._m2o_name(record.get("partner_id"))
        record_id = record.get("id")

        if model_name in {"product.product", "product.template"}:
            return {
                "id": record_id,
                "model": model_name,
                "name": record.get("display_name") or record.get("name") or "",
                "internal_reference": record.get("default_code") or "",
                "barcode": record.get("barcode") or "",
                "stock_quantity": record.get("qty_available"),
                "forecast_quantity": record.get("virtual_available"),
                "price": record.get("list_price"),
                "standard_price": record.get("standard_price"),
                "currency": self._m2o_name(record.get("currency_id")) or "MAD",
            }

        if model_name == "res.partner":
            customer_rank = record.get("customer_rank") or 0
            supplier_rank = record.get("supplier_rank") or 0
            partner_type = []

            if customer_rank:
                partner_type.append("client")

            if supplier_rank:
                partner_type.append("fournisseur")

            return {
                "id": record_id,
                "model": model_name,
                "name": record.get("display_name") or record.get("name") or "",
                "type": ", ".join(partner_type) or "contact",
                "phone": record.get("phone") or record.get("mobile") or "",
                "email": record.get("email") or "",
            }

        if model_name in DOCUMENT_MODELS:
            date_value = (
                record.get("date_order")
                or record.get("invoice_date")
                or record.get("scheduled_date")
            )
            formatted = {
                "id": record_id,
                "model": model_name,
                "document": record.get("display_name") or record.get("name") or "",
                "reference": record.get("name") or record.get("ref") or record.get("origin") or "",
                "partner": partner,
                "status": record.get("state") or "",
                "date": date_value or "",
            }

            if model_name == "account.move":
                formatted.update({
                    "amount_total": record.get("amount_total"),
                    "payment_state": record.get("payment_state") or "",
                    "currency": self._m2o_name(record.get("currency_id")),
                    "move_type": record.get("move_type") or "",
                })

            return formatted

        if model_name in ACCOUNTING_BANK_READ_MODELS:
            amount = (
                record.get("amount")
                if "amount" in record
                else record.get("amount_total")
            )
            balance = (
                record.get("balance")
                if "balance" in record
                else record.get("balance_end_real")
            )
            return {
                "id": record_id,
                "model": model_name,
                "document": record.get("display_name") or record.get("name") or "",
                "reference": (
                    record.get("payment_ref")
                    or record.get("ref")
                    or record.get("name")
                    or ""
                ),
                "date": record.get("date") or record.get("invoice_date") or "",
                "journal": self._m2o_name(record.get("journal_id")),
                "partner": partner,
                "amount": amount,
                "balance": balance,
                "status": record.get("state") or record.get("type") or "",
                "move": self._m2o_name(record.get("move_id")),
                "statement": self._m2o_name(record.get("statement_id")),
            }

        if model_name == "account.analytic.account":
            return {
                "id": record_id,
                "model": model_name,
                "name": record.get("display_name") or record.get("name") or "",
                "reference": record.get("code") or "",
                "code": record.get("code") or "",
                "client": self._m2o_name(record.get("partner_id")),
                "partner": self._m2o_name(record.get("partner_id")),
                "company": self._m2o_name(record.get("company_id")),
                "amount": record.get("amount"),
                "balance": record.get("balance"),
                "currency": self._m2o_name(record.get("currency_id")),
                "pointage": record.get("x_studio_pointage"),
            }

        return {
            "id": record_id,
            "model": model_name,
            "name": record.get("display_name") or record.get("name") or "",
        }

    def _accounting_bank_query_domain(self, model_name: str, keyword: str, fields: list[str]):
        query_conditions = []

        for field in ["name", "display_name", "ref", "payment_ref", "code"]:
            if field in fields:
                query_conditions.append([field, "ilike", keyword])

        for field in ["journal_id", "partner_id", "move_id", "statement_id"]:
            if field in fields:
                query_conditions.append([f"{field}.name", "ilike", keyword])

        return self._or_domain(query_conditions)

    def _accounting_bank_date_domain(self, message: str, fields: list[str]):
        date_field = next(
            (
                field
                for field in ["date", "invoice_date"]
                if field in fields
            ),
            None,
        )
        period = _parse_month_year_period(message)

        if not period:
            return [], None

        if not date_field:
            return None, {
                "failure_reason": "missing_field",
                "message": "No safe date field is available for this accounting model.",
            }

        start, end = period
        return [[date_field, ">=", start], [date_field, "<", end]], {
            "date_field": date_field,
            "start": start,
            "end": end,
        }

    def search_bank_accounting_records(
        self,
        keyword: str,
        message: str = "",
        limit: int = 10,
        candidate_models: list[str] | None = None,
    ):
        if self.mock_mode:
            return {
                "success": False,
                "source": "mock_odoo",
                "status": "failed",
                "found": False,
                "candidate_models": [],
                "records": [],
                "record_count": 0,
                "failure_reason": "odoo_unavailable",
                "message": "Odoo credentials are missing.",
            }

        candidate_models = candidate_models or list(ACCOUNTING_BANK_READ_MODELS)
        bounded_limit = max(1, min(int(limit or 10), DYNAMIC_READ_MAX_LIMIT))
        allowed_models = [
            model
            for model in candidate_models
            if model in ALLOWED_GENERIC_READ_MODELS
            and model in ACCOUNTING_BANK_READ_MODELS
        ]

        if not allowed_models:
            return {
                "success": False,
                "source": "real_odoo",
                "status": "unsupported",
                "found": False,
                "candidate_models": [],
                "records": [],
                "record_count": 0,
                "failure_reason": "unsupported_by_policy",
                "message": (
                    "Odoo est connecté, mais le modèle nécessaire aux relevés bancaires "
                    "n’est pas disponible dans cette base ou n’est pas autorisé par la politique de lecture."
                ),
            }

        try:
            models = self._models()
        except Exception as error:
            return {
                "success": False,
                "source": "real_odoo_error",
                "status": "failed",
                "found": False,
                "candidate_models": allowed_models,
                "records": [],
                "record_count": 0,
                "failure_reason": "odoo_unavailable",
                "message": "Odoo search is unavailable for this request.",
                "error": str(error),
            }

        model_diagnostics = []
        queried_model_count = 0
        last_queried_diagnostic = {}

        for model_name in allowed_models:
            try:
                fields = self._existing_fields(
                    model_name,
                    SAFE_ACCOUNTING_BANK_FIELDS[model_name],
                )
            except Exception as error:
                model_diagnostics.append({
                    "model": model_name,
                    "failure_reason": "missing_model",
                    "message": str(error),
                })
                continue

            if not fields:
                model_diagnostics.append({
                    "model": model_name,
                    "failure_reason": "missing_field",
                    "fields_used": [],
                })
                continue

            date_domain, date_metadata = self._accounting_bank_date_domain(
                message or keyword,
                fields,
            )

            if date_domain is None:
                model_diagnostics.append({
                    "model": model_name,
                    "failure_reason": date_metadata["failure_reason"],
                    "fields_used": fields,
                    "message": date_metadata["message"],
                })
                continue

            query_domain = self._accounting_bank_query_domain(model_name, keyword, fields)
            domain = []

            if date_domain:
                domain.extend(date_domain)

            if query_domain:
                domain.extend(query_domain)

            try:
                raw_records = models.execute_kw(
                    self.database,
                    self.uid,
                    self.auth_secret,
                    model_name,
                    "search_read",
                    [domain],
                    {
                        "fields": fields,
                        "limit": bounded_limit,
                        "context": {"active_test": False},
                    },
                )
                queried_model_count += 1
            except Exception as error:
                model_diagnostics.append({
                    "model": model_name,
                    "failure_reason": "missing_model",
                    "fields_used": fields,
                    "domain_used": domain,
                    "message": str(error),
                })
                continue

            records = [
                self._format_generic_record(model_name, record)
                for record in raw_records
            ]

            diagnostic = {
                "model": model_name,
                "fields_used": fields,
                "domain_used": domain,
                "count_returned": len(records),
                "date_filter": date_metadata,
            }
            model_diagnostics.append(diagnostic)
            last_queried_diagnostic = diagnostic

            if records:
                period_label = _accounting_period_label(date_metadata)
                return {
                    "success": True,
                    "source": "real_odoo",
                    "status": "completed",
                    "found": True,
                    "candidate_models": allowed_models,
                    "selected_model": model_name,
                    "model": model_name,
                    "keyword": keyword,
                    "fields_used": fields,
                    "domain_used": domain,
                    "count_returned": len(records),
                    "date_filter": date_metadata,
                    "period_label": period_label,
                    "records": records,
                    "record_count": len(records),
                    "model_diagnostics": model_diagnostics,
                    "failure_reason": None,
                    "message": "Matching bank/accounting records found in Odoo.",
                }

        any_model_available = any(
            item.get("failure_reason") != "missing_model"
            for item in model_diagnostics
        )
        missing_field = next(
            (
                item
                for item in model_diagnostics
                if item.get("failure_reason") == "missing_field"
            ),
            None,
        )

        if not any_model_available:
            failure_reason = "missing_model"
            message_text = (
                "Odoo est connecté, mais le modèle nécessaire aux relevés bancaires "
                "n’est pas disponible dans cette base ou n’est pas autorisé par la politique de lecture."
            )
        elif missing_field and queried_model_count == 0:
            failure_reason = "missing_field"
            message_text = (
                "Le modèle existe, mais les champs nécessaires pour filtrer par banque/date "
                "ne sont pas disponibles."
            )
        else:
            failure_reason = "no_records"
            period_label = _accounting_period_label(last_queried_diagnostic.get("date_filter"))
            period_text = f" {period_label}" if period_label else " sur la période demandée"
            message_text = (
                f"Aucun relevé ou transaction bancaire correspondant à {keyword}"
                f"{period_text} n’a été trouvé."
            )

        last_diagnostic = last_queried_diagnostic or (model_diagnostics[-1] if model_diagnostics else {})
        return {
            "success": False,
            "source": "real_odoo",
            "status": "not_found" if failure_reason == "no_records" else "unsupported",
            "found": False,
            "candidate_models": allowed_models,
            "selected_model": last_diagnostic.get("model"),
            "model": last_diagnostic.get("model"),
            "keyword": keyword,
            "fields_used": last_diagnostic.get("fields_used") or [],
            "domain_used": last_diagnostic.get("domain_used") or [],
            "count_returned": 0,
            "date_filter": last_diagnostic.get("date_filter"),
            "period_label": _accounting_period_label(last_diagnostic.get("date_filter")),
            "records": [],
            "record_count": 0,
            "model_diagnostics": model_diagnostics,
            "failure_reason": failure_reason,
            "message": message_text,
        }

    def list_customer_invoices(self, filters: list | None = None, limit: int = 10):
        model_name = "account.move"

        if self.mock_mode:
            return {
                "success": False,
                "source": "mock_odoo",
                "model": model_name,
                "found": False,
                "records": [],
                "record_count": 0,
                "message": "Odoo credentials are missing.",
            }

        try:
            self._validate_generic_read_model(model_name)
            safe_fields = self.safe_dynamic_fields(model_name)
            required_fields = ["move_type", "invoice_date"]
            missing_fields = [field for field in required_fields if field not in safe_fields]

            if missing_fields:
                return {
                    "success": False,
                    "source": "real_odoo",
                    "model": model_name,
                    "found": False,
                    "status": "failed",
                    "records": [],
                    "record_count": 0,
                    "fields_used": [],
                    "domain_used": [],
                    "failure_reason": "missing_field",
                    "missing_fields": missing_fields,
                    "message": "Les champs nécessaires pour filtrer les factures clients ne sont pas disponibles.",
                }

            requested_fields = [
                "id",
                "name",
                "display_name",
                "partner_id",
                "invoice_date",
                "amount_total",
                "state",
                "payment_state",
                "currency_id",
                "move_type",
            ]
            fields = self._existing_fields(model_name, requested_fields)
            base_filters = [
                {"field": "move_type", "operator": "=", "value": "out_invoice"},
            ]
            user_filters = [
                item
                for item in (filters or [])
                if not (
                    isinstance(item, dict)
                    and item.get("field") == "move_type"
                )
            ]
            domain, validated_filters = self._validated_dynamic_filter_domain(
                model_name,
                base_filters + user_filters,
            )
            bounded_limit = max(1, min(int(limit or 10), 20))
            raw_records = self._models().execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                model_name,
                "search_read",
                [domain],
                {
                    "fields": fields,
                    "limit": bounded_limit,
                    "context": {"active_test": False},
                },
            )
            records = [
                self._format_generic_record(model_name, record)
                for record in raw_records
            ]

            return {
                "success": True,
                "source": "real_odoo",
                "model": model_name,
                "found": bool(records),
                "status": "completed" if records else "not_found",
                "records": records,
                "record_count": len(records),
                "fields_used": fields,
                "domain_used": domain,
                "search_domain": domain,
                "validated_filters": validated_filters,
                "failure_reason": None if records else "no_records",
                "message": (
                    "Factures clients trouvées dans Odoo."
                    if records
                    else "Aucune facture client ne correspond aux critères demandés."
                ),
            }
        except Exception as error:
            return {
                "success": False,
                "source": "real_odoo_error",
                "model": model_name,
                "found": False,
                "status": "failed",
                "records": [],
                "record_count": 0,
                "fields_used": [],
                "domain_used": [],
                "failure_reason": "odoo_error",
                "message": str(error),
            }

    def generic_search_records(self, model_name: str, keyword: str, limit: int = 6):
        if self.mock_mode:
            return {
                "success": False,
                "source": "mock_odoo",
                "model": model_name,
                "keyword": keyword,
                "found": False,
                "records": [],
                "message": "Odoo credentials are missing.",
            }

        try:
            self._validate_generic_read_model(model_name)
            search_conditions = self._generic_search_fields(model_name)
            domain = self._or_domain([
                [field, operator, keyword]
                for field, operator, _ in search_conditions
            ])

            if not domain:
                return {
                    "success": False,
                    "source": "real_odoo",
                    "model": model_name,
                    "keyword": keyword,
                    "found": False,
                    "records": [],
                    "message": "No safe searchable fields are available for this model.",
                }

            models = self._models()
            raw_records = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                model_name,
                "search_read",
                [domain],
                {
                    "fields": self._generic_summary_fields(model_name),
                    "limit": limit,
                    "context": {
                        "active_test": False,
                    },
                },
            )
            records = [
                self._format_generic_record(model_name, record)
                for record in raw_records
            ]

            return {
                "success": True,
                "source": "real_odoo",
                "model": model_name,
                "keyword": keyword,
                "found": bool(records),
                "records": records,
                "message": (
                    "Matching records found in Odoo."
                    if records
                    else "No matching record found in Odoo."
                ),
            }

        except Exception:
            return {
                "success": False,
                "source": "real_odoo_error",
                "model": model_name if model_name in ALLOWED_GENERIC_READ_MODELS else None,
                "keyword": keyword,
                "found": False,
                "records": [],
                "message": "Odoo search is unavailable for this request.",
            }

    def generic_get_record_details(
        self,
        model_name: str,
        record_id=None,
        keyword: str = "",
    ):
        if self.mock_mode:
            return {
                "success": False,
                "source": "mock_odoo",
                "model": model_name,
                "record_id": record_id,
                "found": False,
                "record": None,
                "message": "Odoo credentials are missing.",
            }

        try:
            self._validate_generic_read_model(model_name)
            resolved_id = record_id
            candidates = []

            if resolved_id is None:
                search = self.generic_search_records(model_name, keyword, limit=6)
                candidates = search.get("records", [])

                if len(candidates) != 1:
                    return {
                        "success": False,
                        "source": search.get("source", "real_odoo"),
                        "model": model_name,
                        "keyword": keyword,
                        "found": bool(candidates),
                        "ambiguous": len(candidates) > 1,
                        "record": None,
                        "candidates": candidates,
                        "message": (
                            "Multiple matching records found in Odoo."
                            if len(candidates) > 1
                            else "No matching record found in Odoo."
                        ),
                    }

                resolved_id = candidates[0].get("id")

            if model_name in DOCUMENT_MODELS:
                details = self._get_document_details(
                    model_name,
                    keyword or "",
                    document_id=resolved_id,
                )
                return details

            records = self._read_records(
                model_name,
                [resolved_id],
                self._generic_summary_fields(model_name),
            )

            if not records:
                return {
                    "success": False,
                    "source": "real_odoo",
                    "model": model_name,
                    "record_id": resolved_id,
                    "found": False,
                    "record": None,
                    "message": "No matching record found in Odoo.",
                }

            return {
                "success": True,
                "source": "real_odoo",
                "model": model_name,
                "record_id": resolved_id,
                "found": True,
                "record": self._format_generic_record(model_name, records[0]),
                "message": "Record details read from Odoo.",
            }

        except Exception:
            return {
                "success": False,
                "source": "real_odoo_error",
                "model": model_name if model_name in ALLOWED_GENERIC_READ_MODELS else None,
                "record_id": record_id,
                "found": False,
                "record": None,
                "message": "Odoo details are unavailable for this request.",
            }

    def prepare_generic_update_field(
        self,
        model_name: str,
        field_name: str,
        new_value,
        record_id=None,
        keyword: str = "",
    ):
        if self.mock_mode:
            return {
                "success": False,
                "source": "mock_odoo",
                "model": model_name,
                "field_name": field_name,
                "record_id": record_id,
                "found": False,
                "ambiguous": False,
                "candidates": [],
                "message": "Odoo credentials are missing.",
            }

        try:
            self._validate_generic_read_model(model_name)
            self._validate_generic_write_field(model_name, field_name)
            resolved_id = record_id
            candidates = []

            if resolved_id is None:
                search = self.generic_search_records(model_name, keyword, limit=6)
                candidates = search.get("records", [])

                if len(candidates) != 1:
                    return {
                        "success": False,
                        "source": search.get("source", "real_odoo"),
                        "model": model_name,
                        "field_name": field_name,
                        "keyword": keyword,
                        "record_id": None,
                        "found": bool(candidates),
                        "ambiguous": len(candidates) > 1,
                        "candidates": candidates,
                        "message": (
                            "Multiple matching records found in Odoo."
                            if len(candidates) > 1
                            else "No matching record found in Odoo."
                        ),
                    }

                resolved_id = candidates[0].get("id")

            records = self._read_records(
                model_name,
                [resolved_id],
                ["id", "name", "display_name", field_name],
            )

            if not records:
                return {
                    "success": False,
                    "source": "real_odoo",
                    "model": model_name,
                    "field_name": field_name,
                    "record_id": resolved_id,
                    "found": False,
                    "ambiguous": False,
                    "candidates": [],
                    "message": "No matching record found in Odoo.",
                }

            record = records[0]

            return {
                "success": True,
                "source": "real_odoo",
                "model": model_name,
                "field_name": field_name,
                "record_id": resolved_id,
                "record_name": record.get("display_name") or record.get("name") or str(resolved_id),
                "old_value": record.get(field_name),
                "new_value": new_value,
                "found": True,
                "ambiguous": False,
                "candidates": candidates,
                "message": "Record resolved for approval.",
            }

        except ValueError:
            return {
                "success": False,
                "source": "policy",
                "model": model_name if model_name in ALLOWED_GENERIC_READ_MODELS else None,
                "field_name": field_name,
                "record_id": record_id,
                "found": False,
                "ambiguous": False,
                "candidates": [],
                "message": "Unsupported Odoo write field.",
            }
        except Exception:
            return {
                "success": False,
                "source": "real_odoo_error",
                "model": model_name if model_name in ALLOWED_GENERIC_READ_MODELS else None,
                "field_name": field_name,
                "record_id": record_id,
                "found": False,
                "ambiguous": False,
                "candidates": [],
                "message": "Odoo record resolution is unavailable.",
            }

    def update_generic_field(
        self,
        model_name: str,
        record_id,
        field_name: str,
        new_value,
    ):
        if self.mock_mode:
            return {
                "success": False,
                "source": "mock_odoo",
                "model": model_name,
                "record_id": record_id,
                "field": field_name,
                "requested_value": new_value,
                "executed": False,
                "verified": False,
                "message": "Odoo credentials are missing. Real update was not executed.",
            }

        try:
            self._validate_generic_read_model(model_name)
            self._validate_generic_write_field(model_name, field_name)
            before_records = self._read_records(
                model_name,
                [record_id],
                ["id", "name", "display_name", field_name],
            )

            if not before_records:
                return {
                    "success": False,
                    "source": "real_odoo",
                    "model": model_name,
                    "record_id": record_id,
                    "field": field_name,
                    "requested_value": new_value,
                    "executed": False,
                    "verified": False,
                    "found": False,
                    "message": "No matching record found in Odoo.",
                }

            old_value = before_records[0].get(field_name)
            models = self._models()
            write_success = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                model_name,
                "write",
                [[record_id], {field_name: new_value}],
            )
            after_records = self._read_records(
                model_name,
                [record_id],
                ["id", "name", "display_name", field_name],
            )
            updated_record = after_records[0] if after_records else {}
            actual_value = updated_record.get(field_name)
            verified = bool(write_success) and str(actual_value) == str(new_value)

            return {
                "success": verified,
                "source": "real_odoo",
                "model": model_name,
                "record_id": record_id,
                "record": updated_record.get("display_name") or updated_record.get("name") or str(record_id),
                "field": field_name,
                "old_value": old_value,
                "requested_value": new_value,
                "new_value": actual_value,
                "executed": verified,
                "verified": verified,
                "found": True,
                "message": (
                    "Odoo field updated and verified."
                    if verified
                    else "Odoo write returned but read-back verification failed."
                ),
            }

        except Exception:
            return {
                "success": False,
                "source": "real_odoo_error",
                "model": model_name if model_name in ALLOWED_GENERIC_READ_MODELS else None,
                "record_id": record_id,
                "field": field_name,
                "requested_value": new_value,
                "executed": False,
                "verified": False,
                "message": "Odoo update is unavailable for this request.",
            }

    def _m2o_name(self, value):
        if isinstance(value, list) and len(value) > 1:
            return value[1]

        return value or ""

    def _m2o_id(self, value):
        if isinstance(value, list) and value:
            return value[0]

        return value

    def _document_base_fields(self, model_name: str):
        config = DOCUMENT_CONFIGS[model_name]

        return [
            "id",
            "name",
            "partner_id",
            "state",
            config["date_field"],
            config["line_field"],
        ]

    def _format_document_candidate(self, model_name: str, record: dict):
        config = DOCUMENT_CONFIGS[model_name]
        partner = record.get("partner_id")
        date_field = config["date_field"]

        return {
            "id": record.get("id"),
            "record_id": record.get("id"),
            "name": record.get("name") or "",
            "partner": self._m2o_name(partner),
            "partner_id": self._m2o_id(partner),
            "state": record.get("state") or "",
            "date": record.get(date_field) or "",
            "model": model_name,
        }

    def _empty_document_result(self, model_name: str, query: str, message: str):
        return {
            "success": False,
            "found": False,
            "ambiguous": False,
            "model": model_name,
            "record_id": None,
            "name": "",
            "partner": "",
            "state": "",
            "date": "",
            "query": query,
            "candidates": [],
            "message": message,
        }

    def _document_result_from_candidates(
        self,
        model_name: str,
        query: str,
        records,
        ambiguous_message: str = "Document ambigu — aucune modification exécutée.",
    ):
        candidates = [
            self._format_document_candidate(model_name, record)
            for record in records
        ]

        if len(candidates) == 1:
            candidate = candidates[0]

            return {
                "success": True,
                "found": True,
                "ambiguous": False,
                "model": model_name,
                "record_id": candidate["record_id"],
                "name": candidate["name"],
                "partner": candidate["partner"],
                "state": candidate["state"],
                "date": candidate["date"],
                "query": query,
                "candidates": candidates,
                "message": "Document resolved.",
            }

        if len(candidates) > 1:
            return {
                "success": False,
                "found": True,
                "ambiguous": True,
                "model": model_name,
                "record_id": None,
                "name": "",
                "partner": "",
                "state": "",
                "date": "",
                "query": query,
                "candidates": candidates,
                "message": ambiguous_message,
            }

        return None

    def _search_document_records(self, model_name: str, query: str, exact: bool):
        config = DOCUMENT_CONFIGS[model_name]
        operator = "=ilike" if exact else "ilike"
        fields = self._existing_fields(model_name, config["reference_fields"])
        conditions = [[field, operator, query] for field in fields]
        partner_ids = self._search_partner_ids_by_name(query, exact)

        if partner_ids:
            conditions.append(["partner_id", "in", partner_ids])

        domain = self._or_domain(conditions) if conditions else [["name", operator, query]]
        models = self._models()

        return models.execute_kw(
            self.database,
            self.uid,
            self.auth_secret,
            model_name,
            "search_read",
            [domain],
            {
                "fields": self._existing_fields(
                    model_name,
                    self._document_base_fields(model_name),
                ),
                "limit": 20,
                "context": {"active_test": False},
            },
        )

    def _search_document_by_exact_name(self, model_name: str, query: str):
        models = self._models()

        return models.execute_kw(
            self.database,
            self.uid,
            self.auth_secret,
            model_name,
            "search_read",
            [[["name", "=", query]]],
            {
                "fields": self._existing_fields(
                    model_name,
                    self._document_base_fields(model_name),
                ),
                "limit": 20,
                "context": {"active_test": False},
            },
        )

    def _read_document_by_id(self, model_name: str, document_id: int):
        try:
            parsed_id = int(document_id)
        except (TypeError, ValueError):
            return []

        return self._read_records(
            model_name,
            [parsed_id],
            self._document_base_fields(model_name),
        )

    def _search_document_by_exact_name_and_partner(
        self,
        model_name: str,
        query: str,
        partner_name: str,
    ):
        partner_ids = (
            self._search_partner_ids_by_name(partner_name, exact=True)
            or self._search_partner_ids_by_name(partner_name, exact=False)
        )

        if not partner_ids:
            return []

        models = self._models()

        return models.execute_kw(
            self.database,
            self.uid,
            self.auth_secret,
            model_name,
            "search_read",
            [[
                ["name", "=", query],
                ["partner_id", "in", partner_ids],
            ]],
            {
                "fields": self._existing_fields(
                    model_name,
                    self._document_base_fields(model_name),
                ),
                "limit": 20,
                "context": {"active_test": False},
            },
        )

    def _search_partner_ids_by_name(self, query: str, exact: bool):
        operator = "=ilike" if exact else "ilike"
        models = self._models()

        try:
            return models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "res.partner",
                "search",
                [[["name", operator, query]]],
                {
                    "limit": 20,
                    "context": {"active_test": False},
                },
            )
        except Exception:
            return []

    def _resolve_document(
        self,
        model_name: str,
        query: str | None = None,
        document_id: int | None = None,
        partner_name: str | None = None,
    ):
        query = query or ""

        if self.mock_mode:
            return self._empty_document_result(
                model_name,
                query,
                "Odoo credentials are missing.",
            )

        if model_name not in DOCUMENT_CONFIGS:
            return self._empty_document_result(
                model_name,
                query,
                "Unsupported Odoo document model.",
            )

        try:
            if document_id is not None:
                id_records = self._read_document_by_id(model_name, document_id)
                id_result = self._document_result_from_candidates(
                    model_name,
                    str(document_id),
                    id_records,
                )

                if id_result:
                    id_result["source"] = "real_odoo"
                    return id_result

                result = self._empty_document_result(
                    model_name,
                    str(document_id),
                    "No matching Odoo document found for this ID.",
                )
                result["source"] = "real_odoo"
                return result

            if query and partner_name:
                partner_records = self._search_document_by_exact_name_and_partner(
                    model_name,
                    query,
                    partner_name,
                )
                partner_result = self._document_result_from_candidates(
                    model_name,
                    query,
                    partner_records,
                    ambiguous_message=(
                        "Document ambigu pour cette référence et ce partenaire — "
                        "aucune modification exécutée."
                    ),
                )

                if partner_result:
                    partner_result["source"] = "real_odoo"
                    partner_result["partner_filter"] = partner_name
                    return partner_result

            exact_name_records = self._search_document_by_exact_name(model_name, query)
            exact_name_result = self._document_result_from_candidates(
                model_name,
                query,
                exact_name_records,
            )

            if exact_name_result:
                exact_name_result["source"] = "real_odoo"
                return exact_name_result

            exact_records = self._search_document_records(model_name, query, exact=True)
            exact_result = self._document_result_from_candidates(
                model_name,
                query,
                exact_records,
            )

            if exact_result:
                exact_result["source"] = "real_odoo"
                return exact_result

            fallback_records = self._search_document_records(model_name, query, exact=False)
            fallback_result = self._document_result_from_candidates(
                model_name,
                query,
                fallback_records,
            )

            if fallback_result:
                fallback_result["source"] = "real_odoo"
                return fallback_result

            result = self._empty_document_result(
                model_name,
                query,
                "No matching Odoo document found.",
            )
            result["source"] = "real_odoo"
            return result

        except Exception as error:
            result = self._empty_document_result(model_name, query, str(error))
            result["source"] = "real_odoo_error"
            return result

    def search_sale_order(self, query: str) -> dict:
        return self._resolve_document("sale.order", query)

    def search_purchase_order(self, query: str) -> dict:
        return self._resolve_document("purchase.order", query)

    def search_invoice(self, query: str) -> dict:
        return self._resolve_document("account.move", query)

    def search_delivery_order(self, query: str) -> dict:
        return self._resolve_document("stock.picking", query)

    def _product_variant_map(self, product_ids):
        product_ids = [product_id for product_id in product_ids if product_id]

        if not product_ids:
            return {}

        products = self._read_records(
            "product.product",
            product_ids,
            ["id", "name", "default_code"],
        )

        return {product.get("id"): product for product in products}

    def _format_document_line(self, model_name: str, line: dict, product_map: dict):
        product_id = self._m2o_id(line.get("product_id"))
        product = product_map.get(product_id, {})
        config = DOCUMENT_CONFIGS[model_name]
        quantity_field = (
            "product_uom_qty"
            if "product_uom_qty" in config["line_fields"]
            else "product_qty"
            if "product_qty" in config["line_fields"]
            else "quantity"
        )

        formatted = {
            "line_id": line.get("id"),
            "id": line.get("id"),
            "product_id": product_id,
            "product": product.get("name") or self._m2o_name(line.get("product_id")),
            "product_name": product.get("name") or self._m2o_name(line.get("product_id")),
            "default_code": product.get("default_code") or "",
            "quantity": line.get(quantity_field),
        }

        if "price_unit" in line:
            formatted["price_unit"] = line.get("price_unit")

        return formatted

    def _get_document_details(
        self,
        model_name: str,
        query: str | None = None,
        document_id: int | None = None,
        partner_name: str | None = None,
    ):
        resolved = self._resolve_document(
            model_name,
            query,
            document_id=document_id,
            partner_name=partner_name,
        )

        if not resolved.get("success"):
            resolved["lines"] = []
            return resolved

        config = DOCUMENT_CONFIGS[model_name]
        record_id = resolved["record_id"]
        document_records = self._read_records(
            model_name,
            [record_id],
            self._document_base_fields(model_name),
        )

        if not document_records:
            result = self._empty_document_result(
                model_name,
                query or str(document_id or ""),
                "Document disappeared before detail read.",
            )
            result["source"] = "real_odoo"
            result["lines"] = []
            return result

        document = document_records[0]
        line_ids = document.get(config["line_field"]) or []
        line_fields = self._existing_fields(config["line_model"], config["line_fields"])
        line_records = self._read_records(config["line_model"], line_ids, line_fields)
        product_ids = [self._m2o_id(line.get("product_id")) for line in line_records]
        product_map = self._product_variant_map(product_ids)
        lines = [
            self._format_document_line(model_name, line, product_map)
            for line in line_records
        ]

        header = self._format_document_candidate(model_name, document)
        metadata = {
            "document_name": header["name"],
            "document_id": record_id,
            "document_model": model_name,
            "document_type": DOCUMENT_MODEL_TO_TYPE.get(model_name),
            "partner_name": header["partner"],
            "source": "real_odoo",
        }

        return {
            "success": True,
            "found": True,
            "ambiguous": False,
            "source": "real_odoo",
            "model": model_name,
            "record_id": record_id,
            "document_name": header["name"],
            "document_id": record_id,
            "document_model": model_name,
            "document_type": DOCUMENT_MODEL_TO_TYPE.get(model_name),
            "partner_name": header["partner"],
            "metadata": metadata,
            "document": header,
            "name": header["name"],
            "partner": header["partner"],
            "state": header["state"],
            "date": header["date"],
            "lines": lines,
            "candidates": resolved.get("candidates", []),
            "message": "Document details read from Odoo.",
        }

    def get_sale_order_details(self, order_query: str = "", document_id: int | None = None) -> dict:
        return self._get_document_details("sale.order", order_query, document_id=document_id)

    def get_purchase_order_details(self, order_query: str = "", document_id: int | None = None) -> dict:
        return self._get_document_details("purchase.order", order_query, document_id=document_id)

    def get_invoice_details(self, invoice_query: str = "", document_id: int | None = None) -> dict:
        return self._get_document_details("account.move", invoice_query, document_id=document_id)

    def get_delivery_order_details(self, picking_query: str = "", document_id: int | None = None) -> dict:
        return self._get_document_details("stock.picking", picking_query, document_id=document_id)

    def get_document_details_by_id(self, document_id: int) -> dict:
        matches = []

        for model_name in ["purchase.order", "sale.order", "account.move", "stock.picking"]:
            details = self._get_document_details(
                model_name,
                "",
                document_id=document_id,
            )

            if details.get("success") and details.get("found"):
                matches.append(details)

        if len(matches) == 1:
            return matches[0]

        if len(matches) > 1:
            return {
                "success": False,
                "found": True,
                "ambiguous": True,
                "source": "real_odoo",
                "model": "odoo.document",
                "record_id": document_id,
                "candidates": [
                    {
                        "model": item.get("model"),
                        "record_id": item.get("record_id"),
                        "name": item.get("name"),
                        "partner": item.get("partner"),
                        "state": item.get("state"),
                        "date": item.get("date"),
                    }
                    for item in matches
                ],
                "lines": [],
                "message": "Document ID matched multiple Odoo document models.",
            }

        return {
            "success": False,
            "found": False,
            "ambiguous": False,
            "source": "real_odoo",
            "model": "odoo.document",
            "record_id": document_id,
            "candidates": [],
            "lines": [],
            "message": "No matching Odoo document found for this ID.",
        }

    def _blocked_document_message(self, model_name: str, state: str):
        if model_name == "account.move" and state == "posted":
            return "Facture comptabilisée — aucune modification exécutée."

        if model_name == "stock.picking" and state in {"done", "cancel"}:
            return "Bon de livraison terminé ou annulé — aucune modification exécutée."

        if state == "cancel":
            return "Document annulé — aucune modification exécutée."

        return None

    def _resolve_line_for_write(
        self,
        model_name: str,
        document_query: str,
        product_query: str,
        document_id: int | None = None,
        partner_name: str | None = None,
    ):
        details = self._get_document_details(
            model_name,
            document_query,
            document_id=document_id,
            partner_name=partner_name,
        )

        if not details.get("success"):
            return {
                "success": False,
                "document": details,
                "line": None,
                "candidates": details.get("candidates", []),
                "message": details.get("message", "Document was not resolved."),
            }

        normalized_query = _normalize_label(product_query)
        lines = details.get("lines", [])

        exact_matches = [
            line for line in lines
            if normalized_query in {
                _normalize_label(line.get("product_name", "")),
                _normalize_label(line.get("product", "")),
                _normalize_label(line.get("default_code", "")),
            }
        ]

        if len(exact_matches) == 1:
            return {
                "success": True,
                "document": details,
                "line": exact_matches[0],
                "candidates": exact_matches,
                "message": "Document line resolved.",
            }

        if len(exact_matches) > 1:
            return {
                "success": False,
                "document": details,
                "line": None,
                "candidates": exact_matches,
                "ambiguous": True,
                "message": "Ligne produit ambiguë — aucune modification exécutée.",
            }

        fallback_matches = [
            line for line in lines
            if normalized_query
            and (
                normalized_query in _normalize_label(line.get("product_name", ""))
                or normalized_query in _normalize_label(line.get("default_code", ""))
            )
        ]

        if len(fallback_matches) == 1:
            return {
                "success": True,
                "document": details,
                "line": fallback_matches[0],
                "candidates": fallback_matches,
                "message": "Document line resolved.",
            }

        return {
            "success": False,
            "document": details,
            "line": None,
            "candidates": fallback_matches,
            "ambiguous": len(fallback_matches) > 1,
            "message": (
                "Ligne produit ambiguë — aucune modification exécutée."
                if len(fallback_matches) > 1
                else "No matching document line found. No modification executed."
            ),
        }

    def _document_write_failure(
        self,
        model_name: str,
        document_query: str,
        field: str,
        requested_value,
        message: str,
        candidates=None,
        record_id=None,
        document=None,
        line_id=None,
    ):
        return {
            "success": False,
            "verified": False,
            "executed": False,
            "source": "real_odoo" if not self.mock_mode else "mock_odoo",
            "model": model_name,
            "record_id": record_id,
            "document": document or document_query,
            "line_id": line_id,
            "field": field,
            "old_value": None,
            "requested_value": requested_value,
            "new_value": None,
            "message": message,
            "candidates": candidates or [],
        }

    def _update_document_line(
        self,
        model_name: str,
        document_query: str,
        product_query: str,
        field: str,
        new_value,
        document_id: int | None = None,
        partner_name: str | None = None,
    ):
        if self.mock_mode:
            return self._document_write_failure(
                model_name,
                document_query,
                field,
                new_value,
                "Odoo credentials are missing. Real document update was not executed.",
            )

        config = DOCUMENT_CONFIGS.get(model_name)

        if not config or field not in config["allowed_line_fields"]:
            return self._document_write_failure(
                model_name,
                document_query,
                field,
                new_value,
                "Unsupported document line field. No modification executed.",
            )

        try:
            parsed_value = float(new_value)
        except (TypeError, ValueError):
            return self._document_write_failure(
                model_name,
                document_query,
                field,
                new_value,
                "Invalid requested value. No modification executed.",
            )

        try:
            line_resolution = self._resolve_line_for_write(
                model_name,
                document_query,
                product_query,
                document_id=document_id,
                partner_name=partner_name,
            )
            document = line_resolution.get("document") or {}

            if not line_resolution.get("success"):
                return self._document_write_failure(
                    model_name,
                    document_query,
                    field,
                    parsed_value,
                    line_resolution.get("message", "No modification executed."),
                    candidates=line_resolution.get("candidates", []),
                    record_id=document.get("record_id"),
                    document=document.get("name"),
                )

            blocked_message = self._blocked_document_message(
                model_name,
                document.get("state"),
            )

            if blocked_message:
                return self._document_write_failure(
                    model_name,
                    document_query,
                    field,
                    parsed_value,
                    blocked_message,
                    record_id=document.get("record_id"),
                    document=document.get("name"),
                )

            line = line_resolution["line"]
            line_id = line["line_id"]
            before = self._read_records(config["line_model"], [line_id], ["id", field])
            old_value = before[0].get(field) if before else None
            models = self._models()
            write_success = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                config["line_model"],
                "write",
                [[line_id], {field: parsed_value}],
            )
            after = self._read_records(config["line_model"], [line_id], ["id", field])
            actual_value = after[0].get(field) if after else None
            verified = (
                bool(write_success)
                and actual_value is not None
                and abs(float(actual_value) - parsed_value) < 0.00001
            )

            return {
                "success": verified,
                "verified": verified,
                "executed": verified,
                "source": "real_odoo",
                "model": model_name,
                "record_id": document.get("record_id"),
                "document": document.get("name"),
                "line_id": line_id,
                "field": field,
                "old_value": old_value,
                "requested_value": parsed_value,
                "new_value": actual_value,
                "product": line.get("product_name"),
                "message": (
                    "Document line updated and verified in Odoo."
                    if verified
                    else "Odoo write returned but document line read-back did not verify."
                ),
                "candidates": line_resolution.get("candidates", []),
            }

        except Exception as error:
            return self._document_write_failure(
                model_name,
                document_query,
                field,
                new_value,
                str(error),
            )

    def update_sale_order_line(
        self,
        order_query: str,
        product_query: str,
        field: str,
        new_value,
        document_id: int | None = None,
        partner_name: str | None = None,
    ) -> dict:
        return self._update_document_line(
            "sale.order",
            order_query,
            product_query,
            field,
            new_value,
            document_id=document_id,
            partner_name=partner_name,
        )

    def update_purchase_order_line(
        self,
        order_query: str,
        product_query: str,
        field: str,
        new_value,
        document_id: int | None = None,
        partner_name: str | None = None,
    ) -> dict:
        return self._update_document_line(
            "purchase.order",
            order_query,
            product_query,
            field,
            new_value,
            document_id=document_id,
            partner_name=partner_name,
        )

    def update_invoice_line(
        self,
        invoice_query: str,
        product_query: str,
        field: str,
        new_value,
        document_id: int | None = None,
        partner_name: str | None = None,
    ) -> dict:
        return self._update_document_line(
            "account.move",
            invoice_query,
            product_query,
            field,
            new_value,
            document_id=document_id,
            partner_name=partner_name,
        )

    def update_delivery_quantity(
        self,
        picking_query: str,
        product_query: str,
        new_quantity: float,
        document_id: int | None = None,
        partner_name: str | None = None,
    ) -> dict:
        return self._update_document_line(
            "stock.picking",
            picking_query,
            product_query,
            "product_uom_qty",
            new_quantity,
            document_id=document_id,
            partner_name=partner_name,
        )

    def _format_partner_candidate(self, partner: dict):
        return {
            "id": partner.get("id"),
            "name": partner.get("name") or "",
            "ref": partner.get("ref") or "",
            "email": partner.get("email") or "",
            "phone": partner.get("phone") or "",
            "active": bool(partner.get("active", True)),
        }

    def _search_partner_records(self, partner_query: str, exact: bool):
        operator = "=ilike" if exact else "ilike"
        fields = self._existing_fields("res.partner", ["id", "name", "ref", "email", "phone", "active"])
        search_fields = self._existing_fields("res.partner", ["name", "ref"])
        domain = self._or_domain([
            [field, operator, partner_query]
            for field in search_fields
        ]) or [["name", operator, partner_query]]
        models = self._models()

        return models.execute_kw(
            self.database,
            self.uid,
            self.auth_secret,
            "res.partner",
            "search_read",
            [domain],
            {
                "fields": fields,
                "limit": 20,
                "context": {"active_test": False},
            },
        )

    def _resolve_partner_for_write(self, partner_query: str):
        exact = self._search_partner_records(partner_query, exact=True)
        candidates = [self._format_partner_candidate(partner) for partner in exact]

        if len(candidates) == 1:
            return {"success": True, "partner": candidates[0], "candidates": candidates}

        if len(candidates) > 1:
            return {
                "success": False,
                "ambiguous": True,
                "partner": None,
                "candidates": candidates,
                "message": "Partenaire ambigu — aucune modification exécutée.",
            }

        fallback = self._search_partner_records(partner_query, exact=False)
        candidates = [self._format_partner_candidate(partner) for partner in fallback]

        if len(candidates) == 1:
            return {"success": True, "partner": candidates[0], "candidates": candidates}

        return {
            "success": False,
            "ambiguous": len(candidates) > 1,
            "partner": None,
            "candidates": candidates,
            "message": (
                "Partenaire ambigu — aucune modification exécutée."
                if len(candidates) > 1
                else "No matching partner found. No modification executed."
            ),
        }

    def update_document_partner(
        self,
        model_name: str,
        document_query: str,
        partner_query: str,
        document_id: int | None = None,
        current_partner_name: str | None = None,
    ) -> dict:
        if self.mock_mode:
            return self._document_write_failure(
                model_name,
                document_query,
                "partner_id",
                partner_query,
                "Odoo credentials are missing. Real document update was not executed.",
            )

        if model_name not in DOCUMENT_CONFIGS:
            return self._document_write_failure(
                model_name,
                document_query,
                "partner_id",
                partner_query,
                "Unsupported Odoo document model.",
            )

        try:
            document = self._resolve_document(
                model_name,
                document_query,
                document_id=document_id,
                partner_name=current_partner_name,
            )

            if not document.get("success"):
                return self._document_write_failure(
                    model_name,
                    document_query,
                    "partner_id",
                    partner_query,
                    document.get("message", "Document was not resolved."),
                    candidates=document.get("candidates", []),
                )

            blocked_message = self._blocked_document_message(
                model_name,
                document.get("state"),
            )

            if blocked_message:
                return self._document_write_failure(
                    model_name,
                    document_query,
                    "partner_id",
                    partner_query,
                    blocked_message,
                    record_id=document.get("record_id"),
                    document=document.get("name"),
                )

            partner = self._resolve_partner_for_write(partner_query)

            if not partner.get("success"):
                return self._document_write_failure(
                    model_name,
                    document_query,
                    "partner_id",
                    partner_query,
                    partner.get("message", "Partner was not resolved."),
                    candidates=partner.get("candidates", []),
                    record_id=document.get("record_id"),
                    document=document.get("name"),
                )

            partner_id = partner["partner"]["id"]
            before = self._read_records(model_name, [document["record_id"]], ["id", "partner_id"])
            old_partner = self._m2o_name(before[0].get("partner_id")) if before else None
            models = self._models()
            write_success = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                model_name,
                "write",
                [[document["record_id"]], {"partner_id": partner_id}],
            )
            after = self._read_records(model_name, [document["record_id"]], ["id", "partner_id"])
            actual_partner_id = self._m2o_id(after[0].get("partner_id")) if after else None
            actual_partner_name = self._m2o_name(after[0].get("partner_id")) if after else None
            verified = bool(write_success) and actual_partner_id == partner_id

            return {
                "success": verified,
                "verified": verified,
                "executed": verified,
                "source": "real_odoo",
                "model": model_name,
                "record_id": document.get("record_id"),
                "document": document.get("name"),
                "line_id": None,
                "field": "partner_id",
                "old_value": old_partner,
                "requested_value": partner_query,
                "new_value": actual_partner_name,
                "partner_id": actual_partner_id,
                "message": (
                    "Document partner updated and verified in Odoo."
                    if verified
                    else "Odoo write returned but document partner read-back did not verify."
                ),
                "candidates": partner.get("candidates", []),
            }

        except Exception as error:
            return self._document_write_failure(
                model_name,
                document_query,
                "partner_id",
                partner_query,
                str(error),
            )

    def update_document_date(
        self,
        model_name: str,
        document_query: str,
        date_field: str,
        new_date: str,
        document_id: int | None = None,
        partner_name: str | None = None,
    ) -> dict:
        if self.mock_mode:
            return self._document_write_failure(
                model_name,
                document_query,
                date_field,
                new_date,
                "Odoo credentials are missing. Real document update was not executed.",
            )

        if date_field not in DOCUMENT_DATE_FIELDS.get(model_name, set()):
            return self._document_write_failure(
                model_name,
                document_query,
                date_field,
                new_date,
                "Unsupported document date field. No modification executed.",
            )

        try:
            document = self._resolve_document(
                model_name,
                document_query,
                document_id=document_id,
                partner_name=partner_name,
            )

            if not document.get("success"):
                return self._document_write_failure(
                    model_name,
                    document_query,
                    date_field,
                    new_date,
                    document.get("message", "Document was not resolved."),
                    candidates=document.get("candidates", []),
                )

            if model_name == "purchase.order" and date_field == "date_planned":
                return self._update_purchase_order_expected_arrival_date(
                    document,
                    document_query,
                    new_date,
                )

            blocked_message = self._blocked_document_message(
                model_name,
                document.get("state"),
            )

            if blocked_message:
                return self._document_write_failure(
                    model_name,
                    document_query,
                    date_field,
                    new_date,
                    blocked_message,
                    record_id=document.get("record_id"),
                    document=document.get("name"),
                )

            before = self._read_records(model_name, [document["record_id"]], ["id", date_field])
            old_value = before[0].get(date_field) if before else None
            models = self._models()
            write_success = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                model_name,
                "write",
                [[document["record_id"]], {date_field: new_date}],
            )
            after = self._read_records(model_name, [document["record_id"]], ["id", date_field])
            actual_value = after[0].get(date_field) if after else None
            verified = bool(write_success) and str(actual_value or "").startswith(str(new_date))

            return {
                "success": verified,
                "verified": verified,
                "executed": verified,
                "source": "real_odoo",
                "model": model_name,
                "record_id": document.get("record_id"),
                "document": document.get("name"),
                "line_id": None,
                "field": date_field,
                "old_value": old_value,
                "requested_value": new_date,
                "new_value": actual_value,
                "message": (
                    "Document date updated and verified in Odoo."
                    if verified
                    else "Odoo write returned but document date read-back did not verify."
                ),
                "candidates": document.get("candidates", []),
            }

        except Exception as error:
            return self._document_write_failure(
                model_name,
                document_query,
                date_field,
                new_date,
                str(error),
            )

    def _update_purchase_order_expected_arrival_date(
        self,
        document: dict,
        document_query: str,
        new_date: str,
    ) -> dict:
        blocked_message = self._blocked_document_message(
            "purchase.order",
            document.get("state"),
        )

        if blocked_message:
            return self._document_write_failure(
                "purchase.order",
                document_query,
                "date_planned",
                new_date,
                blocked_message,
                record_id=document.get("record_id"),
                document=document.get("name"),
            )

        config = DOCUMENT_CONFIGS["purchase.order"]
        order_records = self._read_records(
            "purchase.order",
            [document["record_id"]],
            ["id", "name", "order_line"],
        )
        order = order_records[0] if order_records else {}
        line_ids = order.get("order_line") or []

        if not line_ids:
            return self._document_write_failure(
                "purchase.order",
                document_query,
                "date_planned",
                new_date,
                "Purchase order has no lines to update. No modification executed.",
                record_id=document.get("record_id"),
                document=document.get("name"),
            )

        before_lines = self._read_records(
            config["line_model"],
            line_ids,
            ["id", "date_planned"],
        )
        old_values = [
            {
                "line_id": line.get("id"),
                "date_planned": line.get("date_planned"),
            }
            for line in before_lines
        ]

        models = self._models()
        write_success = models.execute_kw(
            self.database,
            self.uid,
            self.auth_secret,
            config["line_model"],
            "write",
            [line_ids, {"date_planned": new_date}],
        )

        after_lines = self._read_records(
            config["line_model"],
            line_ids,
            ["id", "date_planned"],
        )
        new_values = [
            {
                "line_id": line.get("id"),
                "date_planned": line.get("date_planned"),
            }
            for line in after_lines
        ]
        verified = bool(write_success) and bool(after_lines) and all(
            str(line.get("date_planned") or "").startswith(str(new_date))
            for line in after_lines
        )

        return {
            "success": verified,
            "verified": verified,
            "executed": verified,
            "source": "real_odoo",
            "model": "purchase.order",
            "record_id": document.get("record_id"),
            "document": document.get("name"),
            "line_id": None,
            "line_ids": line_ids,
            "field": "date_planned",
            "old_value": old_values,
            "requested_value": new_date,
            "new_value": new_values,
            "message": (
                "Purchase order expected arrival date updated and verified in Odoo."
                if verified
                else "Odoo write returned but purchase order line date_planned read-back did not verify."
            ),
            "candidates": document.get("candidates", []),
        }

    def get_analytic_boolean_fields(self):
        if self.mock_mode:
            return {
                "success": False,
                "source": "mock_odoo",
                "model": "account.analytic.account",
                "fields": [],
                "message": "Odoo credentials are missing.",
            }

        try:
            models = self._models()
            raw_fields = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "account.analytic.account",
                "fields_get",
                [],
                {
                    "attributes": [
                        "string",
                        "type",
                        "readonly",
                    ],
                },
            )

            fields = []

            for name, metadata in raw_fields.items():
                if metadata.get("type") != "boolean":
                    continue

                fields.append({
                    "name": name,
                    "label": metadata.get("string") or name,
                    "type": "boolean",
                    "readonly": bool(metadata.get("readonly", False)),
                })

            return {
                "success": True,
                "source": "real_odoo",
                "model": "account.analytic.account",
                "fields": sorted(fields, key=lambda item: item["label"].lower()),
            }

        except Exception as error:
            return {
                "success": False,
                "source": "real_odoo_error",
                "model": "account.analytic.account",
                "fields": [],
                "message": str(error),
            }

    def resolve_analytic_boolean_field(self, field_label: str):
        result = self.get_analytic_boolean_fields()

        if not result.get("success"):
            return None

        normalized_label = _normalize_label(field_label)

        for field in result.get("fields", []):
            if _normalize_label(field.get("label", "")) == normalized_label:
                return field

        for field in result.get("fields", []):
            if _normalize_label(field.get("name", "")) == normalized_label:
                return field

        return None

    def _analytic_search_domain(self, record_query: str, exact: bool):
        operator = "=ilike" if exact else "ilike"
        return [
            "|",
            ["name", operator, record_query],
            ["code", operator, record_query],
        ]

    def _format_analytic_account_candidate(self, account: dict):
        record_id = account.get("id")
        display_name = account.get("display_name") or account.get("name") or str(record_id)

        return {
            "record_id": record_id,
            "id": record_id,
            "name": account.get("name") or display_name,
            "display_name": display_name,
            "code": account.get("code"),
            "label": (
                f"{account.get('code')} - {display_name}"
                if account.get("code")
                else display_name
            ),
        }

    def resolve_analytic_account(self, record_query: str, limit: int = 6):
        record_query = (record_query or "").strip()

        if self.mock_mode:
            return {
                "success": False,
                "source": "mock_odoo",
                "model": "account.analytic.account",
                "record_query": record_query,
                "record_id": None,
                "found": False,
                "ambiguous": False,
                "candidates": [],
                "message": "Odoo credentials are missing.",
            }

        if not record_query:
            return {
                "success": False,
                "source": "real_odoo",
                "model": "account.analytic.account",
                "record_query": record_query,
                "record_id": None,
                "found": False,
                "ambiguous": False,
                "candidates": [],
                "failure_reason": "missing_record_query",
                "message": "Analytic account reference or name is required.",
            }

        try:
            models = self._models()
            fields = self._existing_fields(
                "account.analytic.account",
                ["id", "name", "display_name", "code"],
            )
            search_fields = [
                field
                for field in ["code", "name", "display_name"]
                if field in fields
            ]

            if not search_fields:
                return {
                    "success": False,
                    "source": "real_odoo",
                    "model": "account.analytic.account",
                    "record_query": record_query,
                    "record_id": None,
                    "found": False,
                    "ambiguous": False,
                    "candidates": [],
                    "failure_reason": "missing_search_field",
                    "message": "No safe analytic account search field is available.",
                }

            for exact in [True, False]:
                operator = "=ilike" if exact else "ilike"
                domain = self._or_domain([
                    [field, operator, record_query]
                    for field in search_fields
                ])
                accounts = models.execute_kw(
                    self.database,
                    self.uid,
                    self.auth_secret,
                    "account.analytic.account",
                    "search_read",
                    [domain],
                    {
                        "fields": fields,
                        "limit": max(2, min(int(limit or 6), 10)),
                    },
                )

                if not accounts:
                    continue

                candidates = [
                    self._format_analytic_account_candidate(account)
                    for account in accounts
                ]

                if len(candidates) == 1:
                    candidate = candidates[0]
                    return {
                        "success": True,
                        "source": "real_odoo",
                        "model": "account.analytic.account",
                        "record_query": record_query,
                        "record_id": candidate.get("record_id"),
                        "record": candidate.get("display_name"),
                        "record_name": candidate.get("name"),
                        "record_code": candidate.get("code"),
                        "found": True,
                        "ambiguous": False,
                        "candidates": candidates,
                        "match_mode": "exact" if exact else "partial",
                    }

                return {
                    "success": False,
                    "source": "real_odoo",
                    "model": "account.analytic.account",
                    "record_query": record_query,
                    "record_id": None,
                    "found": True,
                    "ambiguous": True,
                    "candidates": candidates,
                    "match_mode": "exact" if exact else "partial",
                    "message": "Multiple analytic accounts match this reference or name.",
                }

            return {
                "success": False,
                "source": "real_odoo",
                "model": "account.analytic.account",
                "record_query": record_query,
                "record_id": None,
                "found": False,
                "ambiguous": False,
                "candidates": [],
                "message": "No analytic account found in Odoo.",
            }

        except Exception as error:
            return {
                "success": False,
                "source": "real_odoo_error",
                "model": "account.analytic.account",
                "record_query": record_query,
                "record_id": None,
                "found": False,
                "ambiguous": False,
                "candidates": [],
                "message": str(error),
            }

    def search_analytic_accounts(self, record_query: str, limit: int = 6):
        return self.generic_search_records(
            model_name="account.analytic.account",
            keyword=record_query,
            limit=limit,
        )

    def get_analytic_account_details(self, record_query: str = "", record_id=None):
        return self.generic_get_record_details(
            model_name="account.analytic.account",
            record_id=record_id,
            keyword=record_query,
        )

    def _search_analytic_account(self, record_query: str):
        models = self._models()

        for exact in [True, False]:
            try:
                accounts = models.execute_kw(
                    self.database,
                    self.uid,
                    self.auth_secret,
                    "account.analytic.account",
                    "search_read",
                    [self._analytic_search_domain(record_query, exact)],
                    {
                        "fields": ["id", "name", "code"],
                        "limit": 1,
                    },
                )
            except Exception:
                accounts = models.execute_kw(
                    self.database,
                    self.uid,
                    self.auth_secret,
                    "account.analytic.account",
                    "search_read",
                    [[["name", "=ilike" if exact else "ilike", record_query]]],
                    {
                        "fields": ["id", "name"],
                        "limit": 1,
                    },
                )

            if accounts:
                return accounts[0]

        return None

    def update_analytic_boolean_field(
        self,
        record_query: str,
        field_name: str,
        new_value: bool,
        record_id=None,
    ):
        if self.mock_mode:
            return {
                "success": False,
                "source": "mock_odoo",
                "model": "account.analytic.account",
                "action": "toggle_boolean_field",
                "record_query": record_query,
                "record": None,
                "record_id": None,
                "field_name": field_name,
                "requested_value": bool(new_value),
                "new_value": None,
                "executed": False,
                "verified": False,
                "found": False,
                "message": "Odoo credentials are missing. Real analytic account update was not executed.",
            }

        try:
            models = self._models()
            if record_id is not None:
                try:
                    resolved_id = int(record_id)
                except (TypeError, ValueError):
                    resolved_id = None

                account_records = (
                    models.execute_kw(
                        self.database,
                        self.uid,
                        self.auth_secret,
                        "account.analytic.account",
                        "read",
                        [[resolved_id]],
                        {
                            "fields": self._existing_fields(
                                "account.analytic.account",
                                ["id", "name", "display_name", "code"],
                            ),
                        },
                    )
                    if resolved_id is not None
                    else []
                )
                account = account_records[0] if account_records else None
            else:
                resolved = self.resolve_analytic_account(record_query)

                if resolved.get("ambiguous"):
                    return {
                        "success": False,
                        "source": resolved.get("source"),
                        "model": "account.analytic.account",
                        "action": "toggle_boolean_field",
                        "record_query": record_query,
                        "record": None,
                        "record_id": None,
                        "field_name": field_name,
                        "requested_value": bool(new_value),
                        "new_value": None,
                        "executed": False,
                        "verified": False,
                        "found": True,
                        "ambiguous": True,
                        "candidates": resolved.get("candidates", []),
                        "message": "Analytic account is ambiguous. Field was not changed.",
                    }

                account = (
                    {
                        "id": resolved.get("record_id"),
                        "name": resolved.get("record_name") or resolved.get("record"),
                        "display_name": resolved.get("record"),
                        "code": resolved.get("record_code"),
                    }
                    if resolved.get("found") and resolved.get("record_id") is not None
                    else None
                )

            if not account:
                return {
                    "success": False,
                    "source": "real_odoo",
                    "model": "account.analytic.account",
                    "action": "toggle_boolean_field",
                    "record_query": record_query,
                    "record": None,
                    "record_id": None,
                    "field_name": field_name,
                    "requested_value": bool(new_value),
                    "new_value": None,
                    "executed": False,
                    "verified": False,
                    "found": False,
                    "message": "No analytic account found in Odoo. Field was not changed.",
                }

            write_success = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "account.analytic.account",
                "write",
                [[account["id"]], {field_name: bool(new_value)}],
            )

            updated_accounts = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "account.analytic.account",
                "read",
                [[account["id"]]],
                {
                    "fields": ["id", "name", field_name],
                },
            )

            updated_account = updated_accounts[0] if updated_accounts else account
            actual_value = bool(updated_account.get(field_name))
            verified = bool(write_success) and actual_value is bool(new_value)

            return {
                "success": verified,
                "source": "real_odoo",
                "model": "account.analytic.account",
                "action": "toggle_boolean_field",
                "record_query": record_query,
                "record": updated_account.get("name") or account.get("name"),
                "record_id": account.get("id"),
                "field_name": field_name,
                "requested_value": bool(new_value),
                "new_value": actual_value,
                "executed": verified,
                "verified": verified,
                "found": True,
                "message": (
                    "Analytic account boolean field updated and verified in Odoo."
                    if verified
                    else "Odoo write returned but analytic boolean field did not verify against requested value."
                ),
            }

        except Exception as error:
            return {
                "success": False,
                "source": "real_odoo_error",
                "model": "account.analytic.account",
                "action": "toggle_boolean_field",
                "record_query": record_query,
                "record": None,
                "record_id": None,
                "field_name": field_name,
                "requested_value": bool(new_value),
                "new_value": None,
                "executed": False,
                "verified": False,
                "found": False,
                "message": str(error),
            }

    def search_customer(self, customer_name: str):
        if self.mock_mode:
            return {
                "source": "mock_odoo",
                "customer": customer_name,
                "found": True,
                "results": [
                    {
                        "id": "MOCK-CUST-001",
                        "name": customer_name,
                        "email": "mock@example.com",
                        "phone": "-",
                    }
                ],
            }

        try:
            models = self._models()

            customers = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "res.partner",
                "search_read",
                [[["name", "ilike", customer_name]]],
                {
                    "fields": ["id", "name", "email", "phone"],
                    "limit": 5,
                },
            )

            return {
                "source": "real_odoo",
                "customer": customer_name,
                "found": len(customers) > 0,
                "results": customers,
            }

        except Exception as error:
            return {
                "source": "real_odoo_error",
                "customer": customer_name,
                "found": False,
                "message": str(error),
            }

    def create_purchase_request(self, description: str):
        return {
            "source": "real_odoo_pending",
            "action": "create_purchase_request",
            "description": description,
            "message": "Creation actions should require approval before real execution.",
        }

    def create_purchase_order(self, description: str):
        return {
            "source": "real_odoo_pending",
            "action": "create_purchase_order",
            "description": description,
            "message": "Purchase order creation should require approval before real execution.",
        }
