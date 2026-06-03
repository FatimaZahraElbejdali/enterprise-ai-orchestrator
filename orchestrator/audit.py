import json
from datetime import datetime


def log_request(data: dict):

    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        **data
    }

    with open("logs/audit_log.jsonl", "a") as file:
        file.write(json.dumps(log_entry) + "\n")