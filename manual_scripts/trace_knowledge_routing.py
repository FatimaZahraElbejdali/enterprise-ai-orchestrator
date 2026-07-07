import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import agents.knowledge_agent as knowledge_agent
import orchestrator.classifier_router as classifier_router
from orchestrator.knowledge_repository import KnowledgeRepository
from orchestrator.department_profiles import (
    capability_from_route,
    get_department_profile,
)
from orchestrator.permission_policy import resolve_route_permission


def trace_prompt(prompt: str, department: str, use_openai_router: bool):
    if not use_openai_router:
        classifier_router.classify_with_openai_router = lambda *args, **kwargs: None

    profile = get_department_profile(department)
    repository = KnowledgeRepository()
    repository_stats = repository.stats()
    classification = classifier_router.classify_message(prompt)
    route_permission = resolve_route_permission(classification)
    capability = capability_from_route(classification, route_permission)
    result = {}

    if classification.get("selected_agent") == "knowledge_agent":
        result = knowledge_agent.run(
            prompt,
            knowledge_scopes=profile.knowledge_scopes,
            llm_project_env=profile.llm_project_env,
        )

    sources = result.get("sources") or []

    return {
        "prompt": prompt,
        "normalized_intent": classification.get("intent"),
        "selected_agent": classification.get("selected_agent"),
        "domain": classification.get("target_system"),
        "capability": capability,
        "retrieval_called": result.get("tool_used") == "knowledge_rag_retrieval",
        "normalized_query": result.get("retrieval_query"),
        "repository_documents": repository_stats["documents"],
        "repository_chunks": repository_stats["chunks"],
        "knowledge_scopes": list(profile.knowledge_scopes),
        "retrieved_source_titles": [
            source.get("title")
            for source in sources
            if source.get("title")
        ],
        "retrieval_scores": [
            source.get("score")
            for source in sources
            if source.get("score") is not None
        ],
        "fallback_used": result.get("tool_used") == "knowledge_project_answer",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Safely compare knowledge routing for prompts.",
    )
    parser.add_argument("prompts", nargs="+")
    parser.add_argument("--department", default="administration")
    parser.add_argument("--use-openai-router", action="store_true")
    args = parser.parse_args()

    for prompt in args.prompts:
        print(trace_prompt(prompt, args.department, args.use_openai_router))


if __name__ == "__main__":
    main()
