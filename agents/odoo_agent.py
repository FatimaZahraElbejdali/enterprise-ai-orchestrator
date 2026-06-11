from orchestrator.tool_executor import execute_tool


def check_stock(product_name: str):
    return execute_tool(
        "odoo_check_stock",
        product_name=product_name
    )


def search_product(product_name: str):
    return execute_tool(
        "odoo_search_product",
        product_name=product_name
    )


def search_customer(customer_name: str):
    return execute_tool(
        "odoo_search_customer",
        customer_name=customer_name
    )


def create_purchase_request(description: str):
    return execute_tool(
        "odoo_create_purchase_request",
        description=description
    )


def run(message: str):
    text = message.lower()

    if "stock" in text or "inventaire" in text:
        return {
            "agent": "odoo",
            "tool_used": "odoo_check_stock",
            "result": check_stock(message)
        }

    if "product" in text or "produit" in text:
        return {
            "agent": "odoo",
            "tool_used": "odoo_search_product",
            "result": search_product(message)
        }

    if "customer" in text or "client" in text:
        return {
            "agent": "odoo",
            "tool_used": "odoo_search_customer",
            "result": search_customer(message)
        }

    if "purchase" in text or "achat" in text:
        return {
            "agent": "odoo",
            "tool_used": "odoo_create_purchase_request",
            "result": create_purchase_request(message)
        }

    return {
        "agent": "odoo",
        "tool_used": "odoo_test_connection",
        "result": execute_tool("odoo_test_connection")
    }