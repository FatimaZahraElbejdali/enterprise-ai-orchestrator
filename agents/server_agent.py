def check_server_health(message: str):
    return {
        "task": "server_health_check",
        "cpu_usage": "34%",
        "ram_usage": "61%",
        "disk_usage": "72%",
        "status": "healthy"
    }


def check_service_status(message: str):
    return {
        "task": "service_status_check",
        "service": "mock_service",
        "status": "running"
    }


def run(message: str):
    text = message.lower()

    if "server" in text or "serveur" in text:
        return {
            "agent": "server",
            "tool_used": "check_server_health",
            "result": check_server_health(message)
        }

    if "service" in text or "status" in text or "statut" in text:
        return {
            "agent": "server",
            "tool_used": "check_service_status",
            "result": check_service_status(message)
        }

    return {
        "agent": "server",
        "tool_used": "none",
        "result": "Server Agent received the request."
    }