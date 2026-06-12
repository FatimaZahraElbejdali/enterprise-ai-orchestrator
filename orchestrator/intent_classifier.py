INTENT_AGENT_MAP = {
    "odoo": "odoo_agent",
    "support": "support_agent",
    "knowledge": "knowledge_agent",
    "development": "development_agent",
    "security": "security_agent",
    "server": "server_agent",
    "general": "general_agent",
}


KEYWORDS = {
    "security": [
        "security", "cyber", "cybersecurity", "sécurité", "securite",
        "phishing", "spam", "malware", "virus", "ransomware", "breach",
        "intrusion", "attack", "attaque", "threat", "suspicious",
        "unauthorized", "access denied", "permission", "permissions",
        "role", "roles", "privilege", "admin rights", "vpn", "firewall",
        "authentication", "login failed", "2fa", "mfa", "token",
        "password leak", "data leak", "compromised", "piratage", "hacked",
        "hack", "fraud", "fraude", "identity", "identity theft"
    ],

    "development": [
        "bug", "error", "erreur", "exception", "crash", "broken",
        "fix", "debug", "code", "repository", "repo", "github", "gitlab",
        "pull request", "merge request", "branch", "commit", "api",
        "endpoint", "backend", "frontend", "docker", "container",
        "fastapi", "react", "nextjs", "next.js", "typescript",
        "javascript", "python", "deployment", "deploy", "ci/cd",
        "pipeline", "unit test", "integration test", "test failed",
        "build failed", "npm", "package", "dependency", "library",
        "refactor", "feature", "function", "class", "database migration"
    ],

    "server": [
        "server", "serveur", "infrastructure", "uptime", "downtime",
        "cpu", "ram", "disk", "storage", "memory", "database",
        "postgres", "mysql", "mongodb", "latency", "performance",
        "slow", "timeout", "load balancer", "kubernetes", "cluster",
        "monitoring", "logs", "status", "service unavailable", "503",
        "500 error", "restart service", "restart server", "backup",
        "restore", "cloud", "aws", "azure", "gcp", "linux", "nginx",
        "apache", "ssl", "certificate", "domain", "dns"
    ],

    "odoo": [
        "odoo", "erp", "stock", "inventory", "inventaire", "warehouse",
        "entrepôt", "supplier", "fournisseur", "vendor", "customer",
        "client", "crm", "product", "produit", "purchase", "achat",
        "purchase order", "sales order", "invoice", "facture",
        "quotation", "devis", "payment", "paiement", "refund",
        "remboursement", "delivery", "livraison", "order", "commande",
        "sale", "vente", "accounting", "comptabilité", "finance",
        "employee", "employé", "employees", "hr", "rh", "salary",
        "paie", "leave request", "congé", "timesheet", "attendance",
        "stock movement", "reorder", "replenishment"
    ],

    "support": [
        "printer", "imprimante", "print", "scanner", "ticket", "support",
        "helpdesk", "computer", "ordinateur", "pc", "laptop", "screen",
        "monitor", "keyboard", "mouse", "wifi", "wi-fi", "internet",
        "network", "réseau", "reseau", "password", "mot de passe",
        "cannot login", "can't login", "connexion", "connection issue",
        "email issue", "outlook", "gmail", "teams", "zoom", "slack",
        "software not working", "application not working", "install",
        "installation", "reset password", "forgot password", "blocked account",
        "account locked", "vpn problem", "no internet", "slow internet"
    ],

    "knowledge": [
        "document", "documentation", "knowledge", "knowledge base",
        "policy", "politique", "procedure", "procédure", "manual",
        "manuel", "guide", "instructions", "training", "formation",
        "best practice", "company policy", "onboarding", "handbook",
        "faq", "how to", "explain", "explanation", "what is",
        "where can i find", "rules", "process", "workflow",
        "internal documentation", "employee guide", "tutorial"
    ],
}


def _result(intent: str, confidence: float):
    return {
        "intent": intent,
        "selected_agent": INTENT_AGENT_MAP.get(intent, "general_agent"),
        "confidence": confidence,
        "requires_approval": False,
        "classifier_source": "local_rules",
        "classifier_error": None,
    }


def classify_with_confidence(message: str):
    text = message.lower().strip()

    scores = {}

    for intent, keywords in KEYWORDS.items():
        score = 0

        for keyword in keywords:
            if keyword in text:
                if " " in keyword:
                    score += 2
                else:
                    score += 1

        scores[intent] = score

    best_intent = max(scores, key=scores.get)
    best_score = scores[best_intent]

    if best_score == 0:
        return _result("general", 0.50)

    if best_score >= 4:
        confidence = 0.95
    elif best_score == 3:
        confidence = 0.90
    elif best_score == 2:
        confidence = 0.85
    else:
        confidence = 0.75

    return _result(best_intent, confidence)