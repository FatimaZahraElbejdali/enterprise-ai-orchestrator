import os
import re
import unicodedata

from dotenv import load_dotenv

from agents.knowledge_agent import (
    is_general_information_question,
    is_internal_knowledge_question,
    is_orchestrator_help_question,
)
from agents.server_agent import (
    extract_specific_server_reference,
    is_vague_server_problem,
)
from models.openai_router import classify_with_openai_router
from orchestrator.action_capability_registry import (
    enrich_route_with_capability_contract,
    route_from_business_capability,
)
from orchestrator.intent_classifier import classify_with_confidence
from orchestrator.tool_registry import get_capability_metadata

load_dotenv()


AGENT_TARGET_MAP = {
    "odoo_agent": "odoo",
    "support_agent": "support",
    "server_agent": "server",
    "security_agent": "security",
    "knowledge_agent": "knowledge",
    "development_agent": "development",
    "general_agent": "general",
}

INTENT_TARGET_MAP = {
    "odoo": "odoo",
    "support": "support",
    "server": "server",
    "security": "security",
    "knowledge": "knowledge",
    "development": "development",
    "general": "general",
}

ODOO_WRITE_ACTIONS = {
    "create",
    "write",
    "update",
    "delete",
    "unlink",
    "modify",
    "change",
    "set",
    "update_product_price",
    "change_price",
    "update_document_line",
    "update_document_partner",
    "update_document_date",
    "create_purchase_request",
}

SUPPORT_ISSUE_TERMS = {
    "wifi",
    "wi-fi",
    "vpn",
    "imprimante",
    "printer",
    "ordinateur",
    "computer",
    "connexion",
    "login",
    "access",
    "acces",
    "lenteur",
    "slow",
}

SERVER_DIAGNOSTIC_TERMS = {
    "status",
    "etat",
    "health",
    "cpu",
    "ram",
    "memoire",
    "memory",
    "disk",
    "disque",
    "uptime",
    "backend",
    "frontend",
    "service",
    "diagnostic",
}

SERVER_CONTEXT_TERMS = {
    "server",
    "serveur",
    "infrastructure",
    "service",
    "services",
}

SERVER_METRIC_TERMS = {
    "cpu",
    "ram",
    "memoire",
    "memory",
    "disk",
    "disque",
    "uptime",
}

DEVELOPMENT_HELP_TERMS = {
    "api",
    "backend",
    "code",
    "debug",
    "endpoint",
    "erreur",
    "error",
    "fastapi",
    "frontend",
    "nextjs",
    "python",
    "react",
    "typescript",
}

INTENT_ALIASES = {
    "server_documentation_summary": "summarize_server_documentation",
}

SERVER_CAPABILITY_ACTIONS = {
    "server.cpu_usage": ("server_cpu_usage", "check_cpu_usage"),
    "server.disk_usage": ("server_disk_usage", "check_disk_usage"),
    "server.local_health": ("server_health_check", "check_server_health"),
    "server.ram_usage": ("server_ram_usage", "check_ram_usage"),
    "server.uptime": ("server_status", "check_server_status"),
}

SERVER_ACTION_CAPABILITIES = {
    action: capability
    for capability, (_intent, action) in SERVER_CAPABILITY_ACTIONS.items()
}
SERVER_ACTION_CAPABILITIES["check_service_status"] = "server.local_health"
SERVER_ACTION_CAPABILITIES["server_diagnostic_summary"] = "server.local_health"

SERVER_SIGNAL_CAPABILITIES = {
    "backend": "server.local_health",
    "cpu": "server.cpu_usage",
    "diagnostic": "server.local_health",
    "disk": "server.disk_usage",
    "disque": "server.disk_usage",
    "etat": "server.local_health",
    "état": "server.local_health",
    "frontend": "server.local_health",
    "health": "server.local_health",
    "local_health": "server.local_health",
    "memory": "server.ram_usage",
    "memoire": "server.ram_usage",
    "ram": "server.ram_usage",
    "service": "server.local_health",
    "services": "server.local_health",
    "state": "server.local_health",
    "status": "server.local_health",
    "uptime": "server.uptime",
}

SERVER_DIAGNOSTIC_OPERATIONS = {
    "check",
    "diagnose",
    "diagnostic",
    "etat",
    "état",
    "health",
    "inspect",
    "monitor",
    "state",
    "status",
    "uptime",
}

SERVER_UNSUPPORTED_RESOURCE_ACTION_TERMS = {
    "create",
    "cree",
    "crée",
    "gerer",
    "gérer",
    "list",
    "liste",
    "lister",
    "manage",
}

SERVER_RESOURCE_TERMS = {
    "file",
    "files",
    "fichier",
    "fichiers",
    "internal server",
    "ressource serveur",
    "ressources serveur",
    "server resource",
    "server resources",
    "stockage interne",
}

ENTERPRISE_SYSTEM_TERMS = (
    SERVER_CONTEXT_TERMS
    | SERVER_DIAGNOSTIC_TERMS
    | SERVER_METRIC_TERMS
    | SUPPORT_ISSUE_TERMS
    | {
        "api key",
        "approval",
        "approve",
        "approbation",
        "audit",
        "business",
        "cle ssh",
        "clés ssh",
        "database",
        "env",
        "erp",
        "facture",
        "fichier",
        "fichiers",
        "internal",
        "interne",
        "inventory",
        "inventaire",
        "invoice",
        "jamain",
        "odoo",
        "password",
        "produit",
        "product",
        "rag",
        "secret",
        "shell",
        "ssh",
        "stock",
        "token",
    }
)

BACKEND_ACTION_TERMS = {
    "approve",
    "book",
    "buy",
    "cancel",
    "change",
    "changer",
    "create",
    "delete",
    "execute",
    "install",
    "modifier",
    "modify",
    "pay",
    "remove",
    "reserve",
    "réserve",
    "run",
    "send",
    "set",
    "transfer",
    "update",
}

SERVER_DOCUMENTATION_OPERATIONS = {
    "documentation",
    "document",
    "explain",
    "explanation",
    "resume",
    "résume",
    "summarize",
}

BANK_ACCOUNTING_READ_TERMS = {
    "releve bancaire",
    "releves bancaires",
    "bank statement",
    "bank statements",
    "transaction bancaire",
    "transactions bancaires",
    "ecriture bancaire",
    "ecritures bancaires",
    "journal bancaire",
    "journaux bancaires",
    "bank transaction",
    "bank transactions",
    "accounting transaction",
    "accounting transactions",
}

SUPPLIER_RANKING_TERMS = {
    "apparait",
    "apparaissent",
    "classement",
    "count",
    "distribution",
    "frequence",
    "frequency",
    "le plus",
    "les plus",
    "most",
    "nombre",
    "par",
    "ranking",
    "repartition",
    "répartition",
    "top",
}

SUPPLIER_TERMS = {
    "fournisseur",
    "fournisseurs",
    "supplier",
    "suppliers",
    "vendor",
    "vendors",
}

CUSTOMER_TERMS = {
    "client",
    "clients",
    "customer",
    "customers",
}

PURCHASE_ORDER_TERMS = {
    "bon de commande",
    "bons de commande",
    "commande fournisseur",
    "commandes fournisseur",
    "commandes fournisseurs",
    "purchase order",
    "purchase orders",
}

SALE_ORDER_TERMS = {
    "commande client",
    "commandes client",
    "commande de vente",
    "commandes de vente",
    "sale order",
    "sale orders",
    "sales order",
    "sales orders",
    "devis",
    "quotation",
    "quotations",
}

ORDER_LIST_TERMS = {
    "dernier",
    "derniers",
    "donne",
    "liste",
    "lister",
    "quelques",
    "recent",
    "recents",
    "recentes",
    "récent",
    "récents",
    "récentes",
    "show",
    "list",
}

KNOWLEDGE_RETRIEVAL_SIGNALS = {
    "company",
    "documentation",
    "document",
    "groupe",
    "history",
    "histoire",
    "internal",
    "interne",
    "jamain",
    "baco",
    "official",
    "officiel",
}


ODOO_DOCUMENT_PATTERNS = [
    r"\bdocument\s+id\b",
    r"\bid\s+document\b",
    r"\bid\s+du\s+document\b",
    r"\bd[ée]tails?\s+du\s+document\s+id\b",
    r"\bdetails?\s+of\s+document\s+id\b",
    r"\bbon\s+de\s+commande\b",
    r"\bbons\s+de\s+commande\b",
    r"\bcommande\s+fournisseur\b",
    r"\bcommandes\s+fournisseurs?\b",
    r"\bbon\s+de\s+livraison\b",
    r"\bbons\s+de\s+livraison\b",
    r"\bfacture\b",
    r"\blivraison\b",
    r"\bstock\s+picking\b",
    r"\bpurchase\s+order\b",
    r"\bsale\s+order\b",
    r"\binvoice\b",
]

ODOO_DOCUMENT_SEARCH_PATTERNS = [
    r"\b(?:cherche|chercher|recherche|rechercher|search|find)\b",
]


def is_odoo_document_request(message: str) -> bool:
    text = (message or "").lower().replace("’", "'")
    reference_like = bool(
        re.search(r"\b(?=[A-Z0-9/.-]*\d)[A-Z]{1,8}[-/][A-Z0-9][A-Z0-9/.-]{3,}\b", message or "")
    )

    if reference_like and re.search(r"\bdocument\b|\br[ée]f[ée]rence\b|\breference\b", text):
        return True

    return any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in ODOO_DOCUMENT_PATTERNS
    )


def is_odoo_document_search_request(message: str) -> bool:
    text = (message or "").lower().replace("’", "'")

    return is_odoo_document_request(message) and any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in ODOO_DOCUMENT_SEARCH_PATTERNS
    )


def odoo_document_intent(message: str) -> str:
    if is_odoo_document_search_request(message):
        return "odoo_document_search"

    return "odoo_document_details"


def _normalize_text(message: str) -> str:
    normalized = unicodedata.normalize("NFKD", message or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().replace("’", "'").split())


def _confidence_label(value) -> str:
    if value in {"high", "medium", "low"}:
        return value

    try:
        score = float(value)
    except (TypeError, ValueError):
        return "medium"

    if score >= 0.85:
        return "high"

    if score >= 0.65:
        return "medium"

    return "low"


def _route(
    *,
    intent: str,
    selected_agent: str,
    action: str,
    risk_level: str,
    requires_approval: bool,
    confidence="medium",
    reason: str = "Deterministic fallback route.",
    source: str = "local_rules_fallback",
    error=None,
    entities: dict | None = None,
    capability: str | None = None,
    request_type: str | None = None,
    domain: str | None = None,
    execution_mode: str | None = None,
    parameters: dict | None = None,
    capability_validation_error: str | None = None,
):
    target_system = AGENT_TARGET_MAP.get(selected_agent, "general")
    route = {
        "intent": intent,
        "agent": selected_agent,
        "selected_agent": selected_agent,
        "action": action,
        "target_system": domain or target_system,
        "risk_level": risk_level,
        "risk": risk_level,
        "requires_approval": requires_approval,
        "approval_required": requires_approval,
        "entities": entities or {},
        "confidence": _confidence_label(confidence),
        "reason": reason,
        "classifier_source": source,
        "classifier_error": error,
    }

    if capability:
        route["capability"] = capability

    if request_type:
        route["request_type"] = request_type

    if domain:
        route["domain"] = domain

    if execution_mode:
        route["execution_mode"] = execution_mode

    if parameters is not None:
        route["parameters"] = parameters

    if capability_validation_error:
        route["capability_validation_error"] = capability_validation_error

    return route


def _blocked_security_route(intent: str, reason: str):
    return _route(
        intent=intent,
        selected_agent="security_agent",
        action="block_request",
        risk_level="blocked",
        requires_approval=False,
        confidence="high",
        reason=reason,
        source="backend_safety_override",
    )


def _is_secret_or_sensitive_path_request(message: str) -> bool:
    text = _normalize_text(message)

    if any(token in text for token in [".env", "/etc/passwd", "../.env"]):
        return True

    secret_terms = [
        "api key",
        "api keys",
        "cle api",
        "cles api",
        "ssh key",
        "ssh keys",
        "cle ssh",
        "cles ssh",
        "private key",
        "secret",
        "secrets",
        "token",
        "tokens",
        "environment variable",
        "environment variables",
        "variables d'environnement",
        "variables denvironnement",
        "variable d'environnement",
        "variable denvironnement",
        "mot de passe du serveur",
    ]
    password_terms = [
        "password",
        "passwords",
        "mot de passe",
        "mots de passe",
    ]
    exfiltration_verbs = [
        "show",
        "display",
        "print",
        "read",
        "list",
        "give",
        "reveal",
        "dump",
        "affiche",
        "afficher",
        "montre",
        "montrer",
        "donne",
        "donner",
        "liste",
        "lister",
        "lis",
        "lire",
    ]
    support_password_phrases = [
        "password reset",
        "reset password",
        "mot de passe oublie",
        "reinitialiser",
        "reinitialisation",
    ]

    if any(phrase in text for phrase in support_password_phrases):
        return False

    has_secret = any(term in text for term in secret_terms + password_terms)
    asks_to_reveal = any(verb in text for verb in exfiltration_verbs)

    return has_secret and asks_to_reveal


def _is_destructive_or_dangerous_request(message: str) -> bool:
    text = _normalize_text(message)

    dangerous_commands = [
        "rm -rf",
        "sudo rm",
        "mkfs",
        "chmod 777",
        "curl | sh",
        "wget | sh",
        "drop database",
        "truncate table",
        "delete database",
        "format disk",
    ]
    destructive_verbs = [
        "delete",
        "remove",
        "destroy",
        "wipe",
        "erase",
        "drop",
        "truncate",
        "supprime",
        "supprimer",
        "efface",
        "effacer",
        "detruire",
        "détruire",
    ]

    return any(command in text for command in dangerous_commands) or any(
        re.search(rf"\b{re.escape(verb)}\b", text)
        for verb in destructive_verbs
    )


def _is_unsupported_server_resource_request(message: str) -> bool:
    text = _normalize_text(message)

    if not any(term in text for term in SERVER_CONTEXT_TERMS):
        return False

    if any(term in text for term in SERVER_DIAGNOSTIC_TERMS | SERVER_METRIC_TERMS):
        return False

    has_resource = any(term in text for term in SERVER_RESOURCE_TERMS)
    has_unsupported_action = any(
        re.search(rf"\b{re.escape(term)}\b", text)
        for term in SERVER_UNSUPPORTED_RESOURCE_ACTION_TERMS
    )

    return has_resource and has_unsupported_action


def _server_diagnostic_capability_from_message(message: str) -> str | None:
    text = _normalize_text(message)

    if not any(term in text for term in SERVER_CONTEXT_TERMS | {"infrastructure"}):
        return None

    if _is_unsupported_server_resource_request(message):
        return None

    documentation_terms = {
        "documentation",
        "document",
        "manuel",
        "manual",
        "guide",
    }

    if any(term in text for term in documentation_terms):
        return None

    if any(term in text for term in {"ram", "memoire", "memory"}):
        return "server.ram_usage"

    if any(term in text for term in {"cpu", "processeur", "processor"}):
        return "server.cpu_usage"

    if any(term in text for term in {"disque", "disk", "espace disque", "storage"}):
        return "server.disk_usage"

    if "uptime" in text:
        return "server.uptime"

    has_status_signal = any(
        term in text
        for term in {
            "actif",
            "diagnostic",
            "etat",
            "health",
            "status",
            "statut",
            "verifie",
            "verifier",
        }
    )

    if has_status_signal:
        return "server.local_health"

    return None


def _cheap_safe_general_route(message: str) -> dict | None:
    text = _normalize_text(message)

    if not text:
        return None

    tokens = re.findall(r"[a-z0-9]+", text)

    if len(tokens) > 6:
        return None

    if any(term in text for term in ENTERPRISE_SYSTEM_TERMS):
        return None

    if any(re.search(rf"\b{re.escape(term)}\b", text) for term in BACKEND_ACTION_TERMS):
        return None

    if is_general_information_question(message):
        return None

    if is_internal_knowledge_question(message):
        return None

    return _route(
        intent="general_information_question",
        selected_agent="knowledge_agent",
        action="answer_question",
        risk_level="low",
        requires_approval=False,
        confidence="high",
        reason=(
            "Cheap safety pre-router selected direct LLM for harmless general "
            "conversation without backend action signals."
        ),
        source="safe_general_pre_router",
        capability="knowledge.general_answer",
        request_type="general_knowledge",
        domain="knowledge",
        execution_mode="llm_direct",
        parameters={},
    )


def _is_odoo_access_issue(message: str) -> bool:
    text = _normalize_text(message)

    if "odoo" not in text:
        return False

    return any(
        term in text
        for term in [
            "n'arrive pas",
            "narrive pas",
            "probleme de connexion",
            "ne s'ouvre pas",
            "ne souvre pas",
            "acceder",
            "access",
            "cannot access",
            "can't access",
            "login",
            "connexion",
        ]
    )


def _is_odoo_write_request(message: str) -> bool:
    text = _normalize_text(message)
    has_write = any(
        term in text
        for term in [
            "modifier",
            "changer",
            "mettre a jour",
            "update",
            "change",
            "set",
            "create",
            "delete",
        ]
    )

    if "odoo" in text and has_write:
        return True

    has_odoo_object = any(
        term in text
        for term in [
            "prix",
            "price",
            "stock",
            "produit",
            "product",
            "facture",
            "invoice",
            "commande",
            "document",
            "client",
            "customer",
            "fournisseur",
            "supplier",
            "partner",
            "partenaire",
            "telephone",
            "téléphone",
            "email",
            "pointage",
            "analytique",
            "releve bancaire",
            "releves bancaires",
            "bank statement",
            "transaction bancaire",
            "transactions bancaires",
            "ecriture bancaire",
            "ecritures bancaires",
            "journal bancaire",
            "accounting transaction",
        ]
    )

    return has_write and has_odoo_object


def _is_odoo_read_request(message: str) -> bool:
    text = _normalize_text(message)

    if is_odoo_document_request(message):
        return True

    if (
        _is_odoo_connection_status_message(message)
        or _is_sale_customer_ranking_message(message)
        or _is_sale_order_list_message(message)
        or _is_purchase_order_list_message(message)
    ):
        return True

    business_terms = {
        "stock",
        "inventory",
        "inventaire",
        "produit",
        "product",
        "prix",
        "price",
        "supplier",
        "fournisseur",
        "customer",
        "client",
        "partner",
        "partenaire",
        "contact",
        "commande client",
        "commandes client",
        "commande fournisseur",
        "commandes fournisseur",
        "analytic",
        "analytique",
        "releve bancaire",
        "releves bancaires",
        "bank statement",
        "bank statements",
        "transaction bancaire",
        "transactions bancaires",
        "ecriture bancaire",
        "ecritures bancaires",
        "journal bancaire",
        "journaux bancaires",
        "bank transaction",
        "bank transactions",
        "accounting transaction",
        "accounting transactions",
    }
    inventory_existence_terms = {
        "available",
        "categorie",
        "category",
        "contient",
        "contiennent",
        "correspond",
        "existe",
        "existent",
        "found",
        "integr",
        "matching",
        "mot cle",
        "present",
        "trouver",
    }
    read_terms = {
        "available",
        "combien",
        "count",
        "donne",
        "detail",
        "details",
        "disponible",
        "how many",
        "integr",
        "liste",
        "lister",
        "montre",
        "quel est",
        "quelle est",
        "quels sont",
        "quelles sont",
        "read",
        "cherche",
        "recherche",
        "search",
        "show",
        "find",
        "total",
        "trouve",
        "trouver",
        "verifie",
        "verifier",
        "vérifie",
        "vérifier",
        "what is available",
        "information",
        "informations",
        "section",
        "partie",
        "qu est ce qu il y a",
        "qu y a t il",
    }

    if "odoo" in text and any(term in text for term in read_terms):
        return True

    if (
        any(term in text for term in {"inventory", "inventaire", "stock", "product", "produit"})
        and any(term in text for term in inventory_existence_terms)
    ):
        return True

    return any(term in text for term in business_terms) and any(
        term in text for term in read_terms
    )


def _odoo_read_route(message: str, error=None):
    text = _normalize_text(message)
    intent = "product_stock_check"
    action = "read_product_stock"
    capability = "odoo.product_stock"
    parameters = {}
    capability_route = (
        None
        if _is_odoo_connection_status_message(message)
        else route_from_business_capability(
            message,
            {"classifier_error": error} if error else {},
        )
    )

    if _is_odoo_connection_status_message(message):
        intent = "odoo_connection_status"
        action = "odoo_status"
        capability = "odoo.connection_status"
        parameters = {}
    elif capability_route:
        return capability_route
    elif _is_purchase_supplier_ranking_message(message):
        intent = "odoo_purchase_supplier_ranking"
        action = "supplier_ranking"
        capability = "odoo.purchase_supplier_ranking"
        parameters = {
            "operation": "aggregate",
            "business_object": "purchase_order_suppliers",
            "model": "purchase.order",
            "model_hint": "purchase.order",
            "group_by": ["partner_id"],
            "aggregate": {"operation": "count", "field": "id", "alias": "record_count"},
            "sort": [{"field": "record_count", "direction": "desc"}],
            "limit": 10,
        }
    elif _is_sale_customer_ranking_message(message):
        intent = "odoo_sale_customer_ranking"
        action = "customer_ranking"
        capability = "odoo.sale_customer_ranking"
        parameters = {
            "operation": "aggregate",
            "business_object": "sale_order_customers",
            "model": "sale.order",
            "model_hint": "sale.order",
            "group_by": ["partner_id"],
            "aggregate": {"operation": "count", "field": "id", "alias": "record_count"},
            "sort": [{"field": "record_count", "direction": "desc"}],
            "limit": 10,
        }
    elif _is_sale_order_list_message(message):
        intent = "odoo_generic_read"
        action = "odoo_generic_read"
        capability = "odoo.generic_read"
        parameters = {
            "operation": "list",
            "business_object": "commandes client",
            "model": "sale.order",
            "model_hint": "sale.order",
            "requested_fields": ["name", "partner_id", "state", "date_order"],
            "limit": 10,
        }
    elif _is_purchase_order_list_message(message):
        intent = "odoo_generic_read"
        action = "odoo_generic_read"
        capability = "odoo.generic_read"
        parameters = {
            "operation": "list",
            "business_object": "bons de commande fournisseur",
            "model": "purchase.order",
            "model_hint": "purchase.order",
            "requested_fields": ["name", "partner_id", "state", "date_order"],
            "limit": 10,
        }
    elif is_odoo_document_request(message):
        intent = odoo_document_intent(message)
        action = "search_document" if is_odoo_document_search_request(message) else "read_document"
        capability = (
            "odoo.document_search"
            if is_odoo_document_search_request(message)
            else "odoo.document_details"
        )
    elif any(term in text for term in BANK_ACCOUNTING_READ_TERMS):
        intent = "odoo_bank_accounting_search"
        action = "bank_accounting_search"
        capability = "odoo.accounting_bank_read"
        parameters = {
            "operation": "search",
            "business_object": "bank_accounting",
            "model": "account.bank.statement",
            "model_hint": "account.bank.statement",
            "limit": 10,
        }
    elif "combien" in text or "how many" in text or "count" in text or "total" in text:
        intent = "inventory_summary"
        action = "inventory_summary"
        capability = "odoo.inventory_summary" if "stock" in text or "produit" in text or "product" in text else "odoo.generic_read"
        parameters = {"operation": "count", "business_object": message, "limit": 10} if capability == "odoo.generic_read" else {}
    elif (
        any(term in text for term in {"inventory", "inventaire", "stock", "product", "produit"})
        and any(
            term in text
            for term in {
                "available",
                "categorie",
                "category",
                "contient",
                "correspond",
                "existe",
                "existent",
                "found",
                "integr",
                "matching",
                "mot cle",
                "present",
                "trouver",
                "contiennent",
            }
        )
    ):
        intent = "inventory_product_lookup"
        action = "inventory_product_search"
        capability = "odoo.product_search"
    elif "odoo" in text:
        intent = "odoo_generic_read"
        action = "odoo_generic_read"
        capability = "odoo.generic_read"
        parameters = {"operation": "list", "business_object": message, "limit": 10}

    return _route(
        intent=intent,
        selected_agent="odoo_agent",
        action=action,
        risk_level="low",
        requires_approval=False,
        confidence="high",
        reason="Backend category policy detected an Odoo read request.",
        source="local_odoo_read_rules",
        error=error,
        capability=capability,
        request_type="enterprise_action",
        domain="odoo",
        execution_mode="tool",
        parameters=parameters,
    )


def _is_bank_accounting_read_message(message: str) -> bool:
    text = _normalize_text(message)
    return any(term in text for term in BANK_ACCOUNTING_READ_TERMS)


def _is_purchase_supplier_ranking_message(message: str) -> bool:
    text = _normalize_text(message)
    has_supplier = any(term in text for term in SUPPLIER_TERMS)
    has_purchase_order = any(term in text for term in PURCHASE_ORDER_TERMS)
    has_ranking = any(term in text for term in SUPPLIER_RANKING_TERMS)
    return has_supplier and has_purchase_order and has_ranking


def _is_sale_customer_ranking_message(message: str) -> bool:
    text = _normalize_text(message)
    has_customer = any(term in text for term in CUSTOMER_TERMS)
    has_sale_order = any(term in text for term in SALE_ORDER_TERMS)
    has_ranking = any(term in text for term in SUPPLIER_RANKING_TERMS)
    return has_customer and has_sale_order and has_ranking


def _is_odoo_connection_status_message(message: str) -> bool:
    text = _normalize_text(message)
    if "odoo" not in text:
        return False

    business_action_signal = any(
        term in text
        for term in {
            "activer",
            "changer",
            "cocher",
            "coche",
            "compte analytique",
            "create",
            "creer",
            "delete",
            "inventaire",
            "modifier",
            "mettre a jour",
            "pointage",
            "price",
            "prix",
            "product",
            "produit",
            "stock",
            "supprimer",
            "update",
            "valider",
        }
    )

    if business_action_signal:
        return False

    return any(
        re.search(pattern, text)
        for pattern in (
            r"\bconnecte(?:e|s|es)?\b",
            r"\bconnexion\b",
            r"\bconnected\b",
            r"\bconnection\b",
            r"\bdisponible\b",
            r"\bstatus\b",
            r"\bstatut\b",
            r"\betat\b",
            r"\bonline\b",
            r"\baccessible\b",
        )
    )


def _is_sale_order_list_message(message: str) -> bool:
    text = _normalize_text(message)
    return any(term in text for term in SALE_ORDER_TERMS) and any(
        term in text for term in ORDER_LIST_TERMS
    )


def _is_purchase_order_list_message(message: str) -> bool:
    text = _normalize_text(message)
    return any(term in text for term in PURCHASE_ORDER_TERMS) and any(
        term in text for term in ORDER_LIST_TERMS
    )


def _is_project_orchestrator_explanation_message(message: str) -> bool:
    text = _normalize_text(message)
    has_orchestrator_subject = any(
        term in text for term in {"orchestrateur", "orchestrator", "orchestrateur ia"}
    )
    has_explanation_intent = any(
        term in text
        for term in {
            "role",
            "rôle",
            "sert",
            "fait",
            "fonctionne",
            "explique",
            "c est quoi",
            "c'est quoi",
            "what is",
            "what can",
            "capabilite",
            "capacite",
            "capability",
        }
    )
    return has_orchestrator_subject and has_explanation_intent


def _orchestrator_help_route(
    message: str,
    source: str = "system_help_router",
    error=None,
) -> dict:
    return _route(
        intent="orchestrator_help",
        selected_agent="knowledge_agent",
        action="orchestrator_help",
        risk_level="low",
        requires_approval=False,
        confidence="high",
        reason="System help question about the orchestrator application.",
        source=source,
        error=error,
        capability="knowledge.general_answer",
        request_type="general_knowledge",
        domain="knowledge",
        execution_mode="system_help",
        parameters={"help_topic": message},
    )


def _knowledge_intent_for(message: str) -> str:
    text = _normalize_text(message)

    if "documentation" in text or "document" in text and "resume" in text:
        if "serveur" in text or "server" in text:
            return "summarize_server_documentation"
        return "summarize_documentation"

    if "validation" in text or "approval" in text or "approbation" in text:
        return "explain_human_approval_benefits"

    if "orchestrateur" in text or "orchestrator" in text:
        return "explain_orchestrator"

    return "general_information_question"


def _canonical_intent(intent: str | None) -> str:
    intent = str(intent or "general")
    return INTENT_ALIASES.get(intent, intent)


def _route_values(route: dict) -> dict:
    values = {}

    for key in ("entities", "parameters"):
        source = route.get(key)

        if isinstance(source, dict):
            values.update(source)

    semantic_request = route.get("semantic_request")

    if isinstance(semantic_request, dict):
        for key in ("entities", "parameters"):
            source = semantic_request.get(key)

            if isinstance(source, dict):
                values.update(source)

        if semantic_request.get("topic") and not values.get("topic"):
            values["topic"] = semantic_request.get("topic")

    if route.get("topic") and not values.get("topic"):
        values["topic"] = route.get("topic")

    return values


def _route_text_signals(route: dict) -> set[str]:
    values = _route_values(route)
    signals = set()

    for key in (
        "knowledge_topic",
        "metric",
        "operation",
        "requested_fields",
        "server_target",
        "target",
        "topic",
    ):
        value = values.get(key)

        if isinstance(value, str):
            signals.update(
                part.strip().lower()
                for part in value.replace("_", " ").replace("-", " ").split()
            )

    return {signal for signal in signals if signal}


def _knowledge_route_requires_retrieval(route: dict) -> bool:
    if route.get("request_type") == "enterprise_knowledge":
        return True

    if route.get("execution_mode") == "retrieval_grounded":
        return True

    semantic_request = route.get("semantic_request")

    if isinstance(semantic_request, dict) and semantic_request.get("requires_internal_context"):
        return True

    return bool(_route_text_signals(route) & KNOWLEDGE_RETRIEVAL_SIGNALS)


def _is_general_direct_llm_route(route: dict) -> bool:
    selected_agent = route.get("selected_agent") or route.get("agent")
    domain = route.get("domain") or route.get("target_system")
    capability = route.get("capability")
    request_type = route.get("request_type")
    action = str(route.get("action") or "").strip().lower()
    intent = str(route.get("intent") or "").strip().lower()

    if capability not in {None, "", "general", "knowledge"}:
        return False

    if selected_agent not in {None, "", "general_agent", "knowledge_agent"}:
        return False

    if domain not in {None, "", "general", "knowledge"}:
        return False

    if request_type in {
        "conversational",
        "creative_generation",
        "general_knowledge",
        "writing_assistance",
    }:
        return True

    if request_type == "enterprise_action":
        return False

    return intent in {"general", "knowledge"} and action in {
        "",
        "answer_question",
        "answer",
    }


def _documentation_summary_intent(route: dict) -> str | None:
    values = _route_values(route)
    operation = str(values.get("operation") or "").strip().lower()
    signals = _route_text_signals(route)
    has_summary_operation = operation in SERVER_DOCUMENTATION_OPERATIONS or bool(
        signals & SERVER_DOCUMENTATION_OPERATIONS
    )
    has_documentation_scope = bool(
        signals
        & {
            "documentation",
            "document",
            "manual",
            "manuel",
            "guide",
        }
    )

    if not has_summary_operation or not has_documentation_scope:
        return None

    if signals & {"server", "serveur", "serveurs"}:
        return "summarize_server_documentation"

    return "summarize_documentation"


def _registered_server_capability_for_route(route: dict) -> str | None:
    for signal in sorted(_route_text_signals(route)):
        capability = SERVER_SIGNAL_CAPABILITIES.get(signal)

        if not capability:
            continue

        metadata = get_capability_metadata(capability)

        if metadata and metadata.get("domain") == "server":
            return capability

    return None


def _apply_server_capability(route: dict, capability: str) -> dict:
    metadata = get_capability_metadata(capability) or {}
    intent, action = SERVER_CAPABILITY_ACTIONS.get(
        capability,
        ("server_health_check", capability),
    )
    normalized = dict(route)
    normalized["intent"] = intent
    normalized["request_type"] = normalized.get("request_type") or "enterprise_action"
    normalized["domain"] = "server"
    normalized["target_system"] = "server"
    normalized["agent"] = "server_agent"
    normalized["selected_agent"] = "server_agent"
    normalized["capability"] = capability
    normalized["execution_mode"] = metadata.get("execution_mode", "tool")
    normalized["action"] = action
    normalized["risk_level"] = metadata.get("risk_level", "low")
    normalized["risk"] = normalized["risk_level"]
    normalized["requires_approval"] = bool(metadata.get("requires_approval"))
    normalized["approval_required"] = normalized["requires_approval"]
    normalized["clarification_needed"] = False
    normalized["missing_parameters"] = []
    return normalized


def _apply_knowledge_capability(route: dict, capability: str) -> dict:
    metadata = get_capability_metadata(capability) or {}
    normalized = dict(route)
    current_intent = _canonical_intent(normalized.get("intent"))
    documentation_intent = _documentation_summary_intent(normalized)

    if documentation_intent:
        normalized["intent"] = documentation_intent
    elif current_intent not in {"general", "knowledge"}:
        normalized["intent"] = current_intent
    else:
        normalized["intent"] = "general_information_question"
    normalized["request_type"] = (
        "enterprise_knowledge"
        if capability == "knowledge.enterprise_answer"
        else normalized.get("request_type") or "general_knowledge"
    )
    normalized["domain"] = "knowledge"
    normalized["target_system"] = "knowledge"
    normalized["agent"] = "knowledge_agent"
    normalized["selected_agent"] = "knowledge_agent"
    normalized["capability"] = capability
    normalized["execution_mode"] = metadata.get(
        "execution_mode",
        "retrieval_grounded" if capability == "knowledge.enterprise_answer" else "llm_direct",
    )
    normalized["action"] = (
        "enterprise_answer"
        if capability == "knowledge.enterprise_answer"
        else "answer_question"
    )
    normalized["risk_level"] = metadata.get("risk_level", "low")
    normalized["risk"] = normalized["risk_level"]
    normalized["requires_approval"] = False
    normalized["approval_required"] = False
    return normalized


def normalize_semantic_boundaries(route: dict) -> dict:
    normalized = dict(route)
    normalized["intent"] = _canonical_intent(normalized.get("intent"))
    domain = normalized.get("domain") or normalized.get("target_system")
    capability = normalized.get("capability")
    operation = str(_route_values(normalized).get("operation") or "").strip().lower()
    documentation_intent = _documentation_summary_intent(normalized)

    if domain == "server" and documentation_intent:
        return _apply_knowledge_capability(normalized, "knowledge.general_answer")

    if _is_project_orchestrator_explanation_message(
        str(
            _route_values(normalized).get("knowledge_topic")
            or _route_values(normalized).get("topic")
            or normalized.get("message")
            or normalized.get("user_message")
            or ""
        )
    ) or (
        normalized.get("selected_agent") == "knowledge_agent"
        and _is_project_orchestrator_explanation_message(
            str(_route_values(normalized).get("topic") or normalized.get("intent") or "")
        )
    ):
        return _apply_knowledge_capability(normalized, "knowledge.general_answer")

    if _is_general_direct_llm_route(normalized):
        return _apply_knowledge_capability(normalized, "knowledge.general_answer")

    if (
        normalized.get("selected_agent") == "knowledge_agent"
        or domain == "knowledge"
        or capability in {"knowledge.general_answer", "knowledge.enterprise_answer"}
    ):
        if _knowledge_route_requires_retrieval(normalized):
            return _apply_knowledge_capability(normalized, "knowledge.enterprise_answer")

        if capability == "knowledge.enterprise_answer":
            return _apply_knowledge_capability(normalized, "knowledge.enterprise_answer")

        if capability in {None, "", "knowledge", "knowledge.general_answer"}:
            return _apply_knowledge_capability(normalized, "knowledge.general_answer")

    if domain == "server" and capability in {None, "", "server"}:
        if normalized.get("request_type") in {"enterprise_knowledge", "general_knowledge"}:
            knowledge_capability = (
                "knowledge.enterprise_answer"
                if normalized.get("request_type") == "enterprise_knowledge"
                else "knowledge.general_answer"
            )
            return _apply_knowledge_capability(normalized, knowledge_capability)

        if operation in SERVER_DOCUMENTATION_OPERATIONS:
            return _apply_knowledge_capability(normalized, "knowledge.general_answer")

        action_value = str(normalized.get("action") or "").strip().lower()
        server_capability = (
            SERVER_ACTION_CAPABILITIES.get(action_value)
            or _registered_server_capability_for_route(normalized)
        )

        if server_capability:
            return _apply_server_capability(normalized, server_capability)

        if operation in SERVER_DIAGNOSTIC_OPERATIONS:
            return _apply_server_capability(normalized, "server.local_health")

        normalized["intent"] = "unsupported_capability"
        normalized["action"] = "unsupported_capability"
        normalized["capability_validation_error"] = "Capability is not registered: server"
        normalized.setdefault("risk_level", "low")
        normalized["risk"] = normalized["risk_level"]
        normalized["requires_approval"] = False
        normalized["approval_required"] = False

    if domain == "server" and capability:
        metadata = get_capability_metadata(str(capability))

        if metadata and metadata.get("domain") == "server":
            return _apply_server_capability(normalized, str(capability))

    return normalized


def _is_odoo_write_route(route: dict) -> bool:
    selected_agent = route.get("selected_agent") or route.get("agent")
    target_system = route.get("target_system")
    action = str(route.get("action") or "").lower()

    if selected_agent != "odoo_agent" and target_system != "odoo":
        return False

    if any(write_action in action for write_action in ODOO_WRITE_ACTIONS):
        return True

    if route.get("requires_approval") is True:
        return True

    return False


def apply_backend_safety_overrides(message: str, route: dict | None = None) -> dict | None:
    if _is_secret_or_sensitive_path_request(message):
        return _blocked_security_route(
            "sensitive_secret_request",
            "Request asks for secrets or sensitive environment data.",
        )

    if _is_destructive_or_dangerous_request(message):
        return _blocked_security_route(
            "destructive_operation_blocked",
            "Request asks for a destructive or dangerous operation.",
        )

    if is_orchestrator_help_question(message):
        return _orchestrator_help_route(message)

    capability_route = (
        route_from_business_capability(message, route)
        if isinstance(route, dict)
        else None
    )

    if capability_route:
        return capability_route

    if _is_bank_accounting_read_message(message):
        return enrich_route_with_capability_contract(message, _odoo_read_route(message))

    if _is_odoo_connection_status_message(message):
        return enrich_route_with_capability_contract(message, _odoo_read_route(message))

    if _is_purchase_supplier_ranking_message(message):
        return enrich_route_with_capability_contract(message, _odoo_read_route(message))

    if _is_sale_customer_ranking_message(message):
        return enrich_route_with_capability_contract(message, _odoo_read_route(message))

    if _is_sale_order_list_message(message) or _is_purchase_order_list_message(message):
        return enrich_route_with_capability_contract(message, _odoo_read_route(message))

    if is_odoo_document_request(message):
        return enrich_route_with_capability_contract(message, _odoo_read_route(message))

    if _is_unsupported_server_resource_request(message):
        return _route(
            intent="unsupported_capability",
            selected_agent="server_agent",
            action="unsupported_capability",
            risk_level="low",
            requires_approval=False,
            confidence="high",
            reason=(
                "Request targets server-side resources, but no registered safe "
                "server resource management capability exists."
            ),
            source="backend_safety_override",
            capability="unsupported_capability",
            request_type="enterprise_action",
            domain="server",
            execution_mode=None,
            parameters={},
            capability_validation_error=(
                "No registered safe server resource management capability exists."
            ),
        )

    specific_server = extract_specific_server_reference(message)

    if specific_server:
        return _route(
            intent="external_server_diagnostic",
            selected_agent="server_agent",
            action="unsupported_external_server",
            risk_level="low",
            requires_approval=False,
            confidence="high",
            reason="Request names a specific server that is not in the safe diagnostic registry.",
            source="backend_safety_override",
            entities={"server": specific_server},
        )

    if is_vague_server_problem(message):
        return _route(
            intent="server_issue_clarification",
            selected_agent="server_agent",
            action="clarify_server_issue",
            risk_level="low",
            requires_approval=False,
            confidence="high",
            reason="Request mentions a server problem without enough diagnostic detail.",
            source="backend_safety_override",
        )

    if not isinstance(route, dict):
        return route

    selected_agent = route.get("selected_agent") or route.get("agent")
    route_domain = route.get("domain") or route.get("target_system")
    message_server_capability = _server_diagnostic_capability_from_message(message)

    if (
        message_server_capability
        and (route_domain == "server" or selected_agent == "server_agent")
    ):
        return enrich_route_with_capability_contract(
            message,
            _apply_server_capability(route, message_server_capability),
        )

    normalized_route = normalize_semantic_boundaries(route)
    selected_agent = normalized_route.get("selected_agent") or normalized_route.get("agent")
    normalized_route["selected_agent"] = selected_agent or "general_agent"
    normalized_route["agent"] = normalized_route["selected_agent"]
    normalized_route["target_system"] = (
        normalized_route.get("target_system")
        or AGENT_TARGET_MAP.get(normalized_route["selected_agent"])
        or INTENT_TARGET_MAP.get(normalized_route.get("intent"))
        or "general"
    )

    normalized_route = enrich_route_with_capability_contract(message, normalized_route)

    if _is_odoo_write_route(normalized_route):
        normalized_route["requires_approval"] = True
        normalized_route["approval_required"] = True
        normalized_route["risk_level"] = (
            "high"
            if normalized_route.get("risk_level") in {None, "low", "blocked"}
            else normalized_route.get("risk_level")
        )
        normalized_route["risk"] = normalized_route["risk_level"]
        normalized_route["reason"] = (
            "Backend policy requires approval for Odoo write operations."
        )

    return normalized_route


def _agent_from_intent(intent: str) -> str:
    if intent == "odoo" or intent.startswith("odoo_"):
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


def _format_result(result: dict, source: str, error=None):
    intent = result.get("intent", "general")
    selected_agent = result.get("selected_agent") or result.get("agent") or _agent_from_intent(intent)
    risk_level = result.get("risk_level") or result.get("risk") or "low"
    requires_approval = bool(result.get("requires_approval", False))

    return {
        "intent": intent,
        "agent": selected_agent,
        "selected_agent": selected_agent,
        "action": result.get("action") or "answer_question",
        "target_system": result.get("target_system") or AGENT_TARGET_MAP.get(selected_agent, "general"),
        "risk_level": risk_level,
        "risk": risk_level,
        "confidence": _confidence_label(result.get("confidence", 0.7)),
        "requires_approval": requires_approval,
        "approval_required": requires_approval,
        "entities": result.get("entities") if isinstance(result.get("entities"), dict) else {},
        "reason": result.get("reason") or f"{source} selected this route.",
        "classifier_source": source,
        "classifier_error": error,
    }


def _classify_with_optional_provider(message: str):
    provider = (os.getenv("LLM_ROUTER_PROVIDER") or "openai").strip().lower()

    if provider == "deepseek" and os.getenv("ENABLE_DEEPSEEK", "").lower() == "true":
        try:
            from models.deepseek_classifier import classify_with_deepseek

            deepseek_result = classify_with_deepseek(message)

            if deepseek_result.get("classifier_source") == "deepseek":
                return _format_result(deepseek_result, "deepseek")

        except Exception as error:
            return None

    if provider == "gemini" and os.getenv("ENABLE_GEMINI", "").lower() == "true":
        try:
            from models.gemini_classifier import classify_intent as classify_with_gemini

            gemini_result = classify_with_gemini(message)

            if gemini_result.get("classifier_source") == "gemini":
                return _format_result(gemini_result, "gemini")

        except Exception as error:
            return None

    return None


def _deterministic_fallback(message: str, error=None):
    text = _normalize_text(message)

    if is_orchestrator_help_question(message):
        return _orchestrator_help_route(
            message,
            source="local_knowledge_fallback",
            error=error,
        )

    if _is_odoo_access_issue(message):
        return _route(
            intent="odoo_access_issue",
            selected_agent="support_agent",
            action="troubleshoot_access",
            risk_level="low",
            requires_approval=False,
            confidence="high",
            reason="Odoo access/login wording is an IT support issue.",
            error=error,
        )

    capability_route = route_from_business_capability(
        message,
        {"classifier_error": error} if error else {},
    )

    if capability_route:
        return capability_route

    if _is_odoo_write_request(message):
        return _route(
            intent="odoo_write_request",
            selected_agent="odoo_agent",
            action="update_odoo_record",
            risk_level="high",
            requires_approval=True,
            confidence="medium",
            reason="Local policy detected an Odoo write-like request.",
            source="local_odoo_write_rules",
            error=error,
        )

    if is_odoo_document_request(message):
        return _odoo_read_route(message, error=error)

    if _is_odoo_read_request(message):
        return _odoo_read_route(message, error=error)

    if any(term in text for term in SUPPORT_ISSUE_TERMS):
        return _route(
            intent="wifi_issue" if "wifi" in text or "wi-fi" in text else "support",
            selected_agent="support_agent",
            action="troubleshoot_network" if "wifi" in text or "wi-fi" in text else "troubleshoot_issue",
            risk_level="low",
            requires_approval=False,
            confidence="high",
            reason="Local support fallback matched an IT support issue.",
            error=error,
        )

    has_server_context = any(term in text for term in SERVER_CONTEXT_TERMS)
    has_server_metric = any(term in text for term in SERVER_METRIC_TERMS)
    has_server_diagnostic = any(term in text for term in SERVER_DIAGNOSTIC_TERMS)

    if has_server_metric or has_server_context and has_server_diagnostic:
        action = "check_server_health"

        if "ram" in text or "memoire" in text or "memory" in text:
            action = "check_ram_usage"
        elif "cpu" in text:
            action = "check_cpu_usage"
        elif "disk" in text or "disque" in text or "espace disque" in text:
            action = "check_disk_usage"
        elif "backend" in text or "frontend" in text or "service" in text:
            action = "check_service_status"
        elif "diagnostic" in text and ("server" in text or "serveur" in text):
            action = "server_diagnostic_summary"

        return _route(
            intent={
                "check_ram_usage": "server_ram_usage",
                "check_cpu_usage": "server_cpu_usage",
                "check_disk_usage": "server_disk_usage",
                "check_service_status": "server_service_status",
                "server_diagnostic_summary": "server_diagnostic_summary",
            }.get(action, "server_health_check"),
            selected_agent="server_agent",
            action=action,
            risk_level="low",
            requires_approval=False,
            confidence="high",
            reason="Local server fallback matched an infrastructure diagnostic.",
            error=error,
        )

    if is_general_information_question(message):
        internal_knowledge = (
            is_internal_knowledge_question(message)
            and not _is_project_orchestrator_explanation_message(message)
        )
        return _route(
            intent=_knowledge_intent_for(message),
            selected_agent="knowledge_agent",
            action="enterprise_answer" if internal_knowledge else "answer_question",
            risk_level="low",
            requires_approval=False,
            confidence="high",
            reason="Local knowledge fallback matched a general information question.",
            error=error,
            capability=(
                "knowledge.enterprise_answer"
                if internal_knowledge
                else "knowledge.general_answer"
            ),
            request_type=(
                "enterprise_knowledge"
                if internal_knowledge
                else "general_knowledge"
            ),
            domain="knowledge",
            execution_mode=(
                "retrieval_grounded"
                if internal_knowledge
                else "llm_direct"
            ),
            parameters={"knowledge_topic": message} if internal_knowledge else None,
        )

    if "documentation" in text and ("resume" in text or "résume" in text):
        return _route(
            intent=_knowledge_intent_for(message),
            selected_agent="knowledge_agent",
            action="answer_question",
            risk_level="low",
            requires_approval=False,
            confidence="high",
            reason="Local knowledge fallback matched a documentation summary request.",
            error=error,
            capability="knowledge.general_answer",
            request_type="general_knowledge",
            domain="knowledge",
            execution_mode="llm_direct",
        )

    if any(term in text for term in DEVELOPMENT_HELP_TERMS):
        return _route(
            intent="development_help",
            selected_agent="development_agent",
            action="developer_guidance",
            risk_level="low",
            requires_approval=False,
            confidence="medium",
            reason="Local development fallback matched a developer question.",
            error=error,
        )

    fallback = classify_with_confidence(message)
    intent = fallback["intent"]
    selected_agent = _agent_from_intent(intent)

    action = "answer_question"
    if intent == "odoo":
        action = "read_odoo"

    return _route(
        intent=intent,
        selected_agent=selected_agent,
        action=action,
        risk_level="low",
        requires_approval=fallback.get("requires_approval", False),
        confidence=fallback["confidence"],
        reason="OpenAI router unavailable; deterministic fallback selected this route.",
        error=error,
    )


def classify_message(
    message: str,
    context_memory: dict | None = None,
    user_permissions: dict | None = None,
):
    blocked_override = apply_backend_safety_overrides(message)

    if blocked_override:
        return blocked_override

    if is_orchestrator_help_question(message):
        return apply_backend_safety_overrides(
            message,
            _orchestrator_help_route(message),
        )

    safe_general_route = _cheap_safe_general_route(message)

    if safe_general_route:
        return apply_backend_safety_overrides(message, safe_general_route)

    optional_provider_route = _classify_with_optional_provider(message)

    if optional_provider_route:
        return apply_backend_safety_overrides(message, optional_provider_route)

    openai_route = classify_with_openai_router(
        message,
        context_memory=context_memory,
        user_permissions=user_permissions,
    )

    if openai_route:
        return apply_backend_safety_overrides(message, openai_route)

    fallback = _deterministic_fallback(
        message,
        error="openai_router_unavailable",
    )
    return apply_backend_safety_overrides(message, fallback)
