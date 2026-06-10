import os
from dotenv import load_dotenv

load_dotenv()


class OdooConnector:
    def __init__(self):
        self.url = os.getenv("ODOO_URL")
        self.database = os.getenv("ODOO_DB")
        self.username = os.getenv("ODOO_USERNAME")
        self.password = os.getenv("ODOO_PASSWORD")

    def is_configured(self):
        return all([
            self.url,
            self.database,
            self.username,
            self.password
        ])

    def test_connection(self):
        if not self.is_configured():
            return {
                "connected": False,
                "mode": "mock",
                "message": "Odoo credentials are not configured yet."
            }

        return {
            "connected": True,
            "mode": "configured",
            "message": "Odoo credentials are configured. Real connection will be implemented next."
        }

    def search_product(self, product_name: str):
        if not self.is_configured():
            return {
                "source": "mock_odoo",
                "product": product_name,
                "found": True,
                "product_id": "MOCK-PROD-001"
            }

        return {
            "source": "real_odoo_pending",
            "product": product_name,
            "message": "Real Odoo product search not implemented yet."
        }

    def check_stock(self, product_name: str):
        if not self.is_configured():
            return {
                "source": "mock_odoo",
                "product": product_name,
                "stock_quantity": 42,
                "unit": "units"
            }

        return {
            "source": "real_odoo_pending",
            "product": product_name,
            "message": "Real Odoo stock check not implemented yet."
        }

    def create_purchase_request(self, description: str):
        if not self.is_configured():
            return {
                "source": "mock_odoo",
                "action": "create_purchase_request",
                "description": description,
                "status": "waiting_for_approval"
            }

        return {
            "source": "real_odoo_pending",
            "action": "create_purchase_request",
            "message": "Real Odoo purchase request creation not implemented yet."
        }