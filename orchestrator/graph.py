from orchestrator.classifier_router import classify_message

from orchestrator.router import select_model
from orchestrator.audit import log_request
from orchestrator.approval import requires_approval
from orchestrator.approval_store import create_approval

from models.openai_adapter import ask_gpt
from models.claude_adapter import ask_claude
from models.gemini_adapter import ask_gemini

from agents.odoo_agent import run as run_odoo_agent
from agents.support_agent import run as run_support_agent
from agents.knowledge_agent import run as run_knowledge_agent
from agents.development_agent import run as run_development_agent
from agents.security_agent import run as run_security_agent
from agents.server_agent import run as run_server_agent


def call_model(model: str, prompt: str):

    if model == "gpt":
        return ask_gpt(prompt)

    if model == "claude":
        return ask_claude(prompt)

    if model == "gemini":
        return ask_gemini(prompt)

    return ask_gpt(prompt)


AGENT_RUNNERS = {
    "odoo_agent": run_odoo_agent,
    "support_agent": run_support_agent,
    "knowledge_agent": run_knowledge_agent,
    "development_agent": run_development_agent,
    "security_agent": run_security_agent,
    "server_agent": run_server_agent,
}


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
    approval_required = False if classification_failed else requires_approval(message)

    # If Gemini explicitly detects approval need, also respect that.
    if not classification_failed and classification.get("requires_approval") is True:
        approval_required = True

    selected_model = select_model(intent)

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
You are the selected model: {selected_model}.

Intent:
{intent}

Classification confidence:
{confidence}

Selected agent:
{selected_agent}

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

    response = call_model(selected_model, prompt)

    log_request({
        "user_message": message,
        "intent": intent,
        "classification_confidence": confidence,
        "selected_agent": selected_agent,
        "selected_model": selected_model,
        "classifier_source": classifier_source,
        "classifier_error": classifier_error,
        "approval_required": approval_required,
        "approval_status": "pending" if approval_required else "not_required",
        "approval_id": approval["id"] if approval else None,
        "agent_result": agent_result
    })

    return {
        "intent": intent,
        "classification_confidence": confidence,
        "selected_agent": selected_agent,
        "selected_model": selected_model,
        "approval_required": approval_required,
        "approval_status": "pending" if approval_required else "not_required",
        "approval": approval,
        "agent_result": agent_result,
        "response": response,
        "classifier_source": classifier_source,
        "classifier_error": classifier_error
    }
