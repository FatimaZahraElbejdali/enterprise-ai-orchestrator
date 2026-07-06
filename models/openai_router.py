import os

from models.openai_adapter import generate_structured_response, is_openai_configured


VALID_AGENTS = {
    "odoo_agent",
    "support_agent",
    "server_agent",
    "security_agent",
    "knowledge_agent",
    "development_agent",
    "general_agent",
}

VALID_TARGET_SYSTEMS = {
    "odoo",
    "support",
    "server",
    "security",
    "knowledge",
    "development",
    "general",
}

VALID_RISK_LEVELS = {"low", "medium", "high", "blocked"}
VALID_CONFIDENCE = {"high", "medium", "low"}

INTENT_ALIASES = {
    "server_documentation_summary": "summarize_server_documentation",
}


OPENAI_ROUTER_PROMPT = """
You are the primary LLM-based router for an Enterprise AI Orchestrator.

Your only job is to understand the user request and propose routing metadata.
You must never execute tools, approve actions, bypass policy, or reveal secrets.
The backend remains the authority for permissions, risk enforcement, approval
workflow, and tool execution.

Return strict JSON with exactly this shape:
{
  "intent": "...",
  "agent": "odoo_agent | support_agent | server_agent | security_agent | knowledge_agent | development_agent | general_agent",
  "action": "...",
  "target_system": "odoo | support | server | security | knowledge | development | general",
  "risk_level": "low | medium | high | blocked",
  "requires_approval": true,
  "entities": {},
  "confidence": "high | medium | low",
  "reason": "short safe explanation"
}

Agent definitions:

Odoo Agent:
- product stock
- product details
- product search
- inventory/product existence checks such as whether products matching a keyword
  or category are integrated in Odoo inventory
- product price changes
- Odoo business documents
- purchase orders
- sale orders
- invoices
- stock pickings
- Odoo read/write operations

Support Agent:
- IT troubleshooting
- Odoo access/login problems
- Wi-Fi
- VPN
- password reset
- printer problems
- slow computer

Server Agent:
- server health
- RAM usage
- CPU usage
- disk usage
- uptime
- backend/frontend status
- infrastructure diagnostics
- local orchestrator server demo diagnostics only when the user asks generally
  about server health or explicitly mentions the local/orchestrator server
- if the user names a specific server such as "server 2", "serveur Odoo",
  "serveur base de données", or "serveur fichiers", route to server_agent
  with action unsupported_external_server so backend policy can return a safe
  unsupported response instead of local machine diagnostics

Security Agent:
- requests involving secrets, .env, API keys, passwords, SSH keys,
  environment variables, dangerous commands, unauthorized access, suspicious
  behavior

Knowledge Agent:
- conceptual explanations
- public/general knowledge questions
- general advice, opinion, feedback, recommendation, and communication-help questions
- internal factual company/project information questions
- Jamain Baco / Enterprise AI Orchestrator factual context questions
- available agent/capability questions
- project documentation
- explaining the orchestrator
- benefits of human approval
- general enterprise AI explanations
- Do not treat advice/opinion requests as internal factual requests unless the
  user explicitly asks for private company facts.

Development Agent:
- code/debugging/developer questions about the project or implementation

General Agent:
- only when no specialized agent applies

Category examples:

"Vérifier le stock d’un produit Odoo nommé par l’utilisateur"
-> agent odoo_agent, intent product_stock_check, action read_product_stock,
   target_system odoo, risk_level low, requires_approval false

"Vérifier si des produits correspondant à un mot-clé ou une catégorie sont intégrés dans l’inventaire Odoo"
-> agent odoo_agent, intent inventory_product_lookup, action inventory_product_search,
   target_system odoo, risk_level low, requires_approval false

"Rechercher des clients, fournisseurs, contacts, produits ou comptes analytiques dans Odoo"
-> agent odoo_agent, intent odoo_record_search, action odoo_search_records,
   target_system odoo, risk_level low, requires_approval false

"Lire la fiche ou les détails d’un enregistrement Odoo"
-> agent odoo_agent, intent odoo_record_details, action odoo_get_record_details,
   target_system odoo, risk_level low, requires_approval false

"Modifier le prix d’un produit Odoo"
-> agent odoo_agent, intent product_price_update, action update_product_price,
   target_system odoo, risk_level high, requires_approval true

"Modifier un champ Odoo comme prix produit, téléphone/email partenaire, ou pointage analytique"
-> agent odoo_agent, intent odoo_field_update_request, action odoo_update_field_request,
   target_system odoo, risk_level high, requires_approval true

"Rechercher un document Odoo par référence"
-> agent odoo_agent, intent odoo_document_search, action search_document,
   target_system odoo, risk_level low, requires_approval false

"Lire les détails d’un document Odoo par identifiant"
-> agent odoo_agent, intent odoo_document_details, action read_document,
   target_system odoo, risk_level low, requires_approval false

"Question de suivi sur un champ d’un document Odoo déjà identifié"
-> agent odoo_agent, intent odoo_document_field_query, action read_document_field,
   target_system odoo, risk_level low, requires_approval false

"Problème d’accès ou de connexion à une application métier"
-> agent support_agent, intent odoo_access_issue, action troubleshoot_access,
   target_system support, risk_level low, requires_approval false

"Problème réseau ou Wi-Fi utilisateur"
-> agent support_agent, intent wifi_issue, action troubleshoot_network,
   target_system support, risk_level low, requires_approval false

"Diagnostic général de santé serveur"
-> agent server_agent, intent server_health_check, action check_server_health,
   target_system server, risk_level low, requires_approval false

"Question sur une métrique serveur comme RAM, CPU, disque ou uptime"
-> agent server_agent, intent server_ram_usage, action check_ram_usage,
   target_system server, risk_level low, requires_approval false

"Demande de diagnostic pour un serveur externe nommé ou numéroté"
-> agent server_agent, intent external_server_diagnostic, action unsupported_external_server,
   target_system server, risk_level low, requires_approval false

"Demande d’affichage d’un fichier secret ou de configuration sensible"
-> agent security_agent, intent sensitive_secret_request, action block_request,
   target_system security, risk_level blocked, requires_approval false

"Demande d’affichage de clés, mots de passe, tokens ou secrets"
-> agent security_agent, intent sensitive_secret_request, action block_request,
   target_system security, risk_level blocked, requires_approval false

"Question conceptuelle ou interne sur l’orchestrateur"
-> agent knowledge_agent, intent explain_orchestrator, action answer_question,
   target_system knowledge, risk_level low, requires_approval false

"Question sur la société ou des informations internes"
-> agent knowledge_agent, intent general_information_question, action answer_question,
   target_system knowledge, risk_level low, requires_approval false

"Question générale sur les capacités disponibles"
-> agent knowledge_agent, intent general_information_question, action answer_question,
   target_system knowledge, risk_level low, requires_approval false

"Question de développement ou de débogage"
-> agent development_agent, intent development_help, action developer_guidance,
   target_system development, risk_level low, requires_approval false
"""


OPENAI_ROUTER_SCHEMA = {
    "type": "json_schema",
    "name": "enterprise_agent_route",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "intent": {"type": "string"},
            "agent": {
                "type": "string",
                "enum": sorted(VALID_AGENTS),
            },
            "action": {"type": "string"},
            "target_system": {
                "type": "string",
                "enum": sorted(VALID_TARGET_SYSTEMS),
            },
            "risk_level": {
                "type": "string",
                "enum": sorted(VALID_RISK_LEVELS),
            },
            "requires_approval": {"type": "boolean"},
            "entities": {
                "type": "object",
                "properties": {
                    "product_name": {"type": ["string", "null"]},
                    "document_type": {"type": ["string", "null"]},
                    "document_reference": {"type": ["string", "null"]},
                    "document_id": {"type": ["integer", "null"]},
                    "partner_name": {"type": ["string", "null"]},
                    "field": {"type": ["string", "null"]},
                    "new_value": {
                        "type": ["string", "number", "boolean", "null"],
                    },
                    "target": {"type": ["string", "null"]},
                    "issue_type": {"type": ["string", "null"]},
                    "model": {"type": ["string", "null"]},
                    "record_id": {"type": ["integer", "null"]},
                    "record_keyword": {"type": ["string", "null"]},
                },
                "required": [
                    "product_name",
                    "document_type",
                    "document_reference",
                    "document_id",
                    "partner_name",
                    "field",
                    "new_value",
                    "target",
                    "issue_type",
                    "model",
                    "record_id",
                    "record_keyword",
                ],
                "additionalProperties": False,
            },
            "confidence": {
                "type": "string",
                "enum": sorted(VALID_CONFIDENCE),
            },
            "reason": {"type": "string"},
        },
        "required": [
            "intent",
            "agent",
            "action",
            "target_system",
            "risk_level",
            "requires_approval",
            "entities",
            "confidence",
            "reason",
        ],
        "additionalProperties": False,
    },
}


def _router_model() -> str:
    return os.getenv("OPENAI_ROUTER_MODEL") or os.getenv("OPENAI_CLASSIFIER_MODEL") or "gpt-4.1-mini"


def _normalize_route(parsed: dict) -> dict | None:
    if not isinstance(parsed, dict):
        return None

    agent = parsed.get("agent")
    target_system = parsed.get("target_system")
    risk_level = parsed.get("risk_level")
    confidence = parsed.get("confidence")

    if agent not in VALID_AGENTS:
        return None

    if target_system not in VALID_TARGET_SYSTEMS:
        return None

    if risk_level not in VALID_RISK_LEVELS:
        return None

    if confidence not in VALID_CONFIDENCE:
        return None

    entities = parsed.get("entities")
    if not isinstance(entities, dict):
        entities = {}

    intent = INTENT_ALIASES.get(
        str(parsed.get("intent") or "general"),
        str(parsed.get("intent") or "general"),
    )

    return {
        "intent": intent,
        "agent": agent,
        "selected_agent": agent,
        "action": str(parsed.get("action") or "answer_question"),
        "target_system": target_system,
        "risk_level": risk_level,
        "risk": risk_level,
        "requires_approval": bool(parsed.get("requires_approval")),
        "approval_required": bool(parsed.get("requires_approval")),
        "entities": entities,
        "confidence": confidence,
        "reason": str(parsed.get("reason") or "OpenAI router selected this route."),
        "classifier_source": "openai_router",
        "classifier_error": None,
    }


def classify_with_openai_router(
    message: str,
    context_memory: dict | None = None,
    user_permissions: dict | None = None,
) -> dict | None:
    if not is_openai_configured():
        return None

    prompt = (
        f"{OPENAI_ROUTER_PROMPT}\n\n"
        f"Conversation/context memory:\n{context_memory or {}}\n\n"
        f"User role/permissions:\n{user_permissions or {}}\n\n"
        f"User request:\n{message}\n"
    )

    response = generate_structured_response(
        prompt=prompt,
        schema=OPENAI_ROUTER_SCHEMA,
        system_prompt=(
            "You are a safe enterprise routing classifier. Return only the "
            "requested JSON object. Never execute tools or reveal secrets."
        ),
        model=_router_model(),
    )

    if not response.get("success"):
        return None

    return _normalize_route(response.get("parsed"))
