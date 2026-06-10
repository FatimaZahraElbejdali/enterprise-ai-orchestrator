import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi import HTTPException
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
        logs = []
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                logs.append({
                    "line": line_number,
                    "error": "Invalid audit log entry"
                })

        return logs


@app.get("/approvals")
def approvals():
    return get_approvals()


@app.post("/approvals/{approval_id}/approve")
def approve_approval(approval_id: str):
    approval = update_approval_status(approval_id, "approved")

    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")

    return approval


@app.post("/approvals/{approval_id}/reject")
def reject_approval(approval_id: str):
    approval = update_approval_status(approval_id, "rejected")

    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")

    return approval
