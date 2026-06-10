INTENT_AGENT_MAP = {
    "odoo": "odoo_agent",
    "support": "support_agent",
    "knowledge": "knowledge_agent",
    "development": "development_agent",
    "security": "security_agent",
    "server": "server_agent",
    "general": "general_agent",
}


def _result(intent: str, confidence: float):
    return {
        "intent": intent,
        "selected_agent": INTENT_AGENT_MAP.get(intent, "general_agent"),
        "confidence": confidence,
        "requires_approval": False,
        "classifier_source": "local_rules",
        "classifier_error": None,
    }


def classify_with_confidence(message: str):

    text = message.lower()

    if any(word in text for word in [
        "security", "cyber", "sécurité", "securite",
        "suspicious", "phishing", "malware", "breach",
        "unauthorized", "intrusion", "alert",
        "access", "accès", "permission", "permissions",
        "role", "roles"
    ]):
        return _result("security", 0.95)

    if any(word in text for word in [
        "bug", "error", "erreur", "exception",
        "deploy", "deployment", "déploiement",
        "code", "repository", "repo", "pull request"
    ]):
        return _result("development", 0.90)

    if any(word in text for word in [
        "server", "serveur", "service", "uptime",
        "downtime", "cpu", "ram", "disk", "memory",
        "database", "status", "statut"
    ]):
        return _result("server", 0.90)

    if any(word in text for word in [
        "stock", "inventory", "inventaire", "odoo",
        "supplier", "fournisseur",
        "customer", "client",
        "product", "produit",
        "purchase", "achat"
    ]):
        return _result("odoo", 0.95)

    if any(word in text for word in [
        "printer", "imprimante",
        "support", "ticket",
        "computer", "ordinateur",
        "password", "mot de passe",
        "network", "réseau", "reseau"
    ]):
        return _result("support", 0.95)

    if any(word in text for word in [
        "document", "documentation",
        "procedure", "procédure",
        "manual", "manuel",
        "guide", "policy", "politique"
    ]):
        return _result("knowledge", 0.95)

    return _result("general", 0.50)
