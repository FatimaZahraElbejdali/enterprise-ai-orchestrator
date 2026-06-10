import json
from pathlib import Path
from datetime import datetime, timezone

LOG_PATH = Path("logs/audit_log.jsonl")


def log_request(data: dict):

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data
    }

    LOG_PATH.parent.mkdir(exist_ok=True)

    with open(LOG_PATH, "a") as file:
        file.write(json.dumps(log_entry) + "\n")
