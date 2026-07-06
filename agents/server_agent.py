import re
import unicodedata

from integrations.internal_server_connector import InternalServerConnector


connector = InternalServerConnector()

UNCONFIGURED_SERVER_MESSAGE = (
    "Je comprends que la demande concerne {server_name}, mais ce serveur n’est pas "
    "encore connecté à un outil de diagnostic sécurisé. Pour le moment, je peux "
    "uniquement vérifier le serveur local de l’orchestrateur en mode démonstration."
)

SERVER_CLARIFICATION_MESSAGE = (
    "Pouvez-vous préciser le problème rencontré : accès, lenteur, RAM, disque, "
    "service arrêté ou réseau ?"
)


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


def _is_internal_storage_request(text: str) -> bool:
    return any(
        term in text
        for term in [
            "serveur interne",
            "fichier serveur",
            "stockage interne",
            "internal server",
            "server file",
            "internal file",
        ]
    )


def _extract_specific_server_reference(message: str):
    text = _normalize_text(message)

    if _is_internal_storage_request(text):
        return None

    local_server_terms = [
        "serveur local",
        "local server",
        "serveur local de l'orchestrateur",
        "orchestrateur",
        "orchestrator",
        "local_orchestrator",
    ]

    if any(term in text for term in local_server_terms):
        return None

    patterns = [
        r"\b(?P<server>(?:serveur|server)\s+\d+)\b",
        r"\b(?P<server>(?:serveur|server)\s+odoo)\b",
        r"\b(?P<server>(?:serveur|server)\s+base\s+de\s+donn[ée]es)\b",
        r"\b(?P<server>(?:serveur|server)\s+(?:database|db))\b",
        r"\b(?P<server>(?:serveur|server)\s+fichiers?)\b",
        r"\b(?P<server>(?:serveur|server)\s+files?)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, message or "", re.IGNORECASE)

        if match:
            return " ".join(match.group("server").split())

    return None


def extract_specific_server_reference(message: str):
    return _extract_specific_server_reference(message)


def _is_vague_server_problem(message: str):
    text = _normalize_text(message)

    if _is_internal_storage_request(text):
        return False

    if _extract_specific_server_reference(message):
        return False

    has_server = "serveur" in text or "server" in text
    has_problem = any(
        term in text
        for term in [
            "probleme",
            "problem",
            "incident",
            "panne",
            "ne marche pas",
            "not working",
        ]
    )
    has_diagnostic_detail = any(
        term in text
        for term in [
            "ram",
            "memoire",
            "memory",
            "cpu",
            "disque",
            "disk",
            "espace disque",
            "service",
            "services",
            "reseau",
            "network",
            "uptime",
            "etat",
            "status",
            "diagnostic",
        ]
    )

    return has_server and has_problem and not has_diagnostic_detail


def is_vague_server_problem(message: str):
    return _is_vague_server_problem(message)


def _unconfigured_server_result(server_name: str):
    return {
        "success": False,
        "action": "unsupported_external_server",
        "server": server_name,
        "configured": False,
        "message": UNCONFIGURED_SERVER_MESSAGE.format(server_name=server_name),
    }


def _server_clarification_result():
    return {
        "success": False,
        "action": "clarify_server_issue",
        "needs_clarification": True,
        "message": SERVER_CLARIFICATION_MESSAGE,
    }


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

    return (
        bool(_extract_specific_server_reference(message))
        or _is_vague_server_problem(message)
        or any(
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

    specific_server = _extract_specific_server_reference(message)

    if specific_server:
        server_id, _server_config = connector.resolve_server_reference(specific_server)

        if server_id != "local_orchestrator":
            return _response(
                "unsupported_external_server",
                "none",
                _unconfigured_server_result(specific_server),
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

    if _is_vague_server_problem(message):
        return _response(
            "clarify_server_issue",
            "none",
            _server_clarification_result(),
            status="needs_clarification",
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
