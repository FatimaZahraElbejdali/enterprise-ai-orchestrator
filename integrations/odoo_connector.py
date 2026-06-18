import os
import unicodedata
import xmlrpc.client

from dotenv import load_dotenv

load_dotenv()


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().split())


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


class OdooConnector:
    def __init__(self):
        self.url = os.getenv("ODOO_URL")
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
        return [
            "|",
            ["name", "ilike", product_name],
            ["default_code", "ilike", product_name],
        ]

    def _product_fields(self):
        return [
            "id",
            "name",
            "default_code",
            "qty_available",
            "virtual_available",
            "uom_id",
            "list_price",
            "sale_ok",
            "active",
        ]

    def _format_product_candidate(self, product: dict):
        unit = product.get("uom_id")

        return {
            "id": product.get("id"),
            "name": product.get("name") or "",
            "default_code": product.get("default_code") or "",
            "list_price": product.get("list_price"),
            "qty_available": product.get("qty_available"),
            "virtual_available": product.get("virtual_available"),
            "sale_ok": bool(product.get("sale_ok")),
            "active": bool(product.get("active", True)),
            "uom_id": unit[1] if isinstance(unit, list) and len(unit) > 1 else unit or "",
        }

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
                "source": "mock_odoo",
                "product": product_name,
                "found": True,
                "results": [
                    {
                        "id": "MOCK-PROD-001",
                        "name": product_name,
                        "default_code": "MOCK-REF",
                        "qty_available": 42,
                        "virtual_available": 42,
                        "list_price": 1.0,
                        "uom_id": [1, "Unité(s)"],
                    }
                ],
                "message": "Mock product result.",
            }

        try:
            products = self._search_product_templates(
                self._product_search_domain(product_name),
                limit=5,
            )

            return {
                "source": "real_odoo",
                "product": product_name,
                "found": len(products) > 0,
                "results": [
                    self._format_product_candidate(product)
                    for product in products
                ],
            }

        except Exception as error:
            return {
                "source": "real_odoo_error",
                "product": product_name,
                "found": False,
                "message": str(error),
            }

    def check_stock(self, product_name: str):
        if self.mock_mode:
            return {
                "source": "mock_odoo",
                "product": product_name,
                "product_id": "MOCK-PROD-001",
                "internal_reference": "MOCK-REF",
                "stock_quantity": 42,
                "forecast_quantity": 42,
                "sale_price": 1.0,
                "unit": "Unité(s)",
                "warehouse": "Mock Warehouse",
                "found": True,
                "message": "Mock stock result.",
            }

        try:
            resolved = self.resolve_product_template_for_write(product_name)

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

            return {
                "source": "real_odoo",
                "product": product.get("name"),
                "product_id": product.get("id"),
                "internal_reference": product.get("default_code") or "-",
                "stock_quantity": product.get("qty_available"),
                "forecast_quantity": product.get("virtual_available"),
                "sale_price": product.get("list_price"),
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

        return {
            "success": True,
            "found": True,
            "ambiguous": False,
            "source": "real_odoo",
            "model": model_name,
            "record_id": record_id,
            "document": header,
            "name": header["name"],
            "partner": header["partner"],
            "state": header["state"],
            "date": header["date"],
            "lines": lines,
            "candidates": resolved.get("candidates", []),
            "message": "Document details read from Odoo.",
        }

    def get_sale_order_details(self, order_query: str) -> dict:
        return self._get_document_details("sale.order", order_query)

    def get_purchase_order_details(self, order_query: str) -> dict:
        return self._get_document_details("purchase.order", order_query)

    def get_invoice_details(self, invoice_query: str) -> dict:
        return self._get_document_details("account.move", invoice_query)

    def get_delivery_order_details(self, picking_query: str) -> dict:
        return self._get_document_details("stock.picking", picking_query)

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
            account = self._search_analytic_account(record_query)

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
