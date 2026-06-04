ACTION_KEYWORDS = [
    # English
    "create",
    "delete",
    "update",
    "modify",
    "approve",
    "reject",
    "schedule",
    "assign",
    "send",
    "cancel",
    "purchase order",
    "purchase request",

    # French
    "créer",
    "creer",
    "supprimer",
    "modifier",
    "mettre à jour",
    "mettre a jour",
    "approuver",
    "rejeter",
    "planifier",
    "assigner",
    "envoyer",
    "annuler",
    "commande achat",
    "demande achat",
]
def requires_approval(message: str) -> bool:
    text = message.lower()
    return any(keyword in text for keyword in ACTION_KEYWORDS)