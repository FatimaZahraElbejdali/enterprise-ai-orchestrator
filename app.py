import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.odoo_agent import run as run_odoo_agent
from integrations.odoo_connector import OdooConnector
from models.openai_adapter import (
    generate_response,
    get_openai_status,
    is_openai_configured,
)
from orchestrator.graph import process_request
from orchestrator.audit import log_request
from orchestrator.approval_store import (
    get_approvals,
    update_approval_status,
)

load_dotenv()

app = FastAPI(
    title="Enterprise AI Orchestrator API",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

odoo = OdooConnector()


class ChatRequest(BaseModel):
    message: str


class AITestRequest(BaseModel):
    message: str


def is_odoo_related(message: str) -> bool:
    text = message.lower()

    keywords = [
        "odoo",
        "stock",
        "inventory",
        "inventaire",
        "product",
        "produit",
        "price",
        "prix",
        "unit",
        "unité",
        "unite",
        "invoice",
        "facture",
        "customer",
        "client",
        "purchase",
        "achat",
        "commande",
    ]

    return any(keyword in text for keyword in keywords)


@app.get("/")
def home():
    return {
        "message": "Enterprise AI Orchestrator API is running",
        "status": "online",
    }


@app.get("/status")
def status():
    return {
        "status": "online",
        "service": "Enterprise AI Orchestrator",
        "version": "0.2.0",
        "features": {
            "intent_classification": True,
            "agent_routing": True,
            "model_routing": True,
            "audit_logging": True,
            "approval_detection": True,
            "approval_storage": True,
            "real_model_apis": is_openai_configured(),
            "odoo_connector": True,
            "odoo_real_integration": True,
            "sensitive_action_blocking": True,
        },
    }


@app.get("/ai/providers")
def ai_providers():
    openai_status = get_openai_status()

    return {
        "openai": openai_status,
        "default_provider": "openai" if openai_status["configured"] else "mock",
    }


@app.post("/ai/test")
def ai_test(request: AITestRequest):
    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty",
        )

    if not is_openai_configured():
        status_info = get_openai_status()

        return {
            "provider": "openai",
            "model": status_info["model"],
            "success": False,
            "content": "",
            "error": "missing_api_key",
            "status": status_info["status"],
        }

    response = generate_response(
        prompt=message,
        system_prompt=(
            "You are testing the Enterprise AI Orchestrator OpenAI provider. "
            "Reply briefly and do not execute any enterprise action."
        ),
    )

    log_request({
        "event_type": "ai_model_call",
        "provider": "openai",
        "model": response.get("model"),
        "agent": "general_agent",
        "status": "completed" if response.get("success") else "failed",
        "risk": "low",
        "approval_status": "not_required",
    })

    return response


@app.post("/chat")
def chat(request: ChatRequest):
    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty",
        )

    if is_odoo_related(message):
        return run_odoo_agent(message)

    return process_request(message)


@app.get("/logs")
def get_logs():
    log_path = Path("logs/audit_log.jsonl")

    if not log_path.exists():
        return []

    logs = []

    with open(log_path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(entry, dict):
                continue

            title = entry.get("title")
            message = entry.get("message")

            if title == "string" or message == "string":
                continue

            logs.append(entry)

    return sorted(
        logs,
        key=lambda item: item.get("timestamp", ""),
        reverse=True,
    )


@app.get("/approvals")
def approvals():
    return get_approvals()


@app.post("/approvals/{approval_id}/approve")
def approve_approval(approval_id: str):
    approval = update_approval_status(approval_id, "approved")

    if approval is None:
        raise HTTPException(
            status_code=404,
            detail="Approval not found",
        )

    log_request({
        "event_type": "approval_decision",
        "title": "Demande approuvée",
        "system": approval.get("source_system", "orchestrator"),
        "agent": approval.get("selected_agent", "orchestrator"),
        "status": "approved",
        "risk": approval.get("risk", "medium"),
        "approval_status": "approved",
        "approval_id": approval.get("id"),
        "user_message": approval.get("user_message"),
        "action": approval.get("action"),
        "product": approval.get("entity_name"),
        "requested_value": approval.get("requested_change"),
        "executed": False,
        "message": "La demande a été approuvée. L’exécution réelle reste désactivée dans cette phase de démonstration.",
    })

    return approval


@app.post("/approvals/{approval_id}/reject")
def reject_approval(approval_id: str):
    approval = update_approval_status(approval_id, "rejected")

    if approval is None:
        raise HTTPException(
            status_code=404,
            detail="Approval not found",
        )

    log_request({
        "event_type": "approval_decision",
        "title": "Demande rejetée",
        "system": approval.get("source_system", "orchestrator"),
        "agent": approval.get("selected_agent", "orchestrator"),
        "status": "rejected",
        "risk": approval.get("risk", "medium"),
        "approval_status": "rejected",
        "approval_id": approval.get("id"),
        "user_message": approval.get("user_message"),
        "action": approval.get("action"),
        "product": approval.get("entity_name"),
        "requested_value": approval.get("requested_change"),
        "executed": False,
        "message": "La demande a été rejetée. Aucune modification Odoo n’a été exécutée.",
    })

    return approval


@app.get("/odoo/status")
def odoo_status():
    return odoo.test_connection()


@app.get("/odoo/stock/{product_name}")
def odoo_stock(product_name: str):
    return odoo.check_stock(product_name)


@app.get("/odoo/product/{product_name}")
def odoo_product(product_name: str):
    return odoo.check_stock(product_name)
