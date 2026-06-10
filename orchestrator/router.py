def classify_intent(message: str):

    text = message.lower()

    # =========================
    # ODOO / ERP
    # =========================

    if any(word in text for word in [
        "stock",
        "inventory",
        "inventaire",
        "odoo",
        "supplier",
        "suppliers",
        "fournisseur",
        "fournisseurs",
        "customer",
        "customers",
        "client",
        "clients",
        "product",
        "products",
        "produit",
        "produits",
        "purchase",
        "purchase order",
        "purchase request",
        "achat",
        "commande",
        "commande achat",
        "vente",
        "sales",
        "facture",
        "invoice",
        "erp"
    ]):
        return "odoo"

    # =========================
    # SUPPORT
    # =========================

    if any(word in text for word in [
        "printer",
        "imprimante",
        "ticket",
        "support",
        "helpdesk",
        "desktop",
        "ordinateur",
        "computer",
        "pc",
        "laptop",
        "incident",
        "problem",
        "issue",
        "error",
        "bug",
        "panne",
        "réseau",
        "reseau",
        "network",
        "wifi",
        "connexion",
        "connection",
        "login",
        "mot de passe",
        "password",
        "access",
        "accès"
    ]):
        return "support"

    # =========================
    # KNOWLEDGE
    # =========================

    if any(word in text for word in [
        "document",
        "documents",
        "documentation",
        "procedure",
        "procedures",
        "procédure",
        "procédures",
        "manual",
        "manuel",
        "guide",
        "policy",
        "politique",
        "instruction",
        "instructions",
        "knowledge",
        "knowledge base",
        "base de connaissance",
        "wiki",
        "how to",
        "comment faire"
    ]):
        return "knowledge"

    return "general"


def select_agent(intent: str):

    if intent == "odoo":
        return "odoo_agent"

    if intent == "support":
        return "support_agent"

    if intent == "knowledge":
        return "knowledge_agent"

    if intent == "development":
        return "development_agent"

    if intent == "security":
        return "security_agent"

    if intent == "server":
        return "server_agent"

    return "general_agent"


def select_model(intent: str):

    # Later we'll make this dynamic
    # depending on cost, latency, confidence, etc.

    if intent == "odoo":
        return "gpt"

    if intent == "support":
        return "gemini"

    if intent == "knowledge":
        return "claude"

    if intent == "development":
        return "gpt"

    if intent == "security":
        return "claude"

    if intent == "server":
        return "gemini"

    return "gpt"
