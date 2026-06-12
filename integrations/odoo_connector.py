import os
from dotenv import load_dotenv

load_dotenv()


class OdooConnector:
    def __init__(self):
        self.url = os.getenv("ODOO_URL", "https://gjbtest31.odoo.com")
        self.database = os.getenv("ODOO_DB")
        self.username = os.getenv("ODOO_USERNAME")
        self.password = os.getenv("ODOO_PASSWORD")
        self.api_key = os.getenv("ODOO_API_KEY")

        self.credentials_configured = bool(
            self.url
            and self.database
            and self.username
            and (self.password or self.api_key)
        )

        self.mock_mode = not self.credentials_configured

    def is_configured(self):
        return self.credentials_configured

    def test_connection(self):
        if self.mock_mode:
            return {
                "connected": False,
                "mode": "mock",
                "url": self.url,
                "database_configured": bool(self.database),
                "username_configured": bool(self.username),
                "password_or_api_key_configured": bool(self.password or self.api_key),
                "message": "Odoo URL is configured, but credentials are missing. Running in mock mode."
            }

        return {
            "connected": False,
            "mode": "configured_pending_auth",
            "url": self.url,
            "database": self.database,
            "username": self.username,
            "message": "Odoo credentials are configured. Real authentication is not implemented yet."
        }

    def authenticate(self):
        if self.mock_mode:
            return {
                "authenticated": False,
                "mode": "mock",
                "message": "Authentication skipped because Odoo credentials are missing."
            }

        return {
            "authenticated": False,
            "mode": "configured_pending_auth",
            "message": "Authentication placeholder. Real XML-RPC/JSON-RPC login will be implemented next."
        }

    def search_product(self, product_name: str):
        if self.mock_mode:
            return {
                "source": "mock_odoo",
                "mode": "mock",
                "product": product_name,
                "found": True,
                "product_id": "MOCK-PROD-001",
                "name": product_name,
                "message": "Mock product result. Real Odoo credentials are not configured yet."
            }

        return {
            "source": "real_odoo_pending",
            "mode": "configured_pending_auth",
            "product": product_name,
            "message": "Real Odoo product search is pending authentication implementation."
        }

    def check_stock(self, product_name: str):
        if self.mock_mode:
            return {
                "source": "mock_odoo",
                "mode": "mock",
                "product": product_name,
                "stock_quantity": 42,
                "unit": "units",
                "warehouse": "Mock Warehouse",
                "message": "Mock stock result. Real Odoo credentials are not configured yet."
            }

        return {
            "source": "real_odoo_pending",
            "mode": "configured_pending_auth",
            "product": product_name,
            "message": "Real Odoo stock check is pending authentication implementation."
        }

    def search_customer(self, customer_name: str):
        if self.mock_mode:
            return {
                "source": "mock_odoo",
                "mode": "mock",
                "customer": customer_name,
                "found": True,
                "customer_id": "MOCK-CUST-001",
                "account_type": "business",
                "message": "Mock customer result. Real Odoo credentials are not configured yet."
            }

        return {
            "source": "real_odoo_pending",
            "mode": "configured_pending_auth",
            "customer": customer_name,
            "message": "Real Odoo customer search is pending authentication implementation."
        }

    def create_purchase_request(self, description: str):
        if self.mock_mode:
            return {
                "source": "mock_odoo",
                "mode": "mock",
                "action": "create_purchase_request",
                "description": description,
                "status": "waiting_for_approval",
                "message": "Mock purchase request prepared. Real Odoo credentials are not configured yet."
            }

        return {
            "source": "real_odoo_pending",
            "mode": "configured_pending_auth",
            "action": "create_purchase_request",
            "description": description,
            "message": "Real Odoo purchase request creation is pending authentication implementation."
        }

    def create_purchase_order(self, description: str):
        if self.mock_mode:
            return {
                "source": "mock_odoo",
                "mode": "mock",
                "action": "create_purchase_order",
                "description": description,
                "status": "waiting_for_approval",
                "message": "Mock purchase order prepared. Real Odoo credentials are not configured yet."
            }

        return {
            "source": "real_odoo_pending",
            "mode": "configured_pending_auth",
            "action": "create_purchase_order",
            "description": description,
            "message": "Real Odoo purchase order creation is pending authentication implementation."
        }