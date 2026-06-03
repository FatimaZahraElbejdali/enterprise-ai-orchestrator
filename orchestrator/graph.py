from orchestrator.router import (
    classify_intent,
    select_model,
    select_agent
)

from orchestrator.audit import log_request

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

    intent = classify_intent(message)

    selected_agent = select_agent(intent)

    selected_model = select_model(intent)

    # Execute agent

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

    # Build prompt for model

    prompt = f"""
You are the selected model: {selected_model}.

Selected agent:
{selected_agent}

User request:
{message}

Agent result:
{agent_result}

Provide a concise response.
"""

    response = call_model(selected_model, prompt)

    # Audit log

    log_request({
        "user_message": message,
        "intent": intent,
        "selected_agent": selected_agent,
        "selected_model": selected_model,
        "agent_result": agent_result,
        "response": response
    })

    return {
        "intent": intent,
        "selected_agent": selected_agent,
        "selected_model": selected_model,
        "agent_result": agent_result,
        "response": response
    }