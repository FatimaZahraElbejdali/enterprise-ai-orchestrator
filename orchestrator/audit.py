import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

from orchestrator.auth import get_audit_user_context

LOG_PATH = Path("logs/audit_log.jsonl")

IMPORTANT_EVENT_TYPES = {
    "approval_required",
    "approval_decision",
    "odoo_write_executed",
    "odoo_write_requested",
    "permission_denied",
    "department_access_denied",
    "unsupported_action",
    "unsupported_capability",
    "official_web_ingestion_rejected",
}

IMPORTANT_STATUSES = {
    "access_denied",
    "blocked",
    "denied",
    "department_access_denied",
    "failed",
    "pending_approval",
    "rejected",
    "security_blocked",
    "unsupported",
}


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


def is_important_audit_event(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False

    event_type = str(entry.get("event_type") or "")
    status = str(entry.get("status") or "")
    risk = str(entry.get("risk") or entry.get("risk_level") or "")
    approval_status = str(entry.get("approval_status") or "")
    permission_decision = str(entry.get("permission_decision") or "")
    system = str(entry.get("system") or entry.get("target_system") or "")

    if event_type in IMPORTANT_EVENT_TYPES:
        return True

    if status in IMPORTANT_STATUSES:
        return True

    if approval_status in {"pending", "approved", "rejected", "requires_approval"}:
        return True

    if permission_decision in {"denied", "department_denied"}:
        return True

    if risk == "blocked":
        return True

    if system == "odoo" and status in {"failed", "error", "unsupported"}:
        return True

    return False
