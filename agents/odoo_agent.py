def check_stock(product_name: str):
    return {
        "product": product_name,
        "stock_quantity": 42,
        "status": "available"
    }


def search_customer(customer_name: str):
    return {
        "customer": customer_name,
        "status": "found",
        "account_type": "business"
    }


def create_purchase_request(product_name: str):
    return {
        "action": "create_purchase_request",
        "product": product_name,
        "status": "waiting_for_approval"
    }


def run(message: str):
    text = message.lower()

    if "stock" in text or "inventaire" in text:
        return {
            "agent": "odoo",
            "tool_used": "check_stock",
            "result": check_stock(message)
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
        "tool_used": "none",
        "result": "Odoo Agent received the request but no specific tool matched."
    }