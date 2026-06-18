from orchestrator.classifier_router import classify_message

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


AGENT_RUNNERS = {
    "odoo_agent": run_odoo_agent,
    "support_agent": run_support_agent,
    "knowledge_agent": run_knowledge_agent,
    "development_agent": run_development_agent,
    "security_agent": run_security_agent,
    "server_agent": run_server_agent,
}


def _fallback_response(model_route: dict, agent_result: dict | str):
    reason = model_route.get("reason", "OpenAI is not configured.")

    return {
        "provider": "local_fallback",
        "model": model_route.get("model", "local"),
        "success": False,
        "content": (
            "OpenAI is not configured or unavailable. "
            "The local Enterprise AI Orchestrator policy handled the request without executing sensitive actions."
        ),
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

    return {
        "agent": "general",
        "tool_used": "none",
        "result": message
    }


def process_request(message: str):
    if not message or not message.strip():
        return {
            "error": "Message cannot be empty"
        }

    classification = classify_message(message)

    intent = classification.get("intent", "general")
    selected_agent = classification.get("selected_agent", "general_agent")
    confidence = classification.get("confidence", 0.0)
    classifier_source = classification.get("classifier_source")
    classifier_error = classification.get("classifier_error")

    classification_failed = classifier_source == "gemini_failed"

    risk_level = classify_risk(message)
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
        "risk_level": risk_level,
        "classification_confidence": confidence,
        "selected_agent": selected_agent,
        "selected_model": selected_model,
        "execution_plan": execution_plan,
        "approval_required": approval_required,
        "approval_status": "pending" if approval_required else "not_required",
        "approval": approval,
        "agent_result": agent_result,
        "response": response,
        "message": response.get("content") if isinstance(response, dict) else response,
        "classifier_source": classifier_source,
        "classifier_error": classifier_error
    }
