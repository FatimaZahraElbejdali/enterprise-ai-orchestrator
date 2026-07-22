import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import app
from fastapi.testclient import TestClient


PLACEHOLDERS = {
    "Réponse générée par l’orchestrateur.",
    "Réponse informative générée par l’orchestrateur.",
}


def main():
    parser = argparse.ArgumentParser(description="Trace safe direct LLM /chat metadata.")
    parser.add_argument("prompt")
    parser.add_argument("--email", default="admin@company.local")
    parser.add_argument("--password", default="admin123")
    args = parser.parse_args()

    client = TestClient(app)
    login = client.post(
        "/auth/login",
        json={"email": args.email, "password": args.password},
    )
    login.raise_for_status()
    token = login.json()["access_token"]
    response = client.post(
        "/chat",
        json={"message": args.prompt, "session_id": "trace-direct-llm"},
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    data = response.json()
    technical = data.get("technical") or {}
    text = data.get("response") or ""

    print(json.dumps({
        "request_type": technical.get("request_type"),
        "capability": technical.get("capability"),
        "execution_mode": technical.get("execution_mode"),
        "provider": technical.get("provider"),
        "model": technical.get("model"),
        "llm_attempted": technical.get("provider") == "openai",
        "llm_success": technical.get("llm_success"),
        "adapter_result_keys": [],
        "extracted_response_length": len(text),
        "final_response_length": len(text),
        "fallback_used": text in PLACEHOLDERS,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
