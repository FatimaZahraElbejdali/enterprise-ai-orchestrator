import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestrator.knowledge_repository import KnowledgeRepository


def main():
    repository = KnowledgeRepository()
    print(json.dumps(repository.stats(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
