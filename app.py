from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from pydantic import BaseModel

from orchestrator.graph import process_request

app = FastAPI()


class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
def chat(request: ChatRequest):

    return process_request(
        request.message
    )
@app.get("/")
def home():
    return {
        "message": "AI Orchestrator API is running"
    }
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
            "real_model_apis": False,
            "odoo_integration": False
        }
    }