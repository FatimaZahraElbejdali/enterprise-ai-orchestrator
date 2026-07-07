from models.openai_adapter import generate_response, is_openai_configured


ODOO_ACCESS_STEPS = [
    "Vérifier la connexion internet.",
    "Vérifier l’URL Odoo utilisée.",
    "Vérifier les identifiants.",
    "Tester avec un autre navigateur ou en navigation privée.",
    "Vider le cache et les cookies.",
    "Vérifier VPN/réseau interne si nécessaire.",
    "Vérifier si d’autres utilisateurs ont le même problème.",
    "Contacter l’administrateur IT si le problème persiste.",
]


def _is_french(message: str):
    text = message.lower()
    return any(
        marker in text
        for marker in [
            "je ",
            "j’ai",
            "j'ai",
            "n’arrive",
            "n'arrive",
            "problème",
            "probleme",
            "connexion",
            "ordinateur",
            "mot de passe",
            "réseau",
            "reseau",
        ]
    )


def _structured_response(
    action: str,
    title: str,
    steps: list[str],
    escalation: str,
    parser_source: str = "support_fallback",
):
    response_text = f"{title}\n" + "\n".join(
        f"{index}. {step}" for index, step in enumerate(steps, start=1)
    )

    if escalation:
        response_text = f"{response_text}\nEscalade: {escalation}"

    return {
        "intent": "support",
        "agent": "support_agent",
        "action": action,
        "parsed_action": action,
        "parser_source": parser_source,
        "requires_approval": False,
        "approval_required": False,
        "status": "completed",
        "response": response_text,
        "message": response_text,
        "tool_used": "support_knowledge_base",
        "result": {
            "title": title,
            "steps": steps,
            "escalation": escalation,
        },
    }


def _support_tool_for_message(message: str, default: str = "support_knowledge_base"):
    text = message.lower()

    if "printer" in text or "imprimante" in text:
        return "diagnose_printer_issue"

    return default


def is_odoo_access_issue(message: str):
    text = message.lower().replace("’", "'")

    has_odoo = "odoo" in text
    access_problem_terms = [
        "n'arrive pas",
        "je n'arrive pas",
        "problème de connexion",
        "probleme de connexion",
        "ne s'ouvre pas",
        "me connecter",
        "accéder",
        "acceder",
        "access",
        "cannot access",
        "can't access",
        "not loading",
        "login problem",
        "connexion",
    ]
    generic_login_problem = any(
        phrase in text
        for phrase in [
            "je n'arrive pas à me connecter",
            "je n'arrive pas a me connecter",
            "impossible de me connecter",
            "i cannot login",
            "i can't login",
            "cannot login",
            "can't login",
        ]
    )

    return (has_odoo and any(term in text for term in access_problem_terms)) or generic_login_problem


def is_support_request(message: str):
    text = message.lower().replace("’", "'")

    return is_odoo_access_issue(message) or any(
        term in text
        for term in [
            "wifi",
            "wi-fi",
            "réseau",
            "reseau",
            "vpn",
            "ordinateur",
            "computer",
            "pc lent",
            "ordinateur lent",
            "slow computer",
            "mot de passe",
            "password",
            "imprimante",
            "printer",
            "support",
            "helpdesk",
            "ticket",
            "incident",
        ]
    )


def classify_support_action(message: str):
    text = message.lower()

    if is_odoo_access_issue(message):
        return "troubleshoot_issue"

    if any(term in text for term in ["wifi", "wi-fi", "réseau", "reseau", "vpn", "lent", "slow", "ordinateur", "computer", "printer", "imprimante"]):
        return "troubleshoot_issue"

    if any(term in text for term in ["mot de passe", "password", "comment", "how do i", "how to"]):
        return "answer_it_question"

    if any(term in text for term in ["procédure", "procedure", "étapes", "etapes", "steps"]):
        return "explain_procedure"

    return "troubleshoot_issue"


def _fallback_steps(message: str, action: str):
    text = message.lower()

    if "printer" in text:
        return (
            "Printer issue detected",
            [
                "Check printer power.",
                "Check printer network connection.",
                "Confirm the printer is selected in the print dialog.",
                "Restart the printer and retry the print job.",
                "Contact IT support if the issue persists.",
            ],
            "Contact IT support if printing still fails.",
        )

    if "imprimante" in text:
        return (
            "Diagnostic imprimante",
            [
                "Vérifier que l’imprimante est allumée.",
                "Vérifier la connexion réseau de l’imprimante.",
                "Confirmer que la bonne imprimante est sélectionnée.",
                "Redémarrer l’imprimante puis relancer l’impression.",
                "Contacter le support IT si le problème persiste.",
            ],
            "Contacter le support IT si l’impression échoue encore.",
        )

    if is_odoo_access_issue(message):
        return (
            "Diagnostic accès Odoo",
            ODOO_ACCESS_STEPS,
            "Contacter l’administrateur IT si le problème persiste.",
        )

    if "vpn" in text:
        return (
            "Diagnostic VPN",
            [
                "Vérifier la connexion internet.",
                "Confirmer que le client VPN est ouvert.",
                "Vérifier l’identifiant et le mot de passe.",
                "Redémarrer le client VPN.",
                "Tester depuis un autre réseau si possible.",
            ],
            "Contacter le support IT si la connexion VPN échoue encore.",
        )

    if "wifi" in text or "wi-fi" in text or "réseau" in text or "reseau" in text:
        return (
            "Diagnostic connexion réseau",
            [
                "Vérifier que le Wi-Fi est activé.",
                "Se reconnecter au réseau de l’entreprise.",
                "Redémarrer l’ordinateur si nécessaire.",
                "Tester un autre site ou service.",
                "Vérifier si d’autres utilisateurs sont impactés.",
            ],
            "Contacter le support IT si le réseau reste indisponible.",
        )

    if "lent" in text or "slow" in text or "ordinateur" in text or "computer" in text:
        return (
            "Diagnostic poste utilisateur",
            [
                "Fermer les applications non nécessaires.",
                "Vérifier l’espace disque disponible.",
                "Redémarrer l’ordinateur.",
                "Vérifier les mises à jour en attente.",
                "Noter depuis quand le ralentissement a commencé.",
            ],
            "Contacter le support IT si le ralentissement persiste.",
        )

    if action == "answer_it_question":
        return (
            "Réponse support IT",
            [
                "Identifier le service concerné.",
                "Vérifier les accès et identifiants.",
                "Suivre la procédure interne si disponible.",
                "Demander une validation administrateur si nécessaire.",
            ],
            "Contacter le support IT pour une action administrateur.",
        )

    return (
        "Diagnostic support",
        [
            "Identifier le service ou l’équipement concerné.",
            "Reproduire le problème et noter le message d’erreur.",
            "Tester une solution simple: redémarrage, autre navigateur ou autre réseau.",
            "Vérifier si d’autres utilisateurs sont impactés.",
        ],
        "Contacter le support IT si le problème persiste.",
    )


def _openai_support_response(message: str, action: str):
    if not is_openai_configured():
        return None

    language = "French" if _is_french(message) else "English"
    response = generate_response(
        prompt=(
            f"User support request: {message}\n"
            "Provide a concise helpdesk troubleshooting answer. "
            "Do not include secrets, raw config, URLs from environment, usernames, tokens, or API keys. "
            "Use clear numbered steps and an escalation sentence."
        ),
        system_prompt=(
            "You are the Support Agent of an enterprise AI orchestrator. "
            f"Answer in {language}. Do not execute actions."
        ),
    )

    if not response.get("success") or not response.get("content"):
        return None

    title, steps, escalation = _fallback_steps(message, action)
    result = _structured_response(
        action=action,
        title=title,
        steps=steps,
        escalation=escalation,
        parser_source="openai",
    )
    result["response"] = response["content"]
    result["message"] = response["content"]
    result["tool_used"] = _support_tool_for_message(message)
    return result


def run(
    message: str,
    action: str | None = None,
    capability: str | None = None,
    execution_mode: str | None = None,
):
    action = action or classify_support_action(message)
    openai_result = _openai_support_response(message, action)

    if openai_result:
        openai_result["capability"] = capability or "support.troubleshooting"
        openai_result["execution_mode"] = execution_mode or "llm_direct"
        return openai_result

    title, steps, escalation = _fallback_steps(message, action)
    result = _structured_response(
        action=action,
        title=title,
        steps=steps,
        escalation=escalation,
    )

    result["tool_used"] = _support_tool_for_message(message)
    result["capability"] = capability or "support.troubleshooting"
    result["execution_mode"] = execution_mode or "llm_direct"

    return result
