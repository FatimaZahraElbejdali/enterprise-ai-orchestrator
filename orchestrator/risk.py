from typing import Literal

RiskLevel = Literal["low", "medium", "high"]


HIGH_RISK_KEYWORDS = [
    "delete",
    "remove",
    "approve payment",
    "payment",
    "refund",
    "invoice",
    "salary",
    "payroll",
    "terminate",
    "disable account",
    "grant access",
    "admin access",
]

MEDIUM_RISK_KEYWORDS = [
    "update",
    "modify",
    "change",
    "restart",
    "create",
    "stock",
    "inventory",
    "order",
    "ticket",
    "customer record",
]


def classify_risk(message: str) -> RiskLevel:
    """
    Classify the business risk level of a user request.

    Low risk:
        Read-only or informational requests.

    Medium risk:
        Requests that may change internal data or system state.

    High risk:
        Requests involving money, access control, deletion, payroll,
        invoices, or destructive actions.
    """

    if not message or not message.strip():
        return "low"

    normalized_message = message.lower()

    if any(keyword in normalized_message for keyword in HIGH_RISK_KEYWORDS):
        return "high"

    if any(keyword in normalized_message for keyword in MEDIUM_RISK_KEYWORDS):
        return "medium"

    return "low"


def requires_approval_for_risk(risk_level: RiskLevel) -> bool:
    """
    Decide whether a request needs human approval based on risk.
    """

    return risk_level in ["medium", "high"]