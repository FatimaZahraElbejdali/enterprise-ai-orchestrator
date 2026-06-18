from typing import Literal

RiskLevel = Literal["low", "medium", "high"]


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

HIGH_RISK_ACTIONS = [
    "delete",
    "remove",
    "approve payment",
    "payment",
    "refund",
    "grant access",
    "revoke access",
    "disable account",
    "admin access",

    "supprimer",
    "effacer",
    "paiement",
    "remboursement",
    "accorder accès",
    "accorder acces",
    "révoquer accès",
    "revoquer acces",
]

MEDIUM_RISK_ACTIONS = [
    "update",
    "modify",
    "change",
    "create",
    "set",
    "increase",
    "decrease",
    "restart",

    "mettre à jour",
    "mettre a jour",
    "modifier",
    "changer",
    "créer",
    "creer",
    "définir",
    "definir",
    "augmenter",
    "diminuer",
]

SENSITIVE_OBJECTS = [
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
    "order",
    "commande",
    "customer",
    "client",
    "record",
    "access",
    "accès",
    "acces",
]


def classify_risk(message: str) -> RiskLevel:
    if not message or not message.strip():
        return "low"

    text = message.lower()

    has_read_only = any(keyword in text for keyword in READ_ONLY_KEYWORDS)
    has_high_action = any(keyword in text for keyword in HIGH_RISK_ACTIONS)
    has_medium_action = any(keyword in text for keyword in MEDIUM_RISK_ACTIONS)
    has_sensitive_object = any(keyword in text for keyword in SENSITIVE_OBJECTS)

    if has_high_action:
        return "high"

    if has_medium_action and has_sensitive_object:
        return "medium"

    if has_medium_action:
        return "medium"

    if has_read_only:
        return "low"

    return "low"


def requires_approval_for_risk(risk_level: RiskLevel) -> bool:
    return risk_level in ["medium", "high"]