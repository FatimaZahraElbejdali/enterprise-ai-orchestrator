import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from pydantic import BaseModel

from orchestrator.graph import process_request
from orchestrator.approval_store import (
    get_approvals,
    update_approval_status
)


app = FastAPI(
    title="AI Orchestrator API",
    version="0.1.0"
)


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def home():
    return {
        "message": "AI Orchestrator API is running"
    }


@app.get("/status")
def status():
    return {
        "status": "online",
        "service": "AI Orchestrator",
        "version": "0.1.0",
        "features": {
            "intent_classification": True,
            "agent_routing": True,
            "model_routing": True,
            "audit_logging": True,
            "approval_detection": True,
            "approval_storage": True,
            "real_model_apis": False,
            "odoo_integration": False
        }
    }


@app.post("/chat")
def chat(request: ChatRequest):
    return process_request(request.message)


@app.get("/logs")
def get_logs():
    log_path = Path("logs/audit_log.jsonl")

    if not log_path.exists():
        return []

    with open(log_path, "r") as file:
        return [
            json.loads(line)
            for line in file
            if line.strip()
        ]


@app.get("/approvals")
def approvals():
    return get_approvals()


@app.post("/approvals/{approval_id}/approve")
def approve_approval(approval_id: str):
    approval = update_approval_status(approval_id, "approved")

    if approval is None:
        return {
            "error": "Approval not found"
        }

    return approval


@app.post("/approvals/{approval_id}/reject")
def reject_approval(approval_id: str):
    approval = update_approval_status(approval_id, "rejected")

    if approval is None:
        return {
            "error": "Approval not found"
        }

    return approval