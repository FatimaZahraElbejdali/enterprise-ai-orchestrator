from orchestrator.classifier_router import (
    apply_backend_safety_overrides,
    classify_message,
)

from orchestrator.model_router import select_model
from orchestrator.risk import classify_risk, requires_approval_for_risk
from orchestrator.audit import log_request
from orchestrator.approval import requires_approval
from orchestrator.approval_store import create_approval
from orchestrator.planner import create_plan

from models.openai_adapter import generate_response

from agents.odoo_agent import run as run_odoo_agent
from agents.support_agent import run as run_support_agent
from agents.knowledge_agent import run as run_knowledge_agent
from agents.development_agent import run as run_development_agent
from agents.security_agent import run as run_security_agent
from agents.server_agent import run as run_server_agent


UNSUPPORTED_MESSAGE = (
    "Je comprends votre demande, mais cette action n’est pas encore disponible "
    "dans les outils autorisés de l’orchestrateur. Vous pouvez me demander de "
    "consulter Odoo, modifier des données Odoo avec validation, diagnostiquer "
    "un problème IT ou accéder aux fichiers du serveur interne."
)


def _general_answer(message: str):
    text = message.lower()

    if "orchestrateur" in text or "orchestrator" in text:
        return (
            "L’orchestrateur IA sert à comprendre une demande métier, choisir le bon agent, "
            "appliquer les règles de sécurité et tracer chaque décision. Il permet d’utiliser "
            "l’IA sans lui donner un accès direct et incontrôlé aux systèmes sensibles."
        )

    if "validation humaine" in text or "human approval" in text:
        return (
            "La validation humaine protège les actions sensibles: l’orchestrateur prépare la "
            "modification, crée une demande de validation, puis attend une décision humaine "
            "avant toute exécution réelle."
        )

    if "traçabilité" in text or "tracabilite" in text or "traceability" in text:
        return (
            "La traçabilité permet de savoir qui a demandé quoi, quel agent a répondu, si une "
            "validation était nécessaire et quel résultat a été obtenu. C’est essentiel pour "
            "l’audit, la conformité et la confiance."
        )

    return UNSUPPORTED_MESSAGE


def _format_agent_content(agent_result):
    if not isinstance(agent_result, dict):
        return str(agent_result)

    direct_response = agent_result.get("response") or agent_result.get("message")

    if isinstance(direct_response, str) and direct_response.strip():
        return direct_response

    result = agent_result.get("result")

    if isinstance(result, str):
        return result

    if not isinstance(result, dict):
        return (
            "The local Enterprise AI Orchestrator policy handled the request "
            "without executing sensitive actions."
        )

    diagnosis = result.get("diagnosis")
    suggested_steps = result.get("suggested_steps")

    if diagnosis and isinstance(suggested_steps, list):
        steps = "; ".join(str(step) for step in suggested_steps)
        return f"Diagnostic: {diagnosis}. Actions recommandées: {steps}."

    summary = result.get("summary")
    next_steps = result.get("next_steps") or result.get("recommended_actions")

    if summary and isinstance(next_steps, list):
        steps = "; ".join(str(step) for step in next_steps)
        return f"{summary} Actions recommandées: {steps}."

    status = result.get("status")

    if status:
        return f"Demande traitée par l’agent local. Statut: {status}."

    return (
        "Demande traitée par l’agent local. Consultez la réponse brute pour les détails."
    )


AGENT_RUNNERS = {
    "odoo_agent": run_odoo_agent,
    "support_agent": run_support_agent,
    "knowledge_agent": run_knowledge_agent,
    "development_agent": run_development_agent,
    "security_agent": run_security_agent,
    "server_agent": run_server_agent,
}


def _blocked_security_response(message: str, classification: dict):
    reason = classification.get("reason") or "Backend safety policy blocked this request."
    intent = classification.get("intent", "sensitive_secret_request")

    safe_message = (
        "Je ne peux pas aider à afficher, extraire ou exécuter cette demande sensible. "
        "L’orchestrateur a bloqué la requête pour protéger les secrets, les accès et les systèmes."
    )

    if intent == "destructive_operation_blocked":
        safe_message = (
            "Je ne peux pas exécuter ni préparer cette opération destructive. "
            "L’orchestrateur a bloqué la requête afin d’éviter une action dangereuse ou irréversible."
        )

    agent_result = {
        "agent": "security_agent",
        "parser_source": "backend_safety_override",
        "parsed_action": "block_request",
        "tool_used": "none",
        "status": "blocked",
        "result": {
            "blocked": True,
            "reason": reason,
        },
        "message": safe_message,
        "response": safe_message,
    }

    return {
        "intent": intent,
        "agent": "security_agent",
        "risk_level": "blocked",
        "risk": "blocked",
        "classification_confidence": classification.get("confidence", "high"),
        "selected_agent": "security_agent",
        "selected_model": {
            "provider": "local_fallback",
            "model": "backend_safety_policy",
            "reason": "Backend safety override blocked the request before tool execution.",
        },
        "execution_plan": [
            "apply_backend_safety_policy",
            "block_sensitive_or_dangerous_request",
            "return_safe_explanation",
        ],
        "approval_required": False,
        "requires_approval": False,
        "approval_status": "not_required",
        "approval": None,
        "agent_result": agent_result,
        "tool_used": "none",
        "result": agent_result["result"],
        "response": {
            "provider": "local_fallback",
            "model": "backend_safety_policy",
            "success": True,
            "content": safe_message,
            "error": None,
            "agent_result": agent_result,
        },
        "message": safe_message,
        "status": "blocked",
        "parser_source": "backend_safety_override",
        "parsed_action": "block_request",
        "classifier_source": classification.get("classifier_source"),
        "classifier_error": classification.get("classifier_error"),
        "action": "block_request",
        "target_system": "security",
        "entities": classification.get("entities", {}),
        "reason": reason,
    }


def _fallback_response(model_route: dict, agent_result: dict | str):
    reason = model_route.get("reason", "OpenAI is not configured.")

    return {
        "provider": "local_fallback",
        "model": model_route.get("model", "local"),
        "success": False,
        "content": _format_agent_content(agent_result),
        "error": reason,
        "agent_result": agent_result,
    }


def _log_openai_call(model_route: dict, selected_agent: str, status: str):
    log_request({
        "event_type": "ai_model_call",
        "provider": "openai",
        "model": model_route.get("model"),
        "agent": selected_agent or "general_agent",
        "status": status,
        "risk": "low",
        "approval_status": "not_required",
    })


def call_model(model_route: dict, prompt: str, selected_agent: str, agent_result):
    if model_route.get("provider") != "openai":
        return _fallback_response(model_route, agent_result)

    response = generate_response(
        prompt,
        system_prompt=(
            "You are the general reasoning layer for the Enterprise AI Orchestrator. "
            "Explain, summarize, and assist. Do not approve, execute, or bypass enterprise actions."
        ),
        model=model_route.get("model"),
    )

    _log_openai_call(
        model_route=model_route,
        selected_agent=selected_agent,
        status="completed" if response.get("success") else "failed",
    )

    if not response.get("success"):
        fallback = _fallback_response(model_route, agent_result)
        fallback["provider"] = "openai"
        fallback["model"] = response.get("model", model_route.get("model"))
        fallback["error"] = response.get("error")
        return fallback

    return response


def run_selected_agent(selected_agent: str, message: str):
    runner = AGENT_RUNNERS.get(selected_agent)

    if runner:
        return runner(message)

    answer = _general_answer(message)

    return {
        "agent": "general_agent",
        "parser_source": "general_fallback",
        "parsed_action": "answer_general_question" if answer != UNSUPPORTED_MESSAGE else "unknown",
        "tool_used": "none",
        "result": {
            "answer": answer,
        },
        "response": answer,
        "message": answer,
    }


def process_request(message: str, classification: dict | None = None):
    if not message or not message.strip():
        return {
            "error": "Message cannot be empty"
        }

    classification = classification or classify_message(message)
    classification = apply_backend_safety_overrides(message, classification) or classification

    intent = classification.get("intent", "general")
    selected_agent = classification.get("selected_agent", "general_agent")
    confidence = classification.get("confidence", 0.0)
    classifier_source = classification.get("classifier_source")
    classifier_error = classification.get("classifier_error")

    classification_failed = (
        intent == "classification_failed"
        or classifier_source in {"gemini_failed", "openai_failed"}
    )

    risk_level = classification.get("risk_level") or classify_risk(message)

    if risk_level == "blocked" or selected_agent == "security_agent" and classification.get("action") == "block_request":
        result = _blocked_security_response(message, classification)
        log_request({
            "user_message": message,
            "intent": result["intent"],
            "risk_level": "blocked",
            "classification_confidence": confidence,
            "selected_agent": "security_agent",
            "selected_model": result["selected_model"],
            "execution_plan": result["execution_plan"],
            "classifier_source": classifier_source,
            "classifier_error": classifier_error,
            "approval_required": False,
            "approval_status": "not_required",
            "approval_id": None,
            "agent_result": result["agent_result"],
        })
        return result

    selected_model = select_model(intent, risk_level)
    execution_plan = create_plan(intent, message, risk_level)

    approval_required = False

    if not classification_failed:
        approval_required = (
            requires_approval_for_risk(risk_level)
            or requires_approval(message)
            or classification.get("requires_approval") is True
        )

    approval = None

    if approval_required:
        approval = create_approval(
            user_message=message,
            intent=intent,
            selected_agent=selected_agent,
            selected_model=selected_model
        )

    agent_result = run_selected_agent(
        selected_agent=selected_agent,
        message=message
    )
    agent_parser_source = (
        agent_result.get("parser_source")
        if isinstance(agent_result, dict)
        else None
    )
    agent_parsed_action = (
        agent_result.get("parsed_action")
        if isinstance(agent_result, dict)
        else None
    )

    prompt = f"""
Selected model route:
{selected_model}

Intent:
{intent}

Risk level:
{risk_level}

Classification confidence:
{confidence}

Selected agent:
{selected_agent}

Execution plan:
{execution_plan}

Classifier source:
{classifier_source}

Classifier error:
{classifier_error}

User request:
{message}

Agent result:
{agent_result}

Approval required:
{approval_required}

Provide a concise final response for the user.
"""

    response = call_model(
        model_route=selected_model,
        prompt=prompt,
        selected_agent=selected_agent,
        agent_result=agent_result,
    )

    log_request({
        "user_message": message,
        "intent": intent,
        "risk_level": risk_level,
        "classification_confidence": confidence,
        "selected_agent": selected_agent,
        "selected_model": selected_model,
        "execution_plan": execution_plan,
        "classifier_source": classifier_source,
        "classifier_error": classifier_error,
        "approval_required": approval_required,
        "approval_status": "pending" if approval_required else "not_required",
        "approval_id": approval["id"] if approval else None,
        "agent_result": agent_result
    })

    return {
        "intent": intent,
        "agent": selected_agent,
        "risk_level": risk_level,
        "risk": risk_level,
        "classification_confidence": confidence,
        "selected_agent": selected_agent,
        "selected_model": selected_model,
        "execution_plan": execution_plan,
        "approval_required": approval_required,
        "approval_status": "pending" if approval_required else "not_required",
        "approval": approval,
        "agent_result": agent_result,
        "tool_used": agent_result.get("tool_used") if isinstance(agent_result, dict) else None,
        "result": agent_result.get("result") if isinstance(agent_result, dict) else agent_result,
        "response": response,
        "message": response.get("content") if isinstance(response, dict) else response,
        "parser_source": agent_parser_source,
        "parsed_action": agent_parsed_action,
        "classifier_source": classifier_source,
        "classifier_error": classifier_error,
        "action": classification.get("action"),
        "target_system": classification.get("target_system"),
        "entities": classification.get("entities", {}),
        "reason": classification.get("reason"),
        "status": (
            "pending_approval"
            if approval_required
            else (
                agent_result.get("status")
                if isinstance(agent_result, dict) and agent_result.get("status")
                else "completed"
            )
        ),
    }
