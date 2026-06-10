ACTION_KEYWORDS = [

    # English
    "create",
    "delete",
    "update",
    "modify",
    "approve",
    "reject",
    "assign",
    "schedule",
    "send",
    "cancel",
    "purchase order",
    "purchase request",
    "access request",
    "access change",
    "grant access",
    "revoke access",
    "permission change",
    "role change",

    # French
    "créer",
    "creer",
    "supprimer",
    "modifier",
    "mettre à jour",
    "mettre a jour",
    "approuver",
    "rejeter",
    "assigner",
    "planifier",
    "envoyer",
    "annuler",
    "commande achat",
    "demande achat",
    "demande accès",
    "demande acces",
    "changement accès",
    "changement acces",
    "accorder accès",
    "accorder acces",
    "révoquer accès",
    "revoquer acces",
]


def requires_approval(message: str) -> bool:
    text = message.lower()

    return any(
        keyword in text
        for keyword in ACTION_KEYWORDS
    )
