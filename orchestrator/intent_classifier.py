def classify_with_confidence(message: str):

    text = message.lower()

    if any(word in text for word in [
        "stock", "inventory", "inventaire", "odoo",
        "supplier", "fournisseur",
        "customer", "client",
        "product", "produit",
        "purchase", "achat"
    ]):
        return {
            "intent": "odoo",
            "confidence": 0.95
        }

    if any(word in text for word in [
        "printer", "imprimante",
        "support", "ticket",
        "computer", "ordinateur",
        "password", "mot de passe",
        "network", "réseau", "reseau"
    ]):
        return {
            "intent": "support",
            "confidence": 0.95
        }

    if any(word in text for word in [
        "document", "documentation",
        "procedure", "procédure",
        "manual", "manuel",
        "guide", "policy", "politique"
    ]):
        return {
            "intent": "knowledge",
            "confidence": 0.95
        }

    return {
        "intent": "general",
        "confidence": 0.50
    }