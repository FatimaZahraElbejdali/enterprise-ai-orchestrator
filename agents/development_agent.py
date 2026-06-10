def analyze_bug(message: str):
    return {
        "task": "bug_analysis",
        "summary": "Mock bug analysis generated.",
        "next_steps": [
            "Check application logs",
            "Identify recent code changes",
            "Reproduce the issue",
            "Assign to developer"
        ]
    }


def deployment_checklist(message: str):
    return {
        "task": "deployment_checklist",
        "steps": [
            "Pull latest code",
            "Run tests",
            "Check environment variables",
            "Deploy to staging",
            "Validate application health"
        ]
    }


def run(message: str):
    text = message.lower()

    if "bug" in text or "error" in text or "erreur" in text:
        return {
            "agent": "development",
            "tool_used": "analyze_bug",
            "result": analyze_bug(message)
        }

    if "deploy" in text or "deployment" in text or "déploiement" in text:
        return {
            "agent": "development",
            "tool_used": "deployment_checklist",
            "result": deployment_checklist(message)
        }

    return {
        "agent": "development",
        "tool_used": "none",
        "result": "Development Agent received the request."
    }