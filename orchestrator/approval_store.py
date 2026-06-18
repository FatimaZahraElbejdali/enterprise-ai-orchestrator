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

    with open(APPROVALS_FILE, "r", encoding="utf-8") as file:
        try:
            approvals = json.load(file)
        except json.JSONDecodeError:
            return []

    if not isinstance(approvals, list):
        return []

    return approvals


def _save_approvals(approvals):
    APPROVALS_FILE.parent.mkdir(exist_ok=True)

    with open(APPROVALS_FILE, "w", encoding="utf-8") as file:
        json.dump(approvals, file, indent=2, ensure_ascii=False)


def create_approval(
    user_message,
    intent,
    selected_agent,
    selected_model="policy_engine",
    action=None,
    risk="medium",
    title=None,
    description=None,
    source_system=None,
    entity_name=None,
    requested_change=None,
    metadata=None,
):
    approvals = _load_approvals()

    approval = {
        "id": str(uuid.uuid4()),
        "timestamp": _utc_timestamp(),
        "updated_at": None,
        "status": "pending",
        "user_message": user_message,
        "intent": intent,
        "selected_agent": selected_agent,
        "selected_model": selected_model,
        "action": action,
        "risk": risk,
        "title": title or "Action sensible en attente de validation",
        "description": description or user_message,
        "source_system": source_system or "orchestrator",
        "entity_name": entity_name,
        "requested_change": requested_change,
        "metadata": metadata or {},
        "executed": False,
    }

    approvals.append(approval)
    _save_approvals(approvals)

    return approval


def get_approvals():
    approvals = _load_approvals()
    return sorted(
        approvals,
        key=lambda item: item.get("timestamp", ""),
        reverse=True
    )


def update_approval_status(approval_id, status):
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid approval status: {status}")

    approvals = _load_approvals()

    for approval in approvals:
        if approval.get("id") == approval_id:
            approval["status"] = status
            approval["updated_at"] = _utc_timestamp()
            _save_approvals(approvals)
            return approval

    return None


def attach_execution_result(approval_id: str, execution_result: dict):
    approvals = _load_approvals()

    for approval in approvals:
        if approval.get("id") == approval_id:
            result = execution_result if isinstance(execution_result, dict) else {}
            approval["execution_result"] = result
            approval["executed"] = bool(
                result.get("success") is True
                and result.get("executed") is True
                and result.get("verified") is True
            )
            approval["execution_status"] = (
                "completed" if approval["executed"] else "failed"
            )
            approval["updated_at"] = _utc_timestamp()

            metadata = approval.get("metadata")

            if not isinstance(metadata, dict):
                metadata = {}

            metadata["executed"] = approval["executed"]
            approval["metadata"] = metadata

            _save_approvals(approvals)
            return approval

    return None
