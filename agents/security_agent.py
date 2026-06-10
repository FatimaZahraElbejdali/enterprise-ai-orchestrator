def analyze_security_alert(message: str):
    return {
        "task": "security_alert_analysis",
        "risk_level": "medium",
        "recommended_actions": [
            "Check user activity logs",
            "Verify source IP address",
            "Review access permissions",
            "Escalate if suspicious"
        ]
    }


def check_access_request(message: str):
    return {
        "task": "access_review",
        "status": "requires_validation",
        "note": "Access changes should require approval."
    }


def run(message: str):
    text = message.lower()

    if (
        "security" in text
        or "cyber" in text
        or "sécurité" in text
        or "suspicious" in text
        or "login" in text
        or "alert" in text
    ):
        return {
            "agent": "security",
            "tool_used": "analyze_security_alert",
            "result": analyze_security_alert(message)
        }

    if "access" in text or "accès" in text or "permission" in text:
        return {
            "agent": "security",
            "tool_used": "check_access_request",
            "result": check_access_request(message)
        }

    return {
        "agent": "security",
        "tool_used": "none",
        "result": "Security Agent received the request."
    }
