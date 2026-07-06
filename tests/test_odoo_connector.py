from integrations.odoo_connector import OdooConnector


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
