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
