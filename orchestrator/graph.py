from orchestrator.router import (
    select_model,
    select_agent
)

from orchestrator.intent_classifier import classify_with_confidence

from orchestrator.audit import log_request
from orchestrator.approval import requires_approval
from orchestrator.approval_store import create_approval

from models.openai_adapter import ask_gpt
from models.claude_adapter import ask_claude
from models.gemini_adapter import ask_gemini

from agents.odoo_agent import run as run_odoo_agent
from agents.support_agent import run as run_support_agent
from agents.knowledge_agent import run as run_knowledge_agent


def call_model(model: str, prompt: str):

    if model == "gpt":
        return ask_gpt(prompt)

    if model == "claude":
        return ask_claude(prompt)

    if model == "gemini":
        return ask_gemini(prompt)

    return ask_gpt(prompt)


def process_request(message: str):

    # Intent Classification

    classification = classify_with_confidence(message)

    intent = classification["intent"]
    confidence = classification["confidence"]

    # Routing

    selected_agent = select_agent(intent)
    selected_model = select_model(intent)

    # Approval Detection

    approval_required = requires_approval(message)
    approval = None

    if approval_required:
        approval = create_approval(
            user_message=message,
            intent=intent,
            selected_agent=selected_agent,
            selected_model=selected_model
        )

    # Agent Execution

    if selected_agent == "odoo_agent":
        agent_result = run_odoo_agent(message)

    elif selected_agent == "support_agent":
        agent_result = run_support_agent(message)

    elif selected_agent == "knowledge_agent":
        agent_result = run_knowledge_agent(message)

    else:
        agent_result = {
            "agent": "general",
            "result": message
        }

    # Build Prompt

    prompt = f"""
You are the selected model: {selected_model}.

Intent:
{intent}

Confidence:
{confidence}

Selected agent:
{selected_agent}

User request:
{message}

Agent result:
{agent_result}

Approval required:
{approval_required}

Provide a concise response.
"""

    # Model Execution

    response = call_model(selected_model, prompt)

    # Audit Logging

    log_request({
        "user_message": message,
        "intent": intent,
        "classification_confidence": confidence,
        "selected_agent": selected_agent,
        "selected_model": selected_model,
        "approval_required": approval_required,
        "approval_status": (
            "pending"
            if approval_required
            else "not_required"
        ),
        "approval_id": (
            approval["id"]
            if approval
            else None
        ),
        "agent_result": agent_result
    })

    # Final Response

    return {
        "intent": intent,
        "classification_confidence": confidence,
        "selected_agent": selected_agent,
        "selected_model": selected_model,
        "approval_required": approval_required,
        "approval_status": (
            "pending"
            if approval_required
            else "not_required"
        ),
        "approval": approval,
        "agent_result": agent_result,
        "response": response
    }