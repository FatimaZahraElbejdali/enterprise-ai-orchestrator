from orchestrator.router import classify_intent, select_model, select_agent

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

    prompt = f"""
You are the selected model: {selected_model}.
The selected agent is: {selected_agent}.
The user request is: {message}.
The agent result is: {agent_result}.

Return a concise final answer.
"""

    response = call_model(selected_model, prompt)

    return {
        "intent": intent,
        "selected_agent": selected_agent,
        "selected_model": selected_model,
        "agent_result": agent_result,
        "response": response
    }