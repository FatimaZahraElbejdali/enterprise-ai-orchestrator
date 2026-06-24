import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

from orchestrator.auth import get_audit_user_context

LOG_PATH = Path("logs/audit_log.jsonl")


def _utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


def log_request(data: dict):
    LOG_PATH.parent.mkdir(exist_ok=True)
    audit_user_context = get_audit_user_context() or {}

    if not isinstance(data, dict):
        data = {
            "event_type": "legacy_event",
            "title": "Ancien événement journalisé",
            "message": str(data),
        }

    log_entry = {
        "id": str(uuid.uuid4()),
        "timestamp": _utc_timestamp(),
        "event_type": data.get("event_type", "system_event"),
        "title": data.get("title", "Événement système"),
        "system": data.get("system", "orchestrator"),
        "agent": data.get("agent", "orchestrator"),
        "status": data.get("status", "logged"),
        "risk": data.get("risk", "low"),
        "approval_status": data.get("approval_status", "not_required"),
        **audit_user_context,
        **data,
    }

    with open(LOG_PATH, "a", encoding="utf-8") as file:
        file.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
