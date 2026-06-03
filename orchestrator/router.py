def classify_intent(message: str):

    text = message.lower()

    if any(word in text for word in [
        "stock",
        "inventory",
        "odoo",
        "supplier",
        "customer"
    ]):
        return "odoo"

    if any(word in text for word in [
        "printer",
        "ticket",
        "support",
        "desktop"
    ]):
        return "support"

    if any(word in text for word in [
        "document",
        "procedure",
        "manual"
    ]):
        return "knowledge"

    return "general"


def select_model(intent: str):

    if intent == "odoo":
        return "gpt"

    if intent == "knowledge":
        return "claude"

    if intent == "support":
        return "gemini"

    return "gpt"

def select_agent(intent: str):
    if intent == "odoo":
        return "odoo_agent"

    if intent == "support":
        return "support_agent"

    if intent == "knowledge":
        return "knowledge_agent"

    return "general_agent"