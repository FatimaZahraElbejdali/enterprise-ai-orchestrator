import json
import os
import re
import unicodedata

from models.openai_adapter import OpenAI, _extract_text, _get_api_key, _get_model, _get_timeout
from orchestrator.tool_executor import odoo


READ_TOOL_NAME_MAP = {
    "odoo_search_models": "odoo.search_models",
    "odoo_describe_model": "odoo.describe_model",
    "odoo_search_records": "odoo.search_records",
    "odoo_count_records": "odoo.count_records",
    "odoo_aggregate_records": "odoo.aggregate_records",
    "odoo_read_record": "odoo.read_record",
}

MAX_TOOL_CALLS = int(os.getenv("ODOO_READ_AGENT_MAX_TOOL_CALLS", "6") or "6")


ODOO_READ_AGENT_TOOLS = [
    {
        "type": "function",
        "name": "odoo_search_models",
        "description": "Search safe installed Odoo models by business concept.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "odoo_describe_model",
        "description": "Describe safe readable fields for one validated Odoo model.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
            },
            "required": ["model"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "odoo_search_records",
        "description": "Search records with a backend-validated read-only domain.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "domain": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "operator": {"type": "string"},
                            "value": {"type": ["string", "number", "boolean", "null"]},
                        },
                        "required": ["field", "operator", "value"],
                        "additionalProperties": False,
                    },
                },
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "limit": {"type": "integer"},
                "order": {"type": ["string", "null"]},
            },
            "required": ["model", "domain", "fields", "limit", "order"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "odoo_count_records",
        "description": "Count records with a backend-validated read-only domain.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "domain": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "operator": {"type": "string"},
                            "value": {"type": ["string", "number", "boolean", "null"]},
                        },
                        "required": ["field", "operator", "value"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["model", "domain"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "odoo_aggregate_records",
        "description": "Group safe Odoo records and return bounded validated count aggregates.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "domain": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "operator": {"type": "string"},
                            "value": {"type": ["string", "number", "boolean", "null"]},
                        },
                        "required": ["field", "operator", "value"],
                        "additionalProperties": False,
                    },
                },
                "group_by": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "aggregates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "operation": {"type": "string"},
                            "field": {"type": "string"},
                            "alias": {"type": "string"},
                        },
                        "required": ["operation", "field", "alias"],
                        "additionalProperties": False,
                    },
                },
                "order_by": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "direction": {"type": "string"},
                        },
                        "required": ["field", "direction"],
                        "additionalProperties": False,
                    },
                },
                "limit": {"type": "integer"},
            },
            "required": ["model", "domain", "group_by", "aggregates", "order_by", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "odoo_read_record",
        "description": "Read one record by ID with backend-validated safe fields.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "record_id": {"type": "integer"},
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["model", "record_id", "fields"],
            "additionalProperties": False,
        },
    },
]


ODOO_READ_AGENT_INSTRUCTIONS = """
Tu es un agent interne de lecture Odoo pour un orchestrateur d'entreprise.

Tu peux uniquement utiliser les outils de lecture Odoo fournis. Tu ne peux pas
modifier, créer, supprimer, confirmer, annuler, valider, affecter ou mettre à
jour des données. Si la demande est une écriture, réponds que la modification
doit passer par le flux de validation existant.

Procédure attendue:
1. Cherche le modèle sûr correspondant au concept métier.
2. Décris le modèle avant de construire un domaine.
3. Utilise uniquement les champs et valeurs visibles dans describe_model.
4. Appelle search_records, count_records, aggregate_records ou read_record.
5. Réponds en français avec une réponse métier concise basée uniquement sur les
   résultats d'outils.

Les outils search_models, describe_model, search_records, count_records,
aggregate_records et read_record sont des outils internes sûrs de lecture seule.
Tu n'as pas besoin de demander l'autorisation humaine pour les appeler. Si un
describe_model, search_records, count_records ou aggregate_records peut
raisonnablement réduire l'incertitude,
appelle l'outil au lieu de demander "souhaitez-vous que je le décrive ?".

Demande une clarification utilisateur uniquement lorsque les métadonnées et les
résultats d'outils disponibles ne permettent pas de distinguer sûrement le sens
métier demandé, ou lorsque la demande elle-même reste ambiguë après
investigation sûre.

Évite de répéter le même outil avec les mêmes arguments. Après un search_records
ou count_records réussi qui répond à la demande, produis la réponse finale.

Pour les demandes de classement, fréquence, top, distribution ou "combien par",
utilise aggregate_records lorsque les champs nécessaires sont visibles et sûrs.
Ne présente pas un simple échantillon search_records comme un classement global.

Chaque sortie d'outil peut inclure business_scope_status:
- proven: le modèle, un champ, une relation ou un domaine valide prouve le
  périmètre métier demandé.
- unresolved: les enregistrements sont lisibles mais leur appartenance exacte au
  périmètre métier demandé n'est pas prouvée.
- not_required: la demande ne vise pas un sous-périmètre métier plus étroit.

Si business_scope_status vaut unresolved, ne nomme pas les enregistrements comme
le périmètre métier demandé. Explique brièvement l'ambiguïté ou demande une
précision. Si le résultat est un échantillon, dis "parmi les enregistrements
consultés". Si aggregate_records réussit, tu peux donner un classement exact
sur les groupes retournés.

Si plusieurs modèles restent plausibles et que les résultats ne permettent pas
de trancher, demande une précision. Ne devine pas un modèle.
"""


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _get_item_value(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)

    return getattr(item, key, default)


def _response_output(response):
    if isinstance(response, dict):
        return response.get("output") or []

    return getattr(response, "output", []) or []


def _response_text(response):
    if isinstance(response, dict):
        if response.get("output_text"):
            return str(response.get("output_text") or "").strip()

        chunks = []

        for item in response.get("output") or []:
            if isinstance(item, dict) and item.get("type") == "message":
                for content in item.get("content") or []:
                    if isinstance(content, dict) and content.get("text"):
                        chunks.append(str(content.get("text")))

        return "\n".join(chunks).strip()

    return _extract_text(response)


def _response_id(response):
    if isinstance(response, dict):
        return response.get("id")

    return getattr(response, "id", None)


def _function_calls(response):
    calls = []

    for item in _response_output(response):
        if _get_item_value(item, "type") == "function_call":
            calls.append(item)

    return calls


def _safe_json(value, max_chars: int = 12000):
    text = json.dumps(value, ensure_ascii=False, default=str)

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "...[truncated]"


def _parse_arguments(raw_arguments):
    if isinstance(raw_arguments, dict):
        return raw_arguments

    if not isinstance(raw_arguments, str) or not raw_arguments.strip():
        return {}

    try:
        parsed = json.loads(raw_arguments)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def _successful_data_tool_used(tool_traces: list[dict]):
    return any(
        trace.get("status") == "completed"
        and trace.get("tool") in {
            "odoo.search_records",
            "odoo.count_records",
            "odoo.aggregate_records",
            "odoo.read_record",
        }
        for trace in tool_traces
    )


def _asks_permission_for_internal_read(text: str):
    normalized = (text or "").lower()

    if "souhaitez-vous" not in normalized and "voulez-vous" not in normalized:
        return False

    return any(
        token in normalized
        for token in [
            "affiche",
            "afficher",
            "décrive",
            "decrive",
            "décrire",
            "decrire",
            "liste",
            "lister",
            "recherche",
            "rechercher",
            "compte",
            "compter",
        ]
    )


def execute_odoo_read_tool(tool_name: str, arguments: dict, connector=None):
    connector = connector or odoo
    arguments = _as_dict(arguments)

    if tool_name not in READ_TOOL_NAME_MAP:
        return {
            "status": "denied",
            "tool": tool_name,
            "validation_allowed": False,
            "message": "Unknown or unavailable Odoo read tool.",
        }

    if tool_name == "odoo_search_models":
        result = connector.agent_search_models(arguments.get("query", ""))
    elif tool_name == "odoo_describe_model":
        result = connector.agent_describe_model(arguments.get("model", ""))
    elif tool_name == "odoo_search_records":
        result = connector.agent_search_records(
            model_name=arguments.get("model", ""),
            domain=arguments.get("domain") or [],
            fields=arguments.get("fields") or [],
            limit=arguments.get("limit") or 10,
            order=arguments.get("order"),
        )
    elif tool_name == "odoo_count_records":
        result = connector.agent_count_records(
            model_name=arguments.get("model", ""),
            domain=arguments.get("domain") or [],
        )
    elif tool_name == "odoo_aggregate_records":
        result = connector.agent_aggregate_records(
            model_name=arguments.get("model", ""),
            domain=arguments.get("domain") or [],
            group_by=arguments.get("group_by") or [],
            aggregates=arguments.get("aggregates") or [],
            order_by=arguments.get("order_by") or [],
            limit=arguments.get("limit") or 10,
        )
    elif tool_name == "odoo_read_record":
        result = connector.agent_read_record(
            model_name=arguments.get("model", ""),
            record_id=arguments.get("record_id"),
            fields=arguments.get("fields") or [],
        )

    result = result if isinstance(result, dict) else {}
    result.setdefault("tool", READ_TOOL_NAME_MAP[tool_name])
    result["validation_allowed"] = result.get("status") not in {"denied", "failed"}
    return result


def _tool_trace(tool_name: str, result: dict, iteration: int):
    return {
        "iteration": iteration,
        "tool": result.get("tool") or READ_TOOL_NAME_MAP.get(tool_name, tool_name),
        "validation_allowed": bool(result.get("validation_allowed")),
        "status": result.get("status"),
        "model": result.get("model"),
        "domain": result.get("domain") or result.get("search_domain"),
        "record_count": result.get("record_count"),
        "group_by": result.get("group_by"),
        "group_count": result.get("group_count"),
        "business_scope_status": result.get("business_scope_status"),
        "truncated": result.get("truncated"),
    }


BUSINESS_SCOPE_STOPWORDS = {
    "abroad",
    "about",
    "avec",
    "brouillon",
    "business",
    "cite",
    "citer",
    "dans",
    "des",
    "draft",
    "enregistrement",
    "enregistrements",
    "few",
    "for",
    "in",
    "les",
    "list",
    "liste",
    "moi",
    "odoo",
    "quelques",
    "record",
    "records",
    "show",
    "the",
}


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().split())


def _scope_tokens(value: str | None) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", _normalize_label(value or ""))
    tokens = set()

    for token in normalized.split():
        if len(token) <= 2 or token in BUSINESS_SCOPE_STOPWORDS:
            continue

        tokens.add(token)

        if token.endswith("ies") and len(token) > 4:
            tokens.add(token[:-3] + "y")
        if token.endswith("s") and len(token) > 4:
            tokens.add(token[:-1])
        if token.endswith("es") and len(token) > 4:
            tokens.add(token[:-2])

    return tokens


def _field_metadata(described_models: dict, model_name: str | None, field_name: str | None):
    if not model_name or not field_name:
        return {}

    for field in described_models.get(model_name) or []:
        if isinstance(field, dict) and field.get("name") == field_name:
            return field

    return {}


def _condition_field(condition):
    if isinstance(condition, dict):
        return condition.get("field") or condition.get("field_name") or condition.get("name")

    if isinstance(condition, (list, tuple)) and condition:
        return condition[0]

    return None


def _business_scope_status(read_plan: dict, result: dict, described_models: dict, model_labels: dict):
    model_name = result.get("model")
    tool_name = result.get("tool")

    if tool_name not in {
        "odoo.search_records",
        "odoo.count_records",
        "odoo.aggregate_records",
        "odoo.read_record",
    }:
        return {
            "status": "not_required",
            "reason": "No business data records were returned by this tool.",
            "evidence": [],
        }

    business_text = " ".join(
        str(value or "")
        for value in [
            read_plan.get("business_object"),
            read_plan.get("model_hint"),
        ]
    )
    requested_tokens = _scope_tokens(business_text)

    if not requested_tokens:
        return {
            "status": "not_required",
            "reason": "No narrow business population was requested.",
            "evidence": [],
        }

    model_tokens = _scope_tokens(f"{model_name or ''} {model_labels.get(model_name) or ''}")

    if requested_tokens & model_tokens:
        return {
            "status": "proven",
            "reason": "The validated Odoo model label matches the requested business population.",
            "evidence": [f"model:{model_name}"],
        }

    evidence = []
    used_fields = []

    for condition in result.get("domain") or []:
        field_name = _condition_field(condition)
        if field_name:
            used_fields.append(field_name)

    used_fields.extend(result.get("group_by") or [])

    for field_name in used_fields:
        metadata = _field_metadata(described_models, model_name, field_name)
        field_tokens = _scope_tokens(
            " ".join([
                str(field_name or ""),
                str(metadata.get("label") or ""),
                str(metadata.get("relation") or ""),
            ])
        )

        if requested_tokens & field_tokens:
            evidence.append(f"field:{field_name}")

    if evidence:
        return {
            "status": "proven",
            "reason": "A validated field or domain supports the requested business population.",
            "evidence": evidence[:3],
        }

    return {
        "status": "unresolved",
        "reason": (
            "The records are readable, but no validated model, field, relation or domain "
            "proves that they belong to the requested narrower business population."
        ),
        "evidence": [],
    }


def _with_business_scope(result: dict, read_plan: dict, described_models: dict, model_labels: dict):
    scope = _business_scope_status(read_plan, result, described_models, model_labels)
    enriched = dict(result)
    enriched["business_scope_status"] = scope["status"]
    enriched["business_scope_reason"] = scope["reason"]
    enriched["business_scope_evidence"] = scope["evidence"]
    return enriched


def _latest_record_count(tool_traces: list[dict]) -> int:
    return next(
        (
            trace.get("record_count")
            for trace in reversed(tool_traces)
            if trace.get("record_count") is not None
        ),
        next(
            (
                trace.get("group_count")
                for trace in reversed(tool_traces)
                if trace.get("group_count") is not None
            ),
            0,
        ),
    )


def _latest_business_scope(tool_traces: list[dict]):
    return next(
        (
            trace.get("business_scope_status")
            for trace in reversed(tool_traces)
            if trace.get("business_scope_status")
        ),
        "not_required",
    )


def _unresolved_business_scope_message():
    return (
        "Je peux lire des enregistrements Odoo proches, mais je n'ai pas de champ, "
        "relation ou domaine validé qui prouve qu'ils correspondent exactement au "
        "périmètre métier demandé. Pouvez-vous préciser le modèle Odoo ou le champ "
        "qui définit ce périmètre ?"
    )


def _create_openai_response(
    *,
    input_items,
    tools,
    instructions,
    previous_response_id=None,
    model=None,
    max_tool_calls=1,
):
    selected_model = _get_model(model)
    api_key = _get_api_key()

    if not api_key or OpenAI is None:
        return None, {
            "provider": "openai",
            "model": selected_model,
            "success": False,
            "error": "missing_api_key",
        }

    try:
        client = OpenAI(
            api_key=api_key,
            timeout=_get_timeout(),
        )
        request = {
            "model": selected_model,
            "instructions": instructions,
            "input": input_items,
            "tools": tools,
            "parallel_tool_calls": False,
        }

        if tools:
            request["max_tool_calls"] = max_tool_calls

        if previous_response_id:
            request["previous_response_id"] = previous_response_id

        response = client.responses.create(**request)
        return response, {
            "provider": "openai",
            "model": selected_model,
            "success": True,
            "error": None,
        }
    except Exception as error:
        return None, {
            "provider": "openai",
            "model": selected_model,
            "success": False,
            "error": error.__class__.__name__,
        }


def _final_response_after_tool_limit(
    *,
    input_items,
    previous_response_id,
    provider,
    model,
    tool_traces,
    models_used,
):
    response, metadata = _create_openai_response(
        input_items=input_items,
        tools=[],
        instructions=(
            ODOO_READ_AGENT_INSTRUCTIONS
            + "\nTu as atteint la limite d'outils. Ne demande aucun nouvel outil. "
            "Réponds maintenant en français uniquement avec les résultats d'outils déjà reçus. "
            "Si ces résultats ne suffisent pas, explique précisément la limite sans inventer."
        ),
        previous_response_id=previous_response_id,
    )
    provider = metadata.get("provider") or provider
    model = metadata.get("model") or model

    if not response:
        return None

    final_text = _response_text(response)

    if not final_text:
        return None

    if _latest_business_scope(tool_traces) == "unresolved":
        return {
            "status": "needs_clarification",
            "message": _unresolved_business_scope_message(),
            "tool_used": "odoo_read_agent",
            "tool_sequence": tool_traces,
            "models_used": models_used,
            "record_count": _latest_record_count(tool_traces),
            "business_scope_status": "unresolved",
            "stop_reason": "unresolved_business_scope",
            "provider": provider,
            "model": model,
            "llm_success": True,
            "llm_error": None,
        }

    return {
        "status": "completed",
        "message": final_text,
        "tool_used": "odoo_read_agent",
        "tool_sequence": tool_traces,
        "models_used": models_used,
        "record_count": _latest_record_count(tool_traces),
        "business_scope_status": _latest_business_scope(tool_traces),
        "stop_reason": "final_answer_after_tool_limit",
        "provider": provider,
        "model": model,
        "llm_success": True,
        "llm_error": None,
    }


def run_odoo_read_agent(
    user_message: str,
    read_plan: dict | None = None,
    conversation_context: dict | None = None,
    connector=None,
    max_tool_calls: int = MAX_TOOL_CALLS,
):
    read_plan = read_plan or {}
    conversation_context = conversation_context or {}
    connector = connector or odoo
    tool_traces = []
    models_used = []
    described_models = {}
    model_labels = {}
    provider = "openai"
    model = _get_model()

    initial_input = [
        {
            "role": "user",
            "content": (
                f"Demande utilisateur: {user_message}\n"
                f"Plan sémantique initial: {_safe_json(read_plan, 3000)}\n"
                f"Contexte conversationnel sûr: {_safe_json(conversation_context, 2000)}"
            ),
        }
    ]
    previous_response_id = None
    input_items = initial_input

    for iteration in range(1, max_tool_calls + 1):
        response, metadata = _create_openai_response(
            input_items=input_items,
            tools=ODOO_READ_AGENT_TOOLS,
            instructions=ODOO_READ_AGENT_INSTRUCTIONS,
            previous_response_id=previous_response_id,
        )
        provider = metadata.get("provider") or provider
        model = metadata.get("model") or model

        if not response:
            return {
                "status": "failed",
                "message": "Le service OpenAI n’est pas disponible pour cette lecture Odoo.",
                "tool_used": "odoo_read_agent",
                "tool_sequence": tool_traces,
                "models_used": models_used,
                "record_count": 0,
                "stop_reason": "provider_error",
                "provider": provider,
                "model": model,
                "llm_success": False,
                "llm_error": metadata.get("error"),
            }

        previous_response_id = _response_id(response)
        calls = _function_calls(response)

        if not calls:
            final_text = _response_text(response)

            if final_text:
                if (
                    len(tool_traces) < max_tool_calls
                    and not _successful_data_tool_used(tool_traces)
                    and _asks_permission_for_internal_read(final_text)
                ):
                    input_items = [
                        {
                            "role": "user",
                            "content": (
                                "Tu viens de demander l'autorisation d'utiliser un outil interne sûr de lecture. "
                                "Ne demande pas cette permission. Continue maintenant avec le prochain outil "
                                "read-only approprié, ou demande une clarification seulement si les métadonnées "
                                "ne permettent pas de distinguer le sens métier."
                            ),
                        }
                    ]
                    continue

                if _latest_business_scope(tool_traces) == "unresolved":
                    return {
                        "status": "needs_clarification",
                        "message": _unresolved_business_scope_message(),
                        "tool_used": "odoo_read_agent",
                        "tool_sequence": tool_traces,
                        "models_used": models_used,
                        "record_count": _latest_record_count(tool_traces),
                        "business_scope_status": "unresolved",
                        "stop_reason": "unresolved_business_scope",
                        "provider": provider,
                        "model": model,
                        "llm_success": True,
                        "llm_error": None,
                    }

                return {
                    "status": "completed",
                    "message": final_text,
                    "tool_used": "odoo_read_agent",
                    "tool_sequence": tool_traces,
                    "models_used": models_used,
                    "record_count": _latest_record_count(tool_traces),
                    "business_scope_status": _latest_business_scope(tool_traces),
                    "stop_reason": "final_answer",
                    "provider": provider,
                    "model": model,
                    "llm_success": True,
                    "llm_error": None,
                }

            return {
                "status": "failed",
                "message": "Je n’ai pas pu produire une réponse Odoo fiable.",
                "tool_used": "odoo_read_agent",
                "tool_sequence": tool_traces,
                "models_used": models_used,
                "record_count": 0,
                "stop_reason": "empty_final_answer",
                "provider": provider,
                "model": model,
                "llm_success": False,
                "llm_error": "empty_final_answer",
            }

        tool_outputs = []

        for call in calls:
            if len(tool_traces) >= max_tool_calls:
                break

            tool_name = _get_item_value(call, "name")
            call_id = _get_item_value(call, "call_id")
            arguments = _parse_arguments(_get_item_value(call, "arguments"))
            result = execute_odoo_read_tool(tool_name, arguments, connector=connector)
            result = _with_business_scope(result, read_plan, described_models, model_labels)

            if result.get("tool") == "odoo.search_models":
                for model_item in result.get("models") or []:
                    if isinstance(model_item, dict) and model_item.get("model"):
                        model_labels[model_item["model"]] = model_item.get("label") or model_item.get("model")

            if result.get("tool") == "odoo.describe_model" and result.get("model"):
                described_models[result["model"]] = result.get("fields") or []
                model_labels[result["model"]] = result.get("label") or result.get("model")

            trace = _tool_trace(tool_name, result, len(tool_traces) + 1)
            tool_traces.append(trace)

            if trace.get("model") and trace["model"] not in models_used:
                models_used.append(trace["model"])

            if not result.get("validation_allowed"):
                if tool_name in READ_TOOL_NAME_MAP and len(tool_traces) < max_tool_calls:
                    tool_outputs.append({
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": _safe_json(result),
                    })
                    continue

                return {
                    "status": "needs_clarification" if result.get("status") == "denied" else "failed",
                    "message": (
                        "Je ne peux pas identifier ou lire ce périmètre Odoo de manière sûre. "
                        "Pouvez-vous préciser le type d’enregistrement attendu ?"
                    ),
                    "tool_used": "odoo_read_agent",
                    "tool_sequence": tool_traces,
                    "models_used": models_used,
                    "record_count": 0,
                    "business_scope_status": _latest_business_scope(tool_traces),
                    "stop_reason": "validation_denied",
                    "provider": provider,
                    "model": model,
                    "llm_success": True,
                    "llm_error": None,
                }

            tool_outputs.append({
                "type": "function_call_output",
                "call_id": call_id,
                "output": _safe_json(result),
            })

        if not tool_outputs:
            break

        input_items = tool_outputs

        if len(tool_traces) >= max_tool_calls:
            final_result = _final_response_after_tool_limit(
                input_items=input_items,
                previous_response_id=previous_response_id,
                provider=provider,
                model=model,
                tool_traces=tool_traces,
                models_used=models_used,
            )

            if final_result:
                return final_result

            break

    return {
        "status": "needs_clarification",
        "message": (
            "Je n’ai pas pu terminer la lecture Odoo dans la limite de sécurité. "
            "Pouvez-vous préciser le type d’enregistrement ou le filtre recherché ?"
        ),
        "tool_used": "odoo_read_agent",
        "tool_sequence": tool_traces,
        "models_used": models_used,
        "record_count": _latest_record_count(tool_traces),
        "business_scope_status": _latest_business_scope(tool_traces),
        "stop_reason": "max_tool_calls",
        "provider": provider,
        "model": model,
        "llm_success": False,
        "llm_error": "max_tool_calls",
    }
