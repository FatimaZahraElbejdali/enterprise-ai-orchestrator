import re

from integrations.internal_server_connector import InternalServerConnector


connector = InternalServerConnector()


def check_server_health(message: str):
    return {
        "task": "server_health_check",
        "cpu_usage": "34%",
        "ram_usage": "61%",
        "disk_usage": "72%",
        "status": "healthy",
    }


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
    }


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
        r"(?:lis|lire|read)\s+(?:le\s+)?(?:fichier\s+)?(?:serveur\s+)?([^\s]+)",
        r"server\s+file\s+([^\s]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)

        if match:
            return match.group(1).strip()

    return ""


def is_server_request(message: str):
    text = message.lower()

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
        ]
    )


def run(message: str):
    text = message.lower()

    if "/etc" in text or ".env" in text or ".." in text:
        filename = _extract_read_filename(message) or message
        result = connector.read_text_file(filename)
        return _response(
            "blocked_sensitive_path",
            "internal_server_block_path",
            result,
            status="blocked",
        )

    if "supprime" in text or "delete" in text or "remove" in text:
        return _response(
            "unknown",
            "none",
            {
                "success": False,
                "message": "Suppression non supportée dans la démonstration. Aucune action exécutée.",
            },
            status="unsupported",
        )

    if any(phrase in text for phrase in ["liste", "list"]) and any(
        phrase in text for phrase in ["fichiers", "files", "serveur", "server"]
    ):
        return _response(
            "list_internal_files",
            "internal_server_list_files",
            connector.list_files(),
        )

    if any(phrase in text for phrase in ["crée", "cree", "create"]):
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

    if any(phrase in text for phrase in ["lis", "lire", "read"]):
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

    if "server" in text or "serveur" in text or "service" in text or "statut" in text:
        return _response(
            "server_status",
            "check_server_health",
            check_server_health(message),
        )

    return _response(
        "unknown",
        "none",
        "Server Agent received the request but no supported server action matched.",
        status="unsupported",
    )
