READ_ONLY_KEYWORDS = [
    "check",
    "show",
    "view",
    "get",
    "search",
    "consult",
    "retrieve",
    "verify",
    "display",
    "find",

    "vérifier",
    "verifier",
    "afficher",
    "voir",
    "consulter",
    "chercher",
    "rechercher",
    "récupérer",
    "recuperer",
]

SENSITIVE_ACTION_KEYWORDS = [
    "create",
    "delete",
    "update",
    "modify",
    "change",
    "approve",
    "reject",
    "cancel",
    "grant",
    "revoke",
    "set",
    "increase",
    "decrease",

    "créer",
    "creer",
    "supprimer",
    "modifier",
    "changer",
    "mettre à jour",
    "mettre a jour",
    "approuver",
    "rejeter",
    "annuler",
    "accorder",
    "révoquer",
    "revoquer",
    "définir",
    "definir",
    "augmenter",
    "diminuer",
]

SENSITIVE_OBJECT_KEYWORDS = [
    "stock",
    "inventory",
    "inventaire",
    "price",
    "prix",
    "unit",
    "unité",
    "unite",
    "invoice",
    "facture",
    "purchase order",
    "purchase request",
    "commande",
    "client",
    "customer",
    "record",
    "access",
    "accès",
    "acces",
]


def requires_approval(message: str) -> bool:
    if not message or not message.strip():
        return False

    text = message.lower()

    has_sensitive_action = any(
        keyword in text for keyword in SENSITIVE_ACTION_KEYWORDS
    )
    has_sensitive_object = any(
        keyword in text for keyword in SENSITIVE_OBJECT_KEYWORDS
    )

    if has_sensitive_action and has_sensitive_object:
        return True

    if has_sensitive_action:
        return True

    has_read_only_keyword = any(
        keyword in text for keyword in READ_ONLY_KEYWORDS
    )

    if has_read_only_keyword:
        return False

    return False