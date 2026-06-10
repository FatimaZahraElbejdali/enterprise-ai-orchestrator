import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

APPROVALS_FILE = Path("logs/approvals.json")
VALID_STATUSES = {"pending", "approved", "rejected"}


def _utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


def _load_approvals():
    if not APPROVALS_FILE.exists():
        return []

    with open(APPROVALS_FILE, "r") as file:
        try:
            approvals = json.load(file)
        except json.JSONDecodeError:
            return []

    if not isinstance(approvals, list):
        return []

    return approvals


def _save_approvals(approvals):
    APPROVALS_FILE.parent.mkdir(exist_ok=True)

    with open(APPROVALS_FILE, "w") as file:
        json.dump(approvals, file, indent=2)


def create_approval(user_message, intent, selected_agent, selected_model):
    approvals = _load_approvals()

    approval = {
        "id": str(uuid.uuid4()),
        "timestamp": _utc_timestamp(),
        "status": "pending",
        "user_message": user_message,
        "intent": intent,
        "selected_agent": selected_agent,
        "selected_model": selected_model
    }

    approvals.append(approval)
    _save_approvals(approvals)

    return approval


def get_approvals():
    return _load_approvals()


def update_approval_status(approval_id, status):
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid approval status: {status}")

    approvals = _load_approvals()

    for approval in approvals:
        if approval["id"] == approval_id:
            approval["status"] = status
            approval["updated_at"] = _utc_timestamp()
            _save_approvals(approvals)
            return approval
        
    return None
