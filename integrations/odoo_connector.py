import os
import xmlrpc.client

from dotenv import load_dotenv

load_dotenv()


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
            models = self._models()

            products = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "product.template",
                "search_read",
                [[["name", "ilike", product_name]]],
                {
                    "fields": [
                        "id",
                        "name",
                        "default_code",
                        "qty_available",
                        "virtual_available",
                        "uom_id",
                        "list_price",
                    ],
                    "limit": 5,
                },
            )

            return {
                "source": "real_odoo",
                "product": product_name,
                "found": len(products) > 0,
                "results": products,
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
            models = self._models()

            products = models.execute_kw(
                self.database,
                self.uid,
                self.auth_secret,
                "product.template",
                "search_read",
                [[["name", "ilike", product_name]]],
                {
                    "fields": [
                        "id",
                        "name",
                        "default_code",
                        "qty_available",
                        "virtual_available",
                        "uom_id",
                        "list_price",
                    ],
                    "limit": 1,
                },
            )

            if not products:
                return {
                    "source": "real_odoo",
                    "product": product_name,
                    "found": False,
                    "message": "No product found in Odoo.",
                }

            product = products[0]
            unit = product.get("uom_id")

            return {
                "source": "real_odoo",
                "product": product.get("name"),
                "product_id": product.get("id"),
                "internal_reference": product.get("default_code") or "-",
                "stock_quantity": product.get("qty_available"),
                "forecast_quantity": product.get("virtual_available"),
                "sale_price": product.get("list_price"),
                "unit": unit[1] if unit else "-",
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