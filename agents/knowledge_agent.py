import re
import unicodedata
from pathlib import Path

from models.openai_adapter import generate_response, is_openai_configured


INTERNAL_INFO_UNAVAILABLE = (
    "Je n'ai pas encore suffisamment d'informations internes pour répondre "
    "précisément à cette question."
)

PUBLIC_LLM_UNAVAILABLE = (
    "Je ne peux pas générer une réponse fiable pour le moment, car le fournisseur "
    "LLM configuré n’est pas disponible."
)

INTERNAL_DOC_PATHS = [
    Path("docs/company_profile.md"),
    Path("docs/departments.md"),
    Path("docs/internal_faq.md"),
    Path("docs/server_info.md"),
]

STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "can",
    "ce",
    "cet",
    "cette",
    "comment",
    "de",
    "des",
    "do",
    "does",
    "du",
    "est",
    "et",
    "for",
    "how",
    "is",
    "it",
    "la",
    "le",
    "les",
    "me",
    "moi",
    "of",
    "or",
    "ou",
    "pour",
    "que",
    "quel",
    "quelle",
    "quels",
    "quelles",
    "quoi",
    "the",
    "this",
    "un",
    "une",
    "what",
    "where",
    "who",
}

QUESTION_START_PATTERNS = [
    r"^(what|who|how|why|where|when)\b",
    r"^(what's|whats)\b",
    r"^(c'?est quoi|c est quoi|c quoi)\b",
    r"^(qu'?est ce|quest ce|quest-ce)\b",
    r"^(qui|quoi|comment|pourquoi|ou|quel|quelle|quels|quelles)\b",
    r"^(explique|presente)\b",
]

TOOL_CATEGORY_TERMS = {
    "business_object": {
        "stock",
        "inventory",
        "inventaire",
        "price",
        "prix",
        "product",
        "produit",
        "commande",
        "order",
        "invoice",
        "facture",
        "document",
        "supplier",
        "fournisseur",
    },
    "server_operation": {
        "server",
        "serveur",
        "cpu",
        "ram",
        "memory",
        "memoire",
        "disk",
        "disque",
        "uptime",
        "service",
        "diagnostic",
    },
    "support_issue": {
        "access",
        "acces",
        "connexion",
        "login",
        "issue",
        "problem",
        "probleme",
        "troubleshoot",
        "depanner",
        "lenteur",
        "slow",
        "wifi",
        "wi-fi",
        "printer",
        "imprimante",
    },
    "sensitive": {
        ".env",
        "api key",
        "password",
        "mot de passe",
        "secret",
        "ssh",
        "token",
        "environment variable",
        "variable d'environnement",
        "variables d'environnement",
    },
}

OPERATIONAL_ACTION_TERMS = {
    "affiche",
    "change",
    "changer",
    "check",
    "cherche",
    "create",
    "delete",
    "detail",
    "details",
    "diagnose",
    "diagnostic",
    "donne",
    "get",
    "liste",
    "lire",
    "modifier",
    "montre",
    "read",
    "recherche",
    "search",
    "set",
    "show",
    "update",
    "verifie",
    "vérifie",
}

BUSINESS_QUERY_TERMS = {
    "combien",
    "count",
    "how many",
    "available",
    "disponible",
    "availability",
    "qty",
    "quantity",
    "quantite",
    "quantité",
    "total",
}

INTERNAL_KNOWLEDGE_TERMS = {
    "organization": {
        "company",
        "entreprise",
        "jamain",
        "baco",
        "department",
        "departement",
        "employee",
        "employe",
        "responsibility",
        "responsabilite",
    },
    "internal_docs": {
        "internal",
        "interne",
        "procedure",
        "procédure",
        "policy",
        "politique",
        "faq",
        "manual",
        "manuel",
        "handbook",
        "guide",
    },
    "orchestrator_project": {
        "orchestrator",
        "orchestrateur",
        "agent",
        "agents",
        "approval",
        "approbation",
        "validation",
        "audit",
        "workflow",
    },
}

ADVICE_OR_OPINION_TERMS = {
    "advice",
    "advise",
    "ameliore",
    "améliore",
    "ameliorer",
    "améliorer",
    "avis",
    "better",
    "conseil",
    "conseils",
    "critique",
    "feedback",
    "idee",
    "idée",
    "ideas",
    "improve",
    "opinion",
    "pense",
    "penses",
    "propose",
    "proposer",
    "recommend",
    "recommandation",
    "recommandations",
    "should",
    "suggest",
    "suggestion",
    "suggestions",
}

INTERNAL_FACT_TERMS = {
    "adresse",
    "address",
    "budget",
    "ceo",
    "chiffre",
    "contact",
    "contacts",
    "department",
    "departement",
    "departements",
    "departments",
    "directeur",
    "direction",
    "employee",
    "employees",
    "employe",
    "employes",
    "employés",
    "finance",
    "fondateur",
    "founder",
    "manager",
    "policy",
    "policies",
    "politique",
    "politiques",
    "procedure",
    "procedures",
    "procédure",
    "procédures",
    "responsabilite",
    "responsabilites",
    "responsabilité",
    "responsabilités",
    "rh",
    "role",
    "rôle",
    "roles",
    "rôles",
    "salary",
    "salaire",
    "server inventory",
    "serveurs internes",
}

FACTUAL_QUESTION_PATTERNS = [
    r"^(what|who|where|when)\b",
    r"^(what's|whats)\b",
    r"^(c'?est quoi|c est quoi|c quoi)\b",
    r"^(qui|ou|quel|quelle|quels|quelles)\b",
    r"\b(liste|list|affiche|show|donne|give|nom|name|adresse|address|contact)\b",
]

STATIC_PROJECT_ANSWERS = [
    (
        {"jamain", "baco"},
        (
            "Jamain Baco est l'entreprise où l'Enterprise AI Orchestrator est "
            "développé et testé. Je n'ai pas d'autres informations internes "
            "validées à son sujet."
        ),
    ),
    (
        {"orchestrator", "orchestrateur", "capabilities", "capacites", "peux", "do"},
        (
            "L'Enterprise AI Orchestrator est une interface IA interne pour les "
            "systèmes d'entreprise. Il comprend les demandes en langage naturel, "
            "route vers le bon domaine, applique les permissions RBAC, évalue le "
            "risque, demande une validation humaine pour les actions sensibles, "
            "exécute uniquement des capacités backend enregistrées et conserve "
            "des traces d'audit."
        ),
    ),
    (
        {"validation", "approval", "approbation"},
        (
            "La validation humaine sert à bloquer les actions sensibles avant "
            "exécution. L'orchestrateur prépare la demande, vérifie les droits et "
            "le risque, puis attend une décision humaine avant toute modification."
        ),
    ),
    (
        {"systemes", "systèmes", "connectes", "connectés", "integrations", "intégrations"},
        (
            "Les systèmes actuellement représentés dans l'orchestrateur sont Odoo, "
            "les workflows de support IT, les diagnostics serveur locaux de "
            "démonstration, les contrôles de sécurité, les validations et les logs "
            "d'audit."
        ),
    ),
    (
        {"odoo"},
        (
            "Odoo est un ERP utilisé pour gérer des données métier comme les "
            "produits, clients, fournisseurs, commandes, factures et livraisons. "
            "Dans cet orchestrateur, les lectures Odoo passent par des capacités "
            "sécurisées et les écritures sensibles nécessitent une validation."
        ),
    ),
]


def _normalize_text(message: str):
    normalized = unicodedata.normalize("NFKD", message or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().replace("’", "'").split())


def _tokenize(value: str):
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", _normalize_text(value))
        if token not in STOPWORDS
    }


def _is_question_like(text: str):
    return "?" in text or any(
        re.search(pattern, text)
        for pattern in QUESTION_START_PATTERNS
    )


def _looks_like_tool_request(text: str):
    if any(term in text for term in TOOL_CATEGORY_TERMS["sensitive"]):
        return True

    has_operational_action = any(term in text for term in OPERATIONAL_ACTION_TERMS)
    has_tool_object = any(
        term in text
        for category in ("business_object", "server_operation", "support_issue")
        for term in TOOL_CATEGORY_TERMS[category]
    )
    has_business_query = any(term in text for term in BUSINESS_QUERY_TERMS)

    return has_tool_object and (has_operational_action or has_business_query)


def is_advice_or_opinion_question(message: str):
    text = _normalize_text(message)

    if not text:
        return False

    return any(term in text for term in ADVICE_OR_OPINION_TERMS)


def _has_internal_scope(text: str):
    return any(
        term in text
        for terms in INTERNAL_KNOWLEDGE_TERMS.values()
        for term in terms
    )


def _has_internal_fact_signal(text: str):
    return any(term in text for term in INTERNAL_FACT_TERMS) or any(
        re.search(pattern, text)
        for pattern in FACTUAL_QUESTION_PATTERNS
    )


def is_internal_knowledge_question(message: str):
    text = _normalize_text(message)

    if not text:
        return False

    if not _has_internal_scope(text):
        return False

    if is_advice_or_opinion_question(message):
        return False

    return _has_internal_fact_signal(text)


def is_general_information_question(message: str):
    text = _normalize_text(message)

    if not text or _looks_like_tool_request(text):
        return False

    return _is_question_like(text) or is_internal_knowledge_question(message)


def _read_internal_documents():
    documents = []

    for path in INTERNAL_DOC_PATHS:
        if not path.exists() or not path.is_file():
            continue

        content = path.read_text(encoding="utf-8").strip()

        if content:
            documents.append(
                {
                    "path": str(path),
                    "content": content,
                    "tokens": _tokenize(content),
                }
            )

    return documents


def _find_relevant_internal_context(message: str):
    query_tokens = _tokenize(message)

    if not query_tokens:
        return ""

    scored = []

    for document in _read_internal_documents():
        overlap = query_tokens & document["tokens"]

        if overlap:
            scored.append((len(overlap), document["path"], document["content"]))

    if not scored:
        return ""

    scored.sort(reverse=True)
    context_blocks = []

    for _, path, content in scored[:3]:
        context_blocks.append(f"Source: {path}\n{content[:4000]}")

    return "\n\n---\n\n".join(context_blocks)


def _static_project_answer(message: str):
    tokens = _tokenize(message)
    text = _normalize_text(message)

    if "what can you do" in text or "que peux tu faire" in text:
        tokens |= {"orchestrator", "capabilities"}

    unknown_company_detail_tokens = {
        "adresse",
        "address",
        "budget",
        "ceo",
        "contact",
        "contacts",
        "directeur",
        "employee",
        "employees",
        "employe",
        "employes",
        "fondateur",
        "founder",
        "manager",
        "salary",
        "salaire",
    }

    if {"jamain", "baco"} & tokens and unknown_company_detail_tokens & tokens:
        return None

    if "odoo" in text:
        tokens.add("odoo")

    for required_tokens, answer in STATIC_PROJECT_ANSWERS:
        if required_tokens & tokens:
            if "odoo" in required_tokens and "odoo" not in tokens:
                continue
            return _response(
                answer=answer,
                tool_used="knowledge_project_answer",
                provider="local_policy",
                model="static_project_context",
                llm_success=True,
                error=None,
                context_used=True,
            )

    return None


def _answer_with_llm(prompt: str, system_prompt: str, tool_used: str, context: str = ""):
    if not is_openai_configured():
        answer = (
            INTERNAL_INFO_UNAVAILABLE
            if tool_used == "internal_documents"
            else PUBLIC_LLM_UNAVAILABLE
        )
        return _response(
            answer=answer,
            tool_used=tool_used,
            provider="openai",
            model=None,
            llm_success=False,
            error="missing_api_key",
            context_used=bool(context),
        )

    llm_result = generate_response(
        prompt=prompt,
        system_prompt=system_prompt,
    )
    answer = (llm_result.get("content") or "").strip()
    llm_success = bool(llm_result.get("success") and answer)

    if not llm_success:
        answer = (
            INTERNAL_INFO_UNAVAILABLE
            if tool_used == "internal_documents"
            else PUBLIC_LLM_UNAVAILABLE
        )

    return _response(
        answer=answer,
        tool_used=tool_used,
        provider=llm_result.get("provider"),
        model=llm_result.get("model"),
        llm_success=llm_success,
        error=llm_result.get("error"),
        context_used=bool(context),
    )


def _answer_internal_question(message: str):
    context = _find_relevant_internal_context(message)

    if not context:
        return _response(
            answer=INTERNAL_INFO_UNAVAILABLE,
            tool_used="internal_documents",
            provider="local_docs",
            model="configured_internal_documents",
            llm_success=True,
            error=None,
            context_used=False,
        )

    prompt = (
        "Question utilisateur:\n"
        f"{message}\n\n"
        "Documents internes validés:\n"
        f"{context}\n\n"
        "Réponds uniquement avec les informations présentes dans ces documents. "
        "Si les documents ne suffisent pas, réponds exactement: "
        f"{INTERNAL_INFO_UNAVAILABLE}"
    )
    system_prompt = (
        "Tu es l’agent de connaissance interne de Jamain Baco. Réponds en français, "
        "de façon concise, uniquement à partir du contexte interne fourni. "
        "N’invente aucun fait d’entreprise."
    )

    return _answer_with_llm(
        prompt=prompt,
        system_prompt=system_prompt,
        tool_used="internal_documents",
        context=context,
    )


def _answer_public_question(message: str):
    system_prompt = (
        "Tu es l’agent de connaissance publique de l’Enterprise AI Orchestrator. "
        "Réponds en français clair et concis aux questions générales qui ne "
        "nécessitent pas d’outil backend ni de données internes. Ne prétends pas "
        "avoir consulté Odoo, le serveur, des documents internes ou des données "
        "temps réel. Si la question demande une information actuelle ou interne "
        "non fournie, indique prudemment tes limites."
    )

    return _answer_with_llm(
        prompt=message,
        system_prompt=system_prompt,
        tool_used="public_llm_answer",
    )


def _response(
    *,
    answer: str,
    tool_used: str,
    provider: str | None,
    model: str | None,
    llm_success: bool,
    error: str | None,
    context_used: bool,
):
    return {
        "intent": "knowledge",
        "agent": "knowledge_agent",
        "parser_source": "knowledge_agent",
        "parsed_action": "answer_question",
        "requires_approval": False,
        "approval_required": False,
        "status": "completed",
        "tool_used": tool_used,
        "result": {
            "answer": answer,
            "source": tool_used,
            "context_used": context_used,
        },
        "response": answer,
        "message": answer,
        "provider": provider,
        "model": model,
        "llm_success": llm_success,
        "llm_error": error,
    }


def run(message: str):
    static_answer = _static_project_answer(message)

    if static_answer:
        return static_answer

    if is_internal_knowledge_question(message):
        return _answer_internal_question(message)

    if is_general_information_question(message):
        return _answer_public_question(message)

    return _response(
        answer=(
            "Action non disponible. Cette demande n’est pas encore connectée à "
            "un outil backend sécurisé."
        ),
        tool_used="unsupported_knowledge_request",
        provider="local_policy",
        model="knowledge_safety_policy",
        llm_success=True,
        error=None,
        context_used=False,
    )
