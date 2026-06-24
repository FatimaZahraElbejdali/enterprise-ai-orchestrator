import re
import unicodedata

from integrations.internal_server_connector import InternalServerConnector


connector = InternalServerConnector()


def _response(action: str, tool_used: str, result: dict | str, status: str = "completed"):
    return {
        "intent": "server",
        "agent": "server_agent",
        "parser_source": "server_fallback",
        "parsed_action": action,
        "requires_approval": False,
        "approval_required": False,
        "status": status,
        "tool_used": tool_used,
        "result": result,
        "message": result.get("message") if isinstance(result, dict) else str(result),
        "data": result,
    }


def _normalize_text(message: str) -> str:
    normalized = unicodedata.normalize("NFKD", message or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().replace("’", "'").split())


def _has_word(text: str, *words: str) -> bool:
    return any(
        re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE)
        for word in words
    )


def _blocked_security_result(message: str):
    return {
        "success": False,
        "action": "blocked_sensitive_path",
        "blocked": True,
        "message": (
            "Demande refusée: l’orchestrateur ne peut pas afficher de secrets, "
            "variables d’environnement, clés SSH, mots de passe ou chemins système sensibles."
        ),
    }


def _is_sensitive_request(message: str) -> bool:
    text = _normalize_text(message)

    sensitive_terms = [
        ".env",
        "/etc/passwd",
        "api key",
        "api keys",
        "cle api",
        "cles api",
        "ssh key",
        "ssh keys",
        "cle ssh",
        "cles ssh",
        "private key",
        "environment variable",
        "environment variables",
        "variables d'environnement",
        "variables denvironnement",
        "variable d'environnement",
        "variable denvironnement",
        "mot de passe du serveur",
        "mots de passe",
        "password",
        "passwords",
        "rm -rf",
    ]

    return any(term in text for term in sensitive_terms) or any(
        token in text
        for token in ["..", "/etc", "\\"]
    )


def _extract_create_request(message: str):
    patterns = [
        r"nomm[ée]\s+([^\s]+)\s+avec\s+le\s+contenu\s*:?\s*(.+)$",
        r"named\s+([^\s]+)\s+with\s+(?:the\s+)?content\s*:?\s*(.+)$",
        r"file\s+([^\s]+)\s+content\s*:?\s*(.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)

        if match:
            return match.group(1).strip(), match.group(2).strip()

    return None, None


def _extract_read_filename(message: str):
    patterns = [
        r"\b(?:lis|lire|read)\b\s+(?:le\s+)?(?:fichier|file|document|documentation)\s+(?:serveur\s+|interne\s+)?([^\s]+)",
        r"server\s+file\s+([^\s]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)

        if match:
            return match.group(1).strip()

    return ""


def _is_read_file_request(message: str) -> bool:
    text = _normalize_text(message)

    return bool(_extract_read_filename(message)) or (
        _has_word(text, "lis", "lire", "read")
        and any(term in text for term in ["fichier", "file", "document", "documentation"])
    )


def _is_create_file_request(message: str) -> bool:
    text = _normalize_text(message)

    return _has_word(text, "cree", "create") and any(
        term in text
        for term in ["fichier", "file", "document", "note"]
    )


def _is_list_file_request(message: str) -> bool:
    text = _normalize_text(message)

    return _has_word(text, "liste", "lister", "list") and any(
        term in text
        for term in ["fichiers", "files", "stockage interne", "server files"]
    )


def _select_diagnostic_action(message: str):
    text = _normalize_text(message)

    if any(term in text for term in ["diagnostic serveur", "diagnostic server", "fais un diagnostic"]):
        return "server_diagnostic_summary"

    if any(term in text for term in ["backend", "frontend", "service", "services"]):
        return "check_service_status"

    if any(term in text for term in ["ram", "memoire", "memory"]):
        return "check_ram_usage"

    if any(term in text for term in ["cpu", "processeur", "processor"]):
        return "check_cpu_usage"

    if any(term in text for term in ["disque", "disk", "espace disque", "storage"]):
        return "check_disk_usage"

    if any(
        term in text
        for term in [
            "etat des serveurs",
            "etat du serveur",
            "server status",
            "server health",
            "serveur actif",
            "serveur est-il actif",
            "uptime",
            "statut",
            "status",
        ]
    ):
        return "check_server_status"

    if "serveur" in text or "server" in text:
        return "check_server_status"

    return None


def is_server_request(message: str):
    text = _normalize_text(message)

    return any(
        phrase in text
        for phrase in [
            "serveur interne",
            "fichier serveur",
            "stockage interne",
            "internal server",
            "server file",
            "internal file",
            "liste les fichiers",
            "list files",
            "crée un fichier",
            "cree un fichier",
            "create file",
            "lis le fichier",
            "read file",
            "ram",
            "cpu",
            "disque",
            "disk",
            "uptime",
            "backend",
            "frontend",
            "diagnostic serveur",
        ]
    )


def run(message: str):
    text = _normalize_text(message)

    if _is_sensitive_request(message):
        return _response(
            "blocked_sensitive_path",
            "internal_server_block_path",
            _blocked_security_result(message),
            status="blocked",
        )

    if _has_word(text, "supprime", "supprimer", "delete", "remove"):
        return _response(
            "unknown",
            "none",
            {
                "success": False,
                "message": "Suppression non supportée dans la démonstration. Aucune action exécutée.",
            },
            status="unsupported",
        )

    if _is_list_file_request(message):
        return _response(
            "list_internal_files",
            "internal_server_list_files",
            connector.list_files(),
        )

    if _is_create_file_request(message):
        filename, content = _extract_create_request(message)

        if not filename:
            return _response(
                "create_internal_file",
                "internal_server_create_file",
                {
                    "success": False,
                    "message": "Veuillez préciser le nom du fichier et son contenu.",
                },
                status="needs_clarification",
            )

        return _response(
            "create_internal_file",
            "internal_server_create_file",
            connector.store_text_file(filename, content or ""),
        )

    if _is_read_file_request(message):
        filename = _extract_read_filename(message)

        if not filename:
            return _response(
                "read_internal_file",
                "internal_server_read_file",
                {
                    "success": False,
                    "message": "Veuillez préciser le nom du fichier à lire.",
                },
                status="needs_clarification",
            )

        result = connector.read_text_file(filename)
        return _response(
            result.get("action", "read_internal_file"),
            "internal_server_read_file",
            result,
            status="blocked" if result.get("blocked") else "completed",
        )

    diagnostic_action = _select_diagnostic_action(message)

    if diagnostic_action == "check_ram_usage":
        return _response(
            "check_ram_usage",
            "check_ram_usage",
            connector.check_ram_usage(),
        )

    if diagnostic_action == "check_cpu_usage":
        return _response(
            "check_cpu_usage",
            "check_cpu_usage",
            connector.check_cpu_usage(),
        )

    if diagnostic_action == "check_disk_usage":
        return _response(
            "check_disk_usage",
            "check_disk_usage",
            connector.check_disk_usage(),
        )

    if diagnostic_action == "check_service_status":
        return _response(
            "check_service_status",
            "check_service_status",
            connector.check_service_status(),
        )

    if diagnostic_action == "server_diagnostic_summary":
        return _response(
            "server_diagnostic_summary",
            "server_diagnostic_summary",
            connector.server_diagnostic_summary(),
        )

    if diagnostic_action == "check_server_status":
        return _response(
            "check_server_status",
            "check_server_status",
            connector.check_server_status(),
        )

    return _response(
        "unknown",
        "none",
        "Server Agent received the request but no supported server action matched.",
        status="unsupported",
    )
