import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.odoo_agent import build_odoo_read_plan
from agents.odoo_read_agent import run_odoo_read_agent
from orchestrator.classifier_router import classify_message


def main():
    parser = argparse.ArgumentParser(description="Trace the bounded Odoo read agent safely.")
    parser.add_argument("prompt", help="User prompt to trace")
    args = parser.parse_args()

    classification = classify_message(args.prompt)
    read_plan = build_odoo_read_plan(args.prompt, classification)
    result = run_odoo_read_agent(args.prompt, read_plan=read_plan)

    safe_trace = {
        "request_type": classification.get("request_type"),
        "capability": classification.get("capability"),
        "selected_path": result.get("tool_used"),
        "operation": read_plan.get("operation"),
        "business_object": read_plan.get("business_object"),
        "model_hint": read_plan.get("model_hint"),
        "semantic_filters": read_plan.get("filters"),
        "tool_sequence": [
            {
                "iteration": item.get("iteration"),
                "tool": item.get("tool"),
                "validation_allowed": item.get("validation_allowed"),
                "status": item.get("status"),
                "model": item.get("model"),
                "domain": item.get("domain"),
                "record_count": item.get("record_count"),
                "group_by": item.get("group_by"),
                "group_count": item.get("group_count"),
                "business_scope_status": item.get("business_scope_status"),
            }
            for item in result.get("tool_sequence", [])
            if isinstance(item, dict)
        ],
        "models_used": result.get("models_used", []),
        "record_count": result.get("record_count"),
        "business_scope_status": result.get("business_scope_status"),
        "final_status": result.get("status"),
        "final_answer_length": len(result.get("message") or ""),
        "stop_reason": result.get("stop_reason"),
    }

    print(json.dumps(safe_trace, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
