from integrations.odoo_connector import OdooConnector


def test_odoo_connector_normalizes_configured_base_url(monkeypatch):
    monkeypatch.setenv("ODOO_URL", "https://example.odoo.com/")
    monkeypatch.setenv("ODOO_DB", "test-db")
    monkeypatch.setenv("ODOO_USERNAME", "user@example.com")
    monkeypatch.setenv("ODOO_API_KEY", "secret")

    connector = OdooConnector()

    assert connector.url == "https://example.odoo.com"
    assert connector.mock_mode is False


def test_odoo_connector_mock_mode():
    connector = OdooConnector()

    result = connector.test_connection()

    assert "connected" in result
    assert "mode" in result


def test_odoo_check_stock_mock():
    connector = OdooConnector()

    result = connector.check_stock("Product X")

    assert "product" in result
    assert result["product"] == "Product X"


def test_odoo_create_purchase_request_mock():
    connector = OdooConnector()

    result = connector.create_purchase_request("10 laptops")

    assert result["action"] == "create_purchase_request"


def test_generic_read_rejects_non_allowlisted_model():
    connector = OdooConnector()
    connector.mock_mode = False

    result = connector.generic_search_records("res.users", "admin")

    assert result["success"] is False
    assert result["source"] == "real_odoo_error"
    assert result["model"] is None
    assert result["records"] == []


class FakeProductModels:
    def __init__(self, read_back_prices):
        self.read_back_prices = (
            list(read_back_prices)
            if isinstance(read_back_prices, list)
            else [read_back_prices]
        )
        self.write_values = None

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        if model != "product.template":
            raise AssertionError(f"Unexpected model: {model}")

        if method == "search_read":
            return [
                {
                    "id": 7,
                    "name": "BACOTOP",
                    "default_code": "BACOTOP",
                    "list_price": 1.0,
                    "qty_available": 0,
                    "virtual_available": 0,
                    "uom_id": [1, "Unité(s)"],
                    "sale_ok": True,
                    "active": True,
                }
            ]

        if method == "write":
            self.write_values = args[1]
            return True

        if method == "read":
            price = (
                self.read_back_prices.pop(0)
                if len(self.read_back_prices) > 1
                else self.read_back_prices[0]
            )
            return [
                {
                    "id": 7,
                    "name": "BACOTOP",
                    "default_code": "BACOTOP",
                    "list_price": price,
                    "qty_available": 0,
                    "virtual_available": 0,
                    "uom_id": [1, "Unité(s)"],
                    "sale_ok": True,
                    "active": True,
                }
            ]

        raise AssertionError(f"Unexpected method: {method}")


def real_connector_with_models(fake_models):
    connector = OdooConnector()
    connector.mock_mode = False
    connector.uid = 1
    connector.database = "test-db"
    connector.auth_secret = "test-secret"
    connector._models = lambda: fake_models
    return connector


class AnalyticAccountModels:
    def __init__(self, search_results=None, read_result=None):
        self.search_results = search_results if search_results is not None else []
        self.read_result = read_result
        self.calls = []
        self.write_values = None

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        self.calls.append((model, method, args, kwargs or {}))

        if model != "account.analytic.account":
            raise AssertionError(f"Unexpected model: {model}")

        if method == "fields_get":
            return {
                "id": {"type": "integer"},
                "name": {"type": "char"},
                "display_name": {"type": "char"},
                "code": {"type": "char"},
                "x_studio_pointage": {"type": "boolean"},
            }

        if method == "search_read":
            return list(self.search_results)

        if method == "read":
            if self.read_result is not None:
                return [self.read_result]

            return [
                {
                    "id": args[0][0],
                    "name": "11SOCM0001 Services",
                    "display_name": "11SOCM0001 Services",
                    "code": "11SOCM0001",
                    "x_studio_pointage": True,
                }
            ]

        if method == "write":
            self.write_values = args[1]
            return True

        raise AssertionError(f"Unexpected method: {method}")


def test_resolve_analytic_account_by_business_reference():
    fake_models = AnalyticAccountModels(
        search_results=[
            {
                "id": 5935,
                "name": "11SOCM0001 Services",
                "display_name": "11SOCM0001 Services",
                "code": "11SOCM0001",
            }
        ],
    )
    connector = real_connector_with_models(fake_models)

    result = connector.resolve_analytic_account("11SOCM0001")

    assert result["success"] is True
    assert result["found"] is True
    assert result["ambiguous"] is False
    assert result["record_id"] == 5935
    assert result["record_code"] == "11SOCM0001"
    search_call = next(call for call in fake_models.calls if call[1] == "search_read")
    assert ["code", "=ilike", "11SOCM0001"] in search_call[2][0]


def test_resolve_analytic_account_returns_ambiguous_candidates():
    fake_models = AnalyticAccountModels(
        search_results=[
            {"id": 5935, "name": "11SOCM0001 A", "code": "11SOCM0001"},
            {"id": 5936, "name": "11SOCM0001 B", "code": "11SOCM0001"},
        ],
    )
    connector = real_connector_with_models(fake_models)

    result = connector.resolve_analytic_account("11SOCM0001")

    assert result["success"] is False
    assert result["found"] is True
    assert result["ambiguous"] is True
    assert [candidate["record_id"] for candidate in result["candidates"]] == [5935, 5936]


def test_update_analytic_boolean_field_uses_resolved_record_id_without_search():
    fake_models = AnalyticAccountModels(
        read_result={
            "id": 5935,
            "name": "11SOCM0001 Services",
            "display_name": "11SOCM0001 Services",
            "code": "11SOCM0001",
            "x_studio_pointage": True,
        },
    )
    connector = real_connector_with_models(fake_models)

    result = connector.update_analytic_boolean_field(
        record_query="11SOCM0001",
        record_id=5935,
        field_name="x_studio_pointage",
        new_value=True,
    )

    assert result["success"] is True
    assert result["verified"] is True
    assert result["record_id"] == 5935
    assert fake_models.write_values == {"x_studio_pointage": True}
    assert not any(call[1] == "search_read" for call in fake_models.calls)


class StockReadModels:
    def __init__(self):
        self.calls = []

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        self.calls.append((model, method, args, kwargs or {}))

        if method == "fields_get":
            return {
                "id": {"type": "integer"},
                "name": {"type": "char"},
                "default_code": {"type": "char"},
                "barcode": {"type": "char"},
                "product_tmpl_id": {"type": "many2one"},
                "qty_available": {"type": "float"},
                "virtual_available": {"type": "float"},
                "uom_id": {"type": "many2one"},
                "list_price": {"type": "float"},
                "sale_ok": {"type": "boolean"},
                "active": {"type": "boolean"},
            }

        if method == "search_read" and model == "product.product":
            return [
                {
                    "id": 3471,
                    "name": "BACO CLEAN",
                    "default_code": "PDSBACCLN0001",
                    "barcode": "",
                    "product_tmpl_id": [120, "BACO CLEAN"],
                    "qty_available": 14,
                    "virtual_available": 18,
                    "uom_id": [1, "Unité(s)"],
                    "list_price": 25.0,
                    "sale_ok": True,
                    "active": True,
                }
            ]

        if method == "search_read" and model == "product.template":
            return []

        raise AssertionError(f"Unexpected call: {model}.{method}")


def test_check_stock_uses_inventory_product_read_search_for_internal_reference():
    fake_models = StockReadModels()
    connector = real_connector_with_models(fake_models)

    result = connector.check_stock("PDSBACCLN0001")

    assert result["found"] is True
    assert result["product_id"] == 3471
    assert result["product_name"] == "BACO CLEAN"
    assert result["internal_reference"] == "PDSBACCLN0001"
    assert result["stock_quantity"] == 14
    assert any(
        model == "product.product" and method == "search_read"
        for model, method, _args, _kwargs in fake_models.calls
    )


def test_update_product_price_verifies_read_back_success():
    fake_models = FakeProductModels(read_back_prices=[1.0, 3.0])
    connector = real_connector_with_models(fake_models)

    result = connector.update_product_price("BACOTOP", 3.0)

    assert fake_models.write_values == {"list_price": 3.0}
    assert result["model"] == "product.template"
    assert result["old_price"] == 1.0
    assert result["requested_price"] == 3.0
    assert result["new_price"] == 3.0
    assert result["success"] is True
    assert result["executed"] is True
    assert result["verified"] is True


def test_update_product_price_fails_when_read_back_differs():
    fake_models = FakeProductModels(read_back_prices=[1.0, 1.0])
    connector = real_connector_with_models(fake_models)

    result = connector.update_product_price("BACOTOP", 3.0)

    assert fake_models.write_values == {"list_price": 3.0}
    assert result["requested_price"] == 3.0
    assert result["new_price"] == 1.0
    assert result["success"] is False
    assert result["executed"] is False
    assert result["verified"] is False


class AmbiguousProductModels:
    def __init__(self):
        self.write_called = False

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        if model != "product.template":
            raise AssertionError(f"Unexpected model: {model}")

        if method == "write":
            self.write_called = True
            raise AssertionError("Ambiguous product write should not execute")

        if method != "search_read":
            return []

        domain = args[0]

        if domain and domain[0] == "|":
            return [
                {
                    "id": 11,
                    "name": "BACODOR",
                    "default_code": "BACODOR-A",
                    "list_price": 1.0,
                    "qty_available": 44,
                    "virtual_available": 5284,
                    "uom_id": [1, "Unité(s)"],
                    "sale_ok": True,
                    "active": True,
                },
                {
                    "id": 12,
                    "name": "BACODOR variant",
                    "default_code": "BACODOR-B",
                    "list_price": 0.0,
                    "qty_available": 0,
                    "virtual_available": 0,
                    "uom_id": [1, "Unité(s)"],
                    "sale_ok": False,
                    "active": True,
                },
            ]

        return []


def test_update_product_price_refuses_ambiguous_fallback_candidates():
    fake_models = AmbiguousProductModels()
    connector = real_connector_with_models(fake_models)

    result = connector.update_product_price("BACODOR", 7.0)

    assert fake_models.write_called is False
    assert result["success"] is False
    assert result["executed"] is False
    assert result["verified"] is False
    assert result["ambiguous"] is True
    assert result["message"] == "Produit ambigu — aucune modification exécutée."
    assert len(result["candidates"]) == 2
    assert result["candidates"][0]["id"] == 11


class InventoryProductSearchModels:
    def __init__(self):
        self.search_calls = []

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        if model not in {"product.product", "product.template"}:
            raise AssertionError(f"Unexpected model: {model}")

        if method == "fields_get":
            return {
                "id": {},
                "name": {},
                "default_code": {},
                "barcode": {},
                "qty_available": {},
                "virtual_available": {},
                "uom_id": {},
                "list_price": {},
                "sale_ok": {},
                "active": {},
                "product_tmpl_id": {},
            }

        if method == "search_read":
            domain = args[0]
            self.search_calls.append((model, domain, kwargs or {}))

            if model == "product.product":
                return [
                    {
                        "id": 21,
                        "name": "NETTOYAGE SOL",
                        "default_code": "NET-SOL",
                        "barcode": "123456789",
                        "product_tmpl_id": [8, "Famille nettoyage"],
                        "list_price": 12.0,
                        "qty_available": 18,
                        "virtual_available": 20,
                        "uom_id": [1, "Unité(s)"],
                        "sale_ok": True,
                        "active": True,
                    }
                ]

            return []

        raise AssertionError(f"Unexpected method: {method}")


def test_inventory_product_search_uses_allowlisted_models_and_safe_fields():
    fake_models = InventoryProductSearchModels()
    connector = real_connector_with_models(fake_models)

    result = connector.search_product("nettoyage")

    assert result["success"] is True
    assert result["found"] is True
    assert result["model"] == "product.product"
    assert result["results"][0]["name"] == "NETTOYAGE SOL"
    assert result["results"][0]["default_code"] == "NET-SOL"
    assert result["results"][0]["barcode"] == "123456789"
    assert result["results"][0]["template_name"] == "Famille nettoyage"
    assert {call[0] for call in fake_models.search_calls} <= {
        "product.product",
        "product.template",
    }
    assert any("barcode" in str(call[1]) for call in fake_models.search_calls)


class GenericPartnerModels:
    def __init__(self, records=None):
        self.records = records if records is not None else [
            {
                "id": 31,
                "name": "Atlas",
                "display_name": "Atlas",
                "phone": "0612345678",
                "email": "atlas@example.com",
                "customer_rank": 1,
                "supplier_rank": 0,
                "is_company": True,
            }
        ]
        self.write_values = None

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        if model != "res.partner":
            raise AssertionError(f"Unexpected model: {model}")

        if method == "fields_get":
            return {
                "id": {},
                "name": {},
                "display_name": {},
                "phone": {},
                "mobile": {},
                "email": {},
                "customer_rank": {},
                "supplier_rank": {},
                "is_company": {},
            }

        if method == "search_read":
            return self.records

        if method == "read":
            fields = (kwargs or {}).get("fields", [])
            record = dict(self.records[0])
            return [{field: record.get(field) for field in fields}]

        if method == "write":
            self.write_values = args[1]
            self.records[0].update(self.write_values)
            return True

        raise AssertionError(f"Unexpected method: {method}")


def test_generic_partner_search_returns_clean_business_fields():
    connector = real_connector_with_models(GenericPartnerModels())

    result = connector.generic_search_records("res.partner", "Atlas")

    assert result["success"] is True
    assert result["found"] is True
    assert result["records"][0]["name"] == "Atlas"
    assert result["records"][0]["type"] == "client"
    assert result["records"][0]["phone"] == "0612345678"
    assert result["records"][0]["email"] == "atlas@example.com"


def test_generic_update_field_verifies_read_back():
    fake_models = GenericPartnerModels()
    connector = real_connector_with_models(fake_models)

    result = connector.update_generic_field("res.partner", 31, "phone", "0600000000")

    assert fake_models.write_values == {"phone": "0600000000"}
    assert result["success"] is True
    assert result["executed"] is True
    assert result["verified"] is True
    assert result["old_value"] == "0612345678"
    assert result["new_value"] == "0600000000"


def test_generic_update_rejects_non_allowlisted_field():
    connector = real_connector_with_models(GenericPartnerModels())

    result = connector.prepare_generic_update_field(
        "res.partner",
        "comment",
        "secret note",
        keyword="Atlas",
    )

    assert result["success"] is False
    assert result["source"] == "policy"
    assert result["message"] == "Unsupported Odoo write field."


class FakeDocumentModels:
    def __init__(self, ambiguous=False, after_price=7.0):
        self.ambiguous = ambiguous
        self.after_price = after_price
        self.write_values = None

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        if method == "fields_get":
            return {
                "sale.order": {
                    "id": {},
                    "name": {},
                    "client_order_ref": {},
                    "origin": {},
                    "partner_id": {},
                    "state": {},
                    "date_order": {},
                    "order_line": {},
                },
                "sale.order.line": {
                    "id": {},
                    "product_id": {},
                    "name": {},
                    "product_uom_qty": {},
                    "price_unit": {},
                },
                "product.product": {
                    "id": {},
                    "name": {},
                    "default_code": {},
                },
            }[model]

        if model == "sale.order" and method == "search_read":
            if self.ambiguous:
                return [
                    {
                        "id": 100,
                        "name": "S00045",
                        "partner_id": [1, "Client A"],
                        "state": "draft",
                        "date_order": "2026-06-18",
                        "order_line": [10],
                    },
                    {
                        "id": 101,
                        "name": "S00045",
                        "partner_id": [2, "Client B"],
                        "state": "draft",
                        "date_order": "2026-06-18",
                        "order_line": [11],
                    },
                ]

            return [
                {
                    "id": 100,
                    "name": "S00045",
                    "partner_id": [1, "Client A"],
                    "state": "draft",
                    "date_order": "2026-06-18",
                    "order_line": [10],
                }
            ]

        if model == "sale.order" and method == "read":
            return [
                {
                    "id": 100,
                    "name": "S00045",
                    "partner_id": [1, "Client A"],
                    "state": "draft",
                    "date_order": "2026-06-18",
                    "order_line": [10],
                }
            ]

        if model == "sale.order.line" and method == "read":
            price = self.after_price if self.write_values else 3.0

            return [
                {
                    "id": 10,
                    "product_id": [200, "BACO CLEAN"],
                    "name": "BACO CLEAN",
                    "product_uom_qty": 2.0,
                    "price_unit": price,
                }
            ]

        if model == "sale.order.line" and method == "write":
            self.write_values = args[1]
            return True

        if model == "product.product" and method == "read":
            return [
                {
                    "id": 200,
                    "name": "BACO CLEAN",
                    "default_code": "BACO-CLEAN",
                }
            ]

        raise AssertionError(f"Unexpected XML-RPC call: {model}.{method}")


def test_update_sale_order_line_verifies_read_back_success():
    fake_models = FakeDocumentModels(after_price=7.0)
    connector = real_connector_with_models(fake_models)

    result = connector.update_sale_order_line(
        order_query="S00045",
        product_query="BACO CLEAN",
        field="price_unit",
        new_value=7.0,
    )

    assert fake_models.write_values == {"price_unit": 7.0}
    assert result["success"] is True
    assert result["verified"] is True
    assert result["executed"] is True
    assert result["model"] == "sale.order"
    assert result["document"] == "S00045"
    assert result["line_id"] == 10
    assert result["old_value"] == 3.0
    assert result["new_value"] == 7.0


def test_update_sale_order_line_refuses_ambiguous_document():
    fake_models = FakeDocumentModels(ambiguous=True)
    connector = real_connector_with_models(fake_models)

    result = connector.update_sale_order_line(
        order_query="S00045",
        product_query="BACO CLEAN",
        field="price_unit",
        new_value=7.0,
    )

    assert fake_models.write_values is None
    assert result["success"] is False
    assert result["executed"] is False
    assert result["verified"] is False
    assert len(result["candidates"]) == 2
    assert result["message"] == "Document ambigu — aucune modification exécutée."


class PartnerDocumentSearchModels:
    def __init__(self):
        self.document_domains = []

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        if method == "fields_get":
            return {
                "sale.order": {
                    "id": {},
                    "name": {},
                    "client_order_ref": {},
                    "origin": {},
                    "partner_id": {},
                    "state": {},
                    "date_order": {},
                    "order_line": {},
                },
            }.get(model, {})

        if model == "res.partner" and method == "search":
            return [55]

        if model == "sale.order" and method == "search_read":
            domain = args[0]
            self.document_domains.append(domain)

            if ["partner_id", "in", [55]] in domain:
                return [
                    {
                        "id": 300,
                        "name": "S00100",
                        "partner_id": [55, "Client Partner"],
                        "state": "sale",
                        "date_order": "2026-06-18",
                        "order_line": [],
                    }
                ]

            return []

        raise AssertionError(f"Unexpected XML-RPC call: {model}.{method}")


def test_search_sale_order_can_match_partner_name():
    fake_models = PartnerDocumentSearchModels()
    connector = real_connector_with_models(fake_models)

    result = connector.search_sale_order("Client Partner")

    assert result["success"] is True
    assert result["found"] is True
    assert result["record_id"] == 300
    assert result["partner"] == "Client Partner"
    assert any(
        ["partner_id", "in", [55]] in domain
        for domain in fake_models.document_domains
    )


class PurchaseExpectedArrivalModels:
    def __init__(self, after_date="2026-06-15"):
        self.after_date = after_date
        self.write_values = None
        self.search_domains = []

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        if method == "fields_get":
            return {
                "purchase.order": {
                    "id": {},
                    "name": {},
                    "partner_ref": {},
                    "origin": {},
                    "partner_id": {},
                    "state": {},
                    "date_order": {},
                    "order_line": {},
                },
                "purchase.order.line": {
                    "id": {},
                    "product_id": {},
                    "name": {},
                    "product_qty": {},
                    "price_unit": {},
                    "date_planned": {},
                },
            }.get(model, {})

        if model == "res.partner" and method == "search":
            return []

        if model == "purchase.order" and method == "search_read":
            domain = args[0]
            self.search_domains.append(domain)

            if domain == [["name", "=", "BC-BPP2600313"]]:
                return [
                    {
                        "id": 700,
                        "name": "BC-BPP2600313",
                        "partner_id": [50, "Supplier A"],
                        "state": "purchase",
                        "date_order": "2026-06-01",
                        "order_line": [701, 702],
                    }
                ]

            raise AssertionError("Exact name search should resolve before fallback")

        if model == "purchase.order" and method == "read":
            return [
                {
                    "id": 700,
                    "name": "BC-BPP2600313",
                    "partner_id": [50, "Supplier A"],
                    "state": "purchase",
                    "date_order": "2026-06-01",
                    "order_line": [701, 702],
                }
            ]

        if model == "purchase.order.line" and method == "read":
            read_date = self.after_date if self.write_values else "2026-06-10"

            return [
                {"id": 701, "date_planned": read_date},
                {"id": 702, "date_planned": read_date},
            ]

        if model == "purchase.order.line" and method == "write":
            self.write_values = args[1]
            return True

        raise AssertionError(f"Unexpected XML-RPC call: {model}.{method}")


def test_exact_purchase_order_reference_is_not_ambiguous():
    fake_models = PurchaseExpectedArrivalModels()
    connector = real_connector_with_models(fake_models)

    result = connector.search_purchase_order("BC-BPP2600313")

    assert result["success"] is True
    assert result["ambiguous"] is False
    assert result["record_id"] == 700
    assert fake_models.search_domains == [[["name", "=", "BC-BPP2600313"]]]


def test_update_purchase_expected_arrival_date_verifies_line_date_planned():
    fake_models = PurchaseExpectedArrivalModels()
    connector = real_connector_with_models(fake_models)

    result = connector.update_document_date(
        model_name="purchase.order",
        document_query="BC-BPP2600313",
        date_field="date_planned",
        new_date="2026-06-15",
    )

    assert fake_models.write_values == {"date_planned": "2026-06-15"}
    assert result["success"] is True
    assert result["executed"] is True
    assert result["verified"] is True
    assert result["field"] == "date_planned"
    assert result["document"] == "BC-BPP2600313"
    assert result["line_ids"] == [701, 702]
    assert result["new_value"] == [
        {"line_id": 701, "date_planned": "2026-06-15"},
        {"line_id": 702, "date_planned": "2026-06-15"},
    ]


class DuplicatePurchaseReferenceModels:
    def __init__(self):
        self.write_values = None
        self.domains = []

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        if method == "fields_get":
            return {
                "purchase.order": {
                    "id": {},
                    "name": {},
                    "partner_ref": {},
                    "origin": {},
                    "partner_id": {},
                    "state": {},
                    "date_order": {},
                    "order_line": {},
                },
                "purchase.order.line": {
                    "id": {},
                    "date_planned": {},
                },
            }.get(model, {})

        if model == "res.partner" and method == "search":
            domain = args[0]
            if domain == [["name", "=ilike", "P.A.N"]]:
                return [91]
            return []

        if model == "purchase.order" and method == "search_read":
            domain = args[0]
            self.domains.append(domain)

            if domain == [["name", "=", "BC-BPP2600313"]]:
                return [
                    {
                        "id": 793,
                        "name": "BC-BPP2600313",
                        "partner_id": [91, "P.A.N"],
                        "state": "purchase",
                        "date_order": "2026-06-01",
                        "order_line": [801],
                    },
                    {
                        "id": 794,
                        "name": "BC-BPP2600313",
                        "partner_id": [92, "Other Supplier"],
                        "state": "purchase",
                        "date_order": "2026-06-02",
                        "order_line": [802],
                    },
                ]

            if domain == [
                ["name", "=", "BC-BPP2600313"],
                ["partner_id", "in", [91]],
            ]:
                return [
                    {
                        "id": 793,
                        "name": "BC-BPP2600313",
                        "partner_id": [91, "P.A.N"],
                        "state": "purchase",
                        "date_order": "2026-06-01",
                        "order_line": [801],
                    },
                ]

            return []

        if model == "purchase.order" and method == "read":
            ids = args[0]
            if ids == [793]:
                return [
                    {
                        "id": 793,
                        "name": "BC-BPP2600313",
                        "partner_id": [91, "P.A.N"],
                        "state": "purchase",
                        "date_order": "2026-06-01",
                        "order_line": [801],
                    },
                ]
            return []

        if model == "purchase.order.line" and method == "read":
            read_date = "2026-06-15" if self.write_values else "2026-06-10"
            return [{"id": 801, "date_planned": read_date}]

        if model == "purchase.order.line" and method == "write":
            self.write_values = args[1]
            return True

        raise AssertionError(f"Unexpected XML-RPC call: {model}.{method}")


def test_duplicate_purchase_reference_is_ambiguous_without_supplier_or_id():
    fake_models = DuplicatePurchaseReferenceModels()
    connector = real_connector_with_models(fake_models)

    result = connector.search_purchase_order("BC-BPP2600313")

    assert result["success"] is False
    assert result["ambiguous"] is True
    assert len(result["candidates"]) == 2


def test_duplicate_purchase_reference_with_supplier_resolves_one_document():
    fake_models = DuplicatePurchaseReferenceModels()
    connector = real_connector_with_models(fake_models)

    result = connector.update_document_date(
        model_name="purchase.order",
        document_query="BC-BPP2600313",
        date_field="date_planned",
        new_date="2026-06-15",
        partner_name="P.A.N",
    )

    assert result["success"] is True
    assert result["executed"] is True
    assert result["verified"] is True
    assert result["record_id"] == 793
    assert fake_models.write_values == {"date_planned": "2026-06-15"}


def test_purchase_document_id_resolves_one_document():
    fake_models = DuplicatePurchaseReferenceModels()
    connector = real_connector_with_models(fake_models)

    result = connector.update_document_date(
        model_name="purchase.order",
        document_query="",
        document_id=793,
        date_field="date_planned",
        new_date="2026-06-15",
    )

    assert result["success"] is True
    assert result["record_id"] == 793
    assert result["document"] == "BC-BPP2600313"


def test_read_document_details_by_id_resolves_purchase_order():
    fake_models = DuplicatePurchaseReferenceModels()
    connector = real_connector_with_models(fake_models)

    result = connector.get_document_details_by_id(793)

    assert result["success"] is True
    assert result["found"] is True
    assert result["model"] == "purchase.order"
    assert result["record_id"] == 793
    assert result["name"] == "BC-BPP2600313"


class BankAccountingModels:
    def __init__(self, records=None, missing_models=None):
        self.records = records or {}
        self.missing_models = set(missing_models or [])
        self.search_calls = []

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        if model in self.missing_models:
            raise Exception(f"Model not found: {model}")

        if method == "fields_get":
            return {
                "id": {"type": "integer", "string": "ID"},
                "name": {"type": "char", "string": "Name"},
                "display_name": {"type": "char", "string": "Display Name"},
                "date": {"type": "date", "string": "Date"},
                "journal_id": {"type": "many2one", "string": "Journal"},
                "partner_id": {"type": "many2one", "string": "Partner"},
                "amount": {"type": "monetary", "string": "Amount"},
                "balance": {"type": "monetary", "string": "Balance"},
                "ref": {"type": "char", "string": "Reference"},
                "payment_ref": {"type": "char", "string": "Payment Reference"},
                "move_id": {"type": "many2one", "string": "Move"},
                "statement_id": {"type": "many2one", "string": "Statement"},
                "api_key": {"type": "char", "string": "API Key"},
                "password": {"type": "char", "string": "Password"},
            }

        if method == "search_read":
            self.search_calls.append((model, args[0], kwargs or {}))
            return list(self.records.get(model, []))

        raise AssertionError(f"Unexpected XML-RPC call: {model}.{method}")


def test_bank_statement_model_unavailable_gives_clear_policy_or_model_response():
    fake_models = BankAccountingModels(
        missing_models=[
            "account.bank.statement",
            "account.bank.statement.line",
            "account.move",
            "account.move.line",
            "account.journal",
        ]
    )
    connector = real_connector_with_models(fake_models)

    result = connector.search_bank_accounting_records(
        "BMCE",
        message="relevé bancaire de BMCE sur le mois juin 2026",
    )

    assert result["status"] == "unsupported"
    assert result["failure_reason"] == "missing_model"
    assert result["candidate_models"]
    assert "dans cette base" in result["message"]


def test_bank_statement_model_exists_but_no_records_is_no_records():
    fake_models = BankAccountingModels()
    connector = real_connector_with_models(fake_models)

    result = connector.search_bank_accounting_records(
        "BMCE",
        message="relevé bancaire de BMCE sur le mois juin 2026",
    )

    assert result["status"] == "not_found"
    assert result["failure_reason"] == "no_records"
    assert result["record_count"] == 0
    assert result["candidate_models"]
    assert result["domain_used"]
    assert result["message"] == (
        "Aucun relevé ou transaction bancaire correspondant à BMCE "
        "en juin 2026 n’a été trouvé."
    )
    assert any(["date", ">=", "2026-06-01"] in call[1] for call in fake_models.search_calls)


def test_bank_statement_model_exists_with_records_returns_safe_summary_data():
    fake_models = BankAccountingModels(
        records={
            "account.bank.statement.line": [
                {
                    "id": 501,
                    "name": "BMCE Juin 2026",
                    "display_name": "BMCE Juin 2026",
                    "date": "2026-06-12",
                    "journal_id": [7, "BMCE"],
                    "partner_id": [22, "Client A"],
                    "amount": 1500.0,
                    "balance": 3200.0,
                    "ref": "REF-1",
                    "payment_ref": "PAY-1",
                    "move_id": [88, "MISC/2026/88"],
                    "statement_id": [4, "ST/2026/06"],
                    "api_key": "secret",
                    "password": "secret",
                }
            ]
        }
    )
    connector = real_connector_with_models(fake_models)

    result = connector.search_bank_accounting_records(
        "BMCE",
        message="relevé bancaire de BMCE sur le mois juin 2026",
    )

    assert result["status"] == "completed"
    assert result["selected_model"] == "account.bank.statement.line"
    assert "account.bank.statement.line" in result["candidate_models"]
    assert result["count_returned"] == 1
    assert result["records"][0]["journal"] == "BMCE"
    assert result["records"][0]["amount"] == 1500.0
    assert "api_key" not in result["records"][0]
    assert "password" not in result["records"][0]
    assert "api_key" not in result["fields_used"]
    assert "password" not in result["fields_used"]


class PurchaseSupplierRankingModels:
    def __init__(self, read_group_result=None, search_read_result=None, read_group_error=None):
        self.read_group_result = read_group_result
        self.search_read_result = search_read_result or []
        self.read_group_error = read_group_error
        self.calls = []

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        self.calls.append((model, method, args, kwargs or {}))

        if model != "purchase.order":
            raise AssertionError(f"Unexpected model: {model}")

        if method == "fields_get":
            return {
                "id": {"type": "integer", "string": "ID"},
                "partner_id": {"type": "many2one", "string": "Supplier"},
                "amount_total": {"type": "monetary", "string": "Total"},
                "secret_note": {"type": "char", "string": "Secret"},
            }

        if method == "read_group":
            if self.read_group_error:
                raise self.read_group_error
            return self.read_group_result or []

        if method == "search_read":
            return self.search_read_result

        raise AssertionError(f"Unexpected XML-RPC call: {model}.{method}")


class SaleCustomerRankingModels:
    def __init__(self, read_group_result=None, search_read_result=None, read_group_error=None):
        self.read_group_result = read_group_result
        self.search_read_result = search_read_result or []
        self.read_group_error = read_group_error
        self.calls = []

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        self.calls.append((model, method, args, kwargs or {}))

        if model != "sale.order":
            raise AssertionError(f"Unexpected model: {model}")

        if method == "fields_get":
            return {
                "id": {"type": "integer", "string": "ID"},
                "partner_id": {"type": "many2one", "string": "Customer"},
                "amount_total": {"type": "monetary", "string": "Total"},
                "secret_note": {"type": "char", "string": "Secret"},
            }

        if method == "read_group":
            if self.read_group_error:
                raise self.read_group_error
            return self.read_group_result or []

        if method == "search_read":
            return self.search_read_result

        raise AssertionError(f"Unexpected XML-RPC call: {model}.{method}")


class ProductSearchModels:
    def __init__(self):
        self.calls = []

    def execute_kw(self, database, uid, auth_secret, model, method, args, kwargs=None):
        self.calls.append((model, method, args, kwargs or {}))

        if method == "fields_get":
            return {
                "id": {"type": "integer"},
                "name": {"type": "char"},
                "default_code": {"type": "char"},
                "barcode": {"type": "char"},
                "product_tmpl_id": {"type": "many2one"},
                "qty_available": {"type": "float"},
                "virtual_available": {"type": "float"},
                "uom_id": {"type": "many2one"},
                "list_price": {"type": "float"},
                "sale_ok": {"type": "boolean"},
                "active": {"type": "boolean"},
            }

        if method == "search_read" and model == "product.product":
            return [
                {
                    "id": 1,
                    "name": "BACO CLEAN",
                    "default_code": "PDSBACCLN0001",
                    "barcode": "",
                    "product_tmpl_id": [10, "BACO CLEAN"],
                    "qty_available": 12,
                    "virtual_available": 14,
                    "uom_id": [1, "Unité(s)"],
                    "list_price": 4.0,
                    "sale_ok": True,
                    "active": True,
                },
                {
                    "id": 2,
                    "name": "UNRELATED PRODUCT",
                    "default_code": "XYZ-001",
                    "barcode": "",
                    "product_tmpl_id": [20, "UNRELATED PRODUCT"],
                    "qty_available": 5,
                    "virtual_available": 5,
                    "uom_id": [1, "Unité(s)"],
                    "list_price": 1.0,
                    "sale_ok": True,
                    "active": True,
                },
            ]

        if method == "search_read" and model == "product.template":
            return [
                {
                    "id": 3,
                    "name": "BACOTOP",
                    "default_code": "BACOTOP",
                    "barcode": "",
                    "qty_available": 1,
                    "virtual_available": 1,
                    "uom_id": [1, "Unité(s)"],
                    "list_price": 2.0,
                    "sale_ok": True,
                    "active": True,
                }
            ]

        raise AssertionError(f"Unexpected XML-RPC call: {model}.{method}")


def test_purchase_supplier_ranking_uses_read_group():
    fake_models = PurchaseSupplierRankingModels(
        read_group_result=[
            {"partner_id": [10, "Supplier A"], "__count": 8},
            {"partner_id": [20, "Supplier B"], "__count": 5},
        ]
    )
    connector = real_connector_with_models(fake_models)

    result = connector.rank_purchase_order_suppliers(limit=10)

    assert result["status"] == "completed"
    assert result["selected_model"] == "purchase.order"
    assert result["aggregation_field"] == "partner_id"
    assert result["odoo_method"] == "read_group"
    assert result["count_returned"] == 2
    assert result["records"][0] == {"supplier_id": 10, "supplier": "Supplier A", "count": 8}
    assert "secret_note" not in result["fields_used"]


def test_purchase_supplier_ranking_falls_back_to_search_read_when_read_group_fails():
    fake_models = PurchaseSupplierRankingModels(
        read_group_error=Exception("read_group unavailable"),
        search_read_result=[
            {"id": 1, "partner_id": [10, "Supplier A"]},
            {"id": 2, "partner_id": [10, "Supplier A"]},
            {"id": 3, "partner_id": [20, "Supplier B"]},
        ],
    )
    connector = real_connector_with_models(fake_models)

    result = connector.rank_purchase_order_suppliers(limit=10)

    assert result["status"] == "completed"
    assert result["odoo_method"] == "search_read_fallback"
    assert result["records"][0]["supplier"] == "Supplier A"
    assert result["records"][0]["count"] == 2
    assert any(call[1] == "search_read" for call in fake_models.calls)


def test_purchase_supplier_ranking_no_records_is_clear_not_found():
    fake_models = PurchaseSupplierRankingModels(read_group_result=[])
    connector = real_connector_with_models(fake_models)

    result = connector.rank_purchase_order_suppliers(limit=10)

    assert result["status"] == "not_found"
    assert result["failure_reason"] == "no_records"
    assert result["records"] == []
    assert "Aucun fournisseur" in result["message"]


def test_sale_customer_ranking_uses_read_group():
    fake_models = SaleCustomerRankingModels(
        read_group_result=[
            {"partner_id": [10, "Client A"], "__count": 8},
            {"partner_id": [20, "Client B"], "__count": 5},
        ]
    )
    connector = real_connector_with_models(fake_models)

    result = connector.rank_sale_order_customers(limit=10)

    assert result["status"] == "completed"
    assert result["selected_model"] == "sale.order"
    assert result["aggregation_field"] == "partner_id"
    assert result["odoo_method"] == "read_group"
    assert result["count_returned"] == 2
    assert result["records"][0] == {"customer_id": 10, "customer": "Client A", "count": 8}
    assert "secret_note" not in result["fields_used"]


def test_sale_customer_ranking_falls_back_to_search_read_when_read_group_fails():
    fake_models = SaleCustomerRankingModels(
        read_group_error=Exception("read_group unavailable"),
        search_read_result=[
            {"id": 1, "partner_id": [10, "Client A"]},
            {"id": 2, "partner_id": [10, "Client A"]},
            {"id": 3, "partner_id": [20, "Client B"]},
        ],
    )
    connector = real_connector_with_models(fake_models)

    result = connector.rank_sale_order_customers(limit=10)

    assert result["status"] == "completed"
    assert result["odoo_method"] == "search_read_fallback"
    assert result["records"][0]["customer"] == "Client A"
    assert result["records"][0]["count"] == 2
    assert any(call[1] == "search_read" for call in fake_models.calls)


def test_product_search_filters_results_to_requested_keyword():
    connector = real_connector_with_models(ProductSearchModels())

    result = connector.search_product("BACO")

    assert result["found"] is True
    names = {record["name"] for record in result["results"]}
    assert "BACO CLEAN" in names
    assert "BACOTOP" in names
    assert "UNRELATED PRODUCT" not in names
