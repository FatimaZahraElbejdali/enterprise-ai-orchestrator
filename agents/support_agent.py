def create_ticket(issue: str):
    return {
        "ticket_id": "SUP-001",
        "issue": issue,
        "status": "created",
        "priority": "medium"
    }


def diagnose_printer_issue(issue: str):
    return {
        "diagnosis": "Printer issue detected",
        "suggested_steps": [
            "Check printer power",
            "Check network connection",
            "Restart printer",
            "Verify printer queue"
        ]
    }


def reset_password_request(user: str):
    return {
        "action": "reset_password_request",
        "user": user,
        "status": "waiting_for_admin_validation"
    }


def run(message: str):
    text = message.lower()

    if "printer" in text or "imprimante" in text:
        return {
            "agent": "support",
            "tool_used": "diagnose_printer_issue",
            "result": diagnose_printer_issue(message)
        }

    if "password" in text or "mot de passe" in text:
        return {
            "agent": "support",
            "tool_used": "reset_password_request",
            "result": reset_password_request(message)
        }

    if "ticket" in text or "incident" in text:
        return {
            "agent": "support",
            "tool_used": "create_ticket",
            "result": create_ticket(message)
        }

    return {
        "agent": "support",
        "tool_used": "none",
        "result": "Support Agent received the request but no specific tool matched."
    }