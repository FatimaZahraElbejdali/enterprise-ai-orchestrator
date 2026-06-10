from integrations.odoo_connector import OdooConnector

odoo = OdooConnector()


def check_stock(product_name: str):
    return odoo.check_stock(product_name)


def search_product(product_name: str):
    return odoo.search_product(product_name)


def search_customer(customer_name: str):
    return {
        "source": "mock_odoo",
        "customer": customer_name,
        "status": "found",
        "account_type": "business"
    }


def create_purchase_request(description: str):
    return odoo.create_purchase_request(description)


def run(message: str):
    text = message.lower()

    if "stock" in text or "inventaire" in text:
        return {
            "agent": "odoo",
            "tool_used": "check_stock",
            "result": check_stock(message)
        }

    if "product" in text or "produit" in text:
        return {
            "agent": "odoo",
            "tool_used": "search_product",
            "result": search_product(message)
        }

    if "customer" in text or "client" in text:
        return {
            "agent": "odoo",
            "tool_used": "search_customer",
            "result": search_customer(message)
        }

    if "purchase" in text or "achat" in text:
        return {
            "agent": "odoo",
            "tool_used": "create_purchase_request",
            "result": create_purchase_request(message)
        }

    return {
        "agent": "odoo",
        "tool_used": "test_connection",
        "result": odoo.test_connection()
    }