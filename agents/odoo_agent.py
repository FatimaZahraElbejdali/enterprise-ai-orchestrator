import re

from orchestrator.tool_executor import execute_tool
from orchestrator.risk import classify_risk
from orchestrator.approval import requires_approval
from orchestrator.approval_store import create_approval
from orchestrator.audit import log_request


CHANGE_KEYWORDS = [
    "change",
    "modify",
    "update",
    "set",
    "increase",
    "decrease",
    "changer",
    "modifier",
    "mettre à jour",
    "mettre a jour",
    "définir",
    "definir",
    "augmenter",
    "diminuer",
]


def clean_product_name(value: str) -> str:
    if not value:
        return ""

    value = value.strip()

    value = re.sub(
        r"\s+(to|à|a)\s+\d+([.,]\d+)?\s*(dh|dhs|mad|dirhams?)?.*$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\s+(to|à|a)\s+[A-Za-zÀ-ÿ]+$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(r"[?.!,;:]+$", "", value)

    return value.strip()


def extract_product_name(message: str) -> str:
    text = message.strip()

    patterns = [
        r"(?:stock|inventory|inventaire)\s+(?:for|of|du|de|pour)\s+(.+)",
        r"(?:check|show|view|verify|get|consult|search)\s+(?:the\s+)?(?:stock|inventory|product|details|information)\s+(?:for|of)?\s*(.+)",
        r"(?:vérifier|verifier|consulter|afficher|chercher|rechercher)\s+(?:le\s+|la\s+|les\s+)?(?:stock|inventaire|produit|détails|details|informations?)\s+(?:de|du|pour)?\s*(.+)",

        r"(?:change|modify|update|set)\s+(?:the\s+)?(?:sale\s+)?price\s+(?:of|for)\s+(.+?)\s+(?:to|à|a)\s+",
        r"(?:changer|modifier|mettre à jour|mettre a jour|définir|definir)\s+(?:le\s+)?prix\s+(?:de|du|pour)\s+(.+?)\s+(?:à|a|to)\s+",

        r"(?:change|modify|update|set)\s+(?:the\s+)?stock\s+(?:of|for)\s+(.+?)\s+(?:to|à|a)\s+",
        r"(?:changer|modifier|mettre à jour|mettre a jour|définir|definir)\s+(?:le\s+)?stock\s+(?:de|du|pour)\s+(.+?)\s+(?:à|a|to)\s+",

        r"(?:change|modify|update|set)\s+(?:the\s+)?unit\s+(?:of|for)\s+(.+?)\s+(?:to|à|a)\s+",
        r"(?:changer|modifier|mettre à jour|mettre a jour|définir|definir)\s+(?:l['’]unité|unité|unite)\s+(?:de|du|pour)\s+(.+?)\s+(?:à|a|to)\s+",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return clean_product_name(match.group(1))

    fallback = text

    fallback = re.sub(
        r"^(check|show|view|get|verify|consult|search|find)\s+",
        "",
        fallback,
        flags=re.IGNORECASE,
    )

    fallback = re.sub(
        r"^(vérifier|verifier|afficher|voir|consulter|chercher|rechercher)\s+",
        "",
        fallback,
        flags=re.IGNORECASE,
    )

    fallback = re.sub(
        r"^(stock|inventory|inventaire|product|produit|details|détails|informations?)\s+(for|of|de|du|pour)?\s*",
        "",
        fallback,
        flags=re.IGNORECASE,
    )

    return clean_product_name(fallback)


def extract_requested_value(message: str):
    value_match = re.search(
        r"(?:to|à|a)\s+(\d+(?:[.,]\d+)?)\s*(dh|dhs|mad|dirhams?)?",
        message,
        re.IGNORECASE,
    )

    if value_match:
        number = value_match.group(1).replace(",", ".")
        currency = value_match.group(2) or ""
        return f"{number} {currency}".strip()

    unit_match = re.search(
        r"(?:to|à|a)\s+([A-Za-zÀ-ÿ]+)$",
        message.strip(),
        re.IGNORECASE,
    )

    if unit_match:
        return unit_match.group(1).strip()

    return None


def detect_odoo_action(message: str) -> str:
    text = message.lower()

    has_change = any(keyword in text for keyword in CHANGE_KEYWORDS)

    if "price" in text or "prix" in text:
        return "change_price" if has_change else "check_price"

    if "unit" in text or "unité" in text or "unite" in text:
        return "change_unit" if has_change else "check_unit"

    if "stock" in text or "inventory" in text or "inventaire" in text:
        return "change_stock" if has_change else "check_stock"

    if "invoice" in text or "facture" in text:
        if any(word in text for word in ["create", "update", "delete", "modify", "créer", "creer", "modifier", "supprimer"]):
            return "modify_invoice"
        return "check_invoice"

    if "purchase" in text or "achat" in text or "commande" in text:
        if any(word in text for word in ["create", "créer", "creer"]):
            return "create_purchase_request"
        return "check_purchase"

    if "product" in text or "produit" in text or "details" in text or "détails" in text or "information" in text:
        return "check_product_details"

    return "odoo_status"


def unwrap_tool_response(tool_response):
    if not isinstance(tool_response, dict):
        return tool_response

    if tool_response.get("success") is True and "result" in tool_response:
        return tool_response["result"]

    return tool_response


def normalize_stock_result(raw_result: dict, action: str):
    raw_result = unwrap_tool_response(raw_result)

    if not isinstance(raw_result, dict):
        return {
            "action": action,
            "source": "unknown",
            "found": False,
            "raw": raw_result,
        }

    return {
        "action": action,
        "found": raw_result.get("found", False),
        "product": raw_result.get("product"),
        "product_id": raw_result.get("product_id"),
        "internal_reference": raw_result.get("internal_reference"),
        "available_stock": raw_result.get("stock_quantity"),
        "forecast_stock": raw_result.get("forecast_quantity"),
        "sale_price": raw_result.get("sale_price"),
        "unit": raw_result.get("unit"),
        "warehouse": raw_result.get("warehouse"),
        "source": raw_result.get("source", "real_odoo"),
    }


def check_stock(product_name: str):
    return unwrap_tool_response(
        execute_tool(
            "odoo_check_stock",
            product_name=product_name,
        )
    )


def search_product(product_name: str):
    return unwrap_tool_response(
        execute_tool(
            "odoo_search_product",
            product_name=product_name,
        )
    )


def search_customer(customer_name: str):
    return unwrap_tool_response(
        execute_tool(
            "odoo_search_customer",
            customer_name=customer_name,
        )
    )


def build_sensitive_approval_response(message: str, action: str):
    risk = classify_risk(message)
    product_name = extract_product_name(message)
    requested_value = extract_requested_value(message)

    action_labels = {
        "change_price": "Modification du prix produit",
        "change_stock": "Modification du stock produit",
        "change_unit": "Modification de l’unité produit",
        "modify_invoice": "Action sensible sur facture",
        "create_purchase_request": "Création d’une demande d’achat",
    }

    title = action_labels.get(action, "Action Odoo sensible")

    approval = create_approval(
        user_message=message,
        intent="odoo",
        selected_agent="odoo_agent",
        selected_model="policy_engine",
        action=action,
        risk=risk,
        title=title,
        description="Cette demande nécessite une validation humaine avant toute exécution dans Odoo.",
        source_system="odoo",
        entity_name=product_name,
        requested_change=requested_value,
        metadata={
            "product": product_name,
            "requested_value": requested_value,
            "executed": False,
            "simulation": True,
        },
    )

    log_request({
        "event_type": "approval_required",
        "title": title,
        "system": "odoo",
        "agent": "odoo_agent",
        "status": "pending_approval",
        "risk": risk,
        "approval_status": "pending",
        "approval_id": approval["id"],
        "user_message": message,
        "action": action,
        "product": product_name,
        "requested_value": requested_value,
        "executed": False,
        "message": "Action bloquée avant exécution. Validation humaine requise.",
    })

    return {
        "intent": "odoo",
        "agent": "odoo_agent",
        "risk": risk,
        "requires_approval": True,
        "approval_required": True,
        "status": "pending_approval",
        "message": "Cette action nécessite une validation humaine avant exécution dans Odoo.",
        "approval_id": approval["id"],
        "tool_used": None,
        "data": {
            "action": action,
            "product": product_name,
            "requested_value": requested_value,
            "source": "approval_simulation",
            "executed": False,
        },
        "result": {
            "approval": approval,
        },
    }


def run(message: str):
    action = detect_odoo_action(message)

    sensitive_actions = {
        "change_price",
        "change_stock",
        "change_unit",
        "modify_invoice",
        "create_purchase_request",
    }

    if action in sensitive_actions or requires_approval(message):
        return build_sensitive_approval_response(message, action)

    if action in ["check_stock", "check_price", "check_unit", "check_product_details"]:
        product_name = extract_product_name(message)
        raw_result = check_stock(product_name)
        data = normalize_stock_result(raw_result, action)

        found = bool(data.get("found"))

        log_request({
            "event_type": "odoo_read",
            "title": "Consultation produit Odoo",
            "system": "odoo",
            "agent": "odoo_agent",
            "status": "completed" if found else "not_found",
            "risk": "low",
            "approval_status": "not_required",
            "user_message": message,
            "action": action,
            "product": product_name,
            "message": "Données produit consultées dans Odoo sans modification.",
            "data": data,
        })

        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "risk": "low",
            "requires_approval": False,
            "approval_required": False,
            "status": "completed" if found else "not_found",
            "message": "Données produit consultées avec succès." if found else "Produit introuvable dans Odoo.",
            "tool_used": "odoo_check_stock",
            "data": data,
            "result": raw_result,
        }

    if "customer" in message.lower() or "client" in message.lower():
        raw_result = search_customer(message)

        log_request({
            "event_type": "odoo_read",
            "title": "Recherche client Odoo",
            "system": "odoo",
            "agent": "odoo_agent",
            "status": "completed",
            "risk": "low",
            "approval_status": "not_required",
            "user_message": message,
            "action": "search_customer",
            "message": "Recherche client consultative sans modification.",
        })

        return {
            "intent": "odoo",
            "agent": "odoo_agent",
            "risk": "low",
            "requires_approval": False,
            "approval_required": False,
            "status": "completed",
            "message": "Recherche client exécutée.",
            "tool_used": "odoo_search_customer",
            "data": raw_result,
            "result": raw_result,
        }

    raw_result = unwrap_tool_response(execute_tool("odoo_test_connection"))

    log_request({
        "event_type": "odoo_status",
        "title": "Vérification connexion Odoo",
        "system": "odoo",
        "agent": "odoo_agent",
        "status": "completed",
        "risk": "low",
        "approval_status": "not_required",
        "user_message": message,
        "action": "odoo_status",
        "message": "Statut de connexion Odoo consulté.",
    })

    return {
        "intent": "odoo",
        "agent": "odoo_agent",
        "risk": "low",
        "requires_approval": False,
        "approval_required": False,
        "status": "completed",
        "message": "Statut Odoo consulté.",
        "tool_used": "odoo_test_connection",
        "data": raw_result,
        "result": raw_result,
    }