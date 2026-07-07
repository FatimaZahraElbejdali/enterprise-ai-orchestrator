#!/usr/bin/env python
import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(
        description="Trace the safe semantic routing fields used by /chat."
    )
    parser.add_argument("prompt", help="User prompt to route")
    args = parser.parse_args()

    from agents import knowledge_agent
    from orchestrator.classifier_router import classify_message

    retrieval_called = False
    original_search = knowledge_agent.search_knowledge

    def traced_search(*search_args, **search_kwargs):
        nonlocal retrieval_called
        retrieval_called = True
        return original_search(*search_args, **search_kwargs)

    knowledge_agent.search_knowledge = traced_search

    classification = classify_message(args.prompt)
    semantic_request = classification.get("semantic_request")
    if not isinstance(semantic_request, dict):
        semantic_request = {}

    tool_used = None

    if classification.get("selected_agent") == "knowledge_agent":
        result = knowledge_agent.run(
            args.prompt,
            capability=classification.get("capability"),
            execution_mode=classification.get("execution_mode"),
            semantic_request=classification.get("semantic_request"),
            knowledge_query=(
                classification.get("entities", {}).get("knowledge_topic")
                if isinstance(classification.get("entities"), dict)
                else None
            ),
        )
        if isinstance(result, dict):
            tool_used = result.get("tool_used")

    trace = {
        "prompt": args.prompt,
        "raw_router_request_type": semantic_request.get("request_type"),
        "raw_router_domain": semantic_request.get("domain"),
        "raw_router_capability": semantic_request.get("capability"),
        "validated_request_type": classification.get("request_type"),
        "validated_domain": classification.get("domain"),
        "validated_capability": classification.get("capability"),
        "requires_internal_context": semantic_request.get("requires_internal_context"),
        "execution_mode": classification.get("execution_mode"),
        "semantic_source": (
            classification.get("semantic_source")
            or semantic_request.get("semantic_source")
            or classification.get("classifier_source")
        ),
        "selected_agent": classification.get("selected_agent"),
        "retrieval_called": retrieval_called,
        "tool_used": tool_used,
    }
    print(json.dumps(trace, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
