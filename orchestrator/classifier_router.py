import os
import re
import unicodedata

from dotenv import load_dotenv

from agents.knowledge_agent import is_general_information_question
from agents.server_agent import (
    extract_specific_server_reference,
    is_vague_server_problem,
)
from models.openai_router import classify_with_openai_router
from orchestrator.intent_classifier import classify_with_confidence

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
):
    target_system = AGENT_TARGET_MAP.get(selected_agent, "general")

    return {
        "intent": intent,
        "agent": selected_agent,
        "selected_agent": selected_agent,
        "action": action,
        "target_system": target_system,
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
        ]
    )

    return has_write and has_odoo_object


def _is_odoo_read_request(message: str) -> bool:
    text = _normalize_text(message)

    if is_odoo_document_request(message):
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
        "analytic",
        "analytique",
    }
    inventory_existence_terms = {
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
    }
    read_terms = {
        "available",
        "combien",
        "count",
        "detail",
        "details",
        "disponible",
        "how many",
        "integr",
        "liste",
        "lister",
        "montre",
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
    }

    if (
        any(term in text for term in {"odoo", "inventory", "inventaire", "stock"})
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

    if is_odoo_document_request(message):
        intent = odoo_document_intent(message)
        action = "search_document" if is_odoo_document_search_request(message) else "read_document"
    elif "combien" in text or "how many" in text or "count" in text or "total" in text:
        intent = "inventory_summary"
        action = "inventory_summary"
    elif (
        any(term in text for term in {"odoo", "inventory", "inventaire", "stock"})
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
            }
        )
    ):
        intent = "inventory_product_lookup"
        action = "inventory_product_search"

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

    normalized_route = dict(route)
    normalized_route["intent"] = _canonical_intent(normalized_route.get("intent"))
    selected_agent = normalized_route.get("selected_agent") or normalized_route.get("agent")
    normalized_route["selected_agent"] = selected_agent or "general_agent"
    normalized_route["agent"] = normalized_route["selected_agent"]
    normalized_route["target_system"] = (
        normalized_route.get("target_system")
        or AGENT_TARGET_MAP.get(normalized_route["selected_agent"])
        or INTENT_TARGET_MAP.get(normalized_route.get("intent"))
        or "general"
    )

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

    if is_odoo_document_request(message):
        return _odoo_read_route(message, error=error)

    if _is_odoo_read_request(message):
        return _odoo_read_route(message, error=error)

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
        return _route(
            intent=_knowledge_intent_for(message),
            selected_agent="knowledge_agent",
            action="answer_question",
            risk_level="low",
            requires_approval=False,
            confidence="high",
            reason="Local knowledge fallback matched a general information question.",
            error=error,
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
