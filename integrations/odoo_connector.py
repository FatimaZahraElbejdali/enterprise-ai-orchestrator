import os
from dotenv import load_dotenv

load_dotenv()


class OdooConnector:
    def __init__(self):
        self.url = os.getenv("ODOO_URL")
        self.database = os.getenv("ODOO_DB")
        self.username = os.getenv("ODOO_USERNAME")
        self.password = os.getenv("ODOO_PASSWORD")
        self.api_key = os.getenv("ODOO_API_KEY")

        self.mock_mode = not (
            self.url
            and self.database
            and self.username
            and (self.password or self.api_key)
        )

    def is_configured(self):
        return not self.mock_mode

    def test_connection(self):
        if self.mock_mode:
            return {
                "connected": False,
                "mode": "mock",
                "message": "Odoo credentials are not configured yet."
            }

        return {
            "connected": True,
            "mode": "configured",
            "message": "Odoo credentials are configured. Real connection will be implemented when Odoo access is provided.",
            "url": self.url,
            "database": self.database,
            "username": self.username
        }

    def authenticate(self):
        if self.mock_mode:
            return {
                "authenticated": False,
                "mode": "mock",
                "message": "Authentication skipped because Odoo credentials are not configured."
            }

        return {
            "authenticated": True,
            "mode": "configured",
            "message": "Authentication placeholder. Real XML-RPC/JSON-RPC login will be implemented next."
        }

    def search_product(self, product_name: str):
        if self.mock_mode:
            return {
                "source": "mock_odoo",
                "product": product_name,
                "found": True,
                "product_id": "MOCK-PROD-001",
                "name": product_name
            }

        return {
            "source": "real_odoo_pending",
            "product": product_name,
            "message": "Real Odoo product search not implemented yet."
        }

    def check_stock(self, product_name: str):
        if self.mock_mode:
            return {
                "source": "mock_odoo",
                "product": product_name,
                "stock_quantity": 42,
                "unit": "units",
                "warehouse": "Mock Warehouse"
            }

        return {
            "source": "real_odoo_pending",
            "product": product_name,
            "message": "Real Odoo stock check not implemented yet."
        }

    def search_customer(self, customer_name: str):
        if self.mock_mode:
            return {
                "source": "mock_odoo",
                "customer": customer_name,
                "found": True,
                "customer_id": "MOCK-CUST-001",
                "account_type": "business"
            }

        return {
            "source": "real_odoo_pending",
            "customer": customer_name,
            "message": "Real Odoo customer search not implemented yet."
        }

    def create_purchase_request(self, description: str):
        if self.mock_mode:
            return {
                "source": "mock_odoo",
                "action": "create_purchase_request",
                "description": description,
                "status": "waiting_for_approval"
            }

        return {
            "source": "real_odoo_pending",
            "action": "create_purchase_request",
            "description": description,
            "message": "Real Odoo purchase request creation not implemented yet."
        }

    def create_purchase_order(self, description: str):
        if self.mock_mode:
            return {
                "source": "mock_odoo",
                "action": "create_purchase_order",
                "description": description,
                "status": "waiting_for_approval"
            }

        return {
            "source": "real_odoo_pending",
            "action": "create_purchase_order",
            "description": description,
            "message": "Real Odoo purchase order creation not implemented yet."
        }