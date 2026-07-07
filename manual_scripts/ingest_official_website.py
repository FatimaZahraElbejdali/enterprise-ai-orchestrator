import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestrator.official_web_ingestion import (
    OfficialWebIngestionError,
    OfficialWebsiteIngestionService,
)


def main():
    parser = argparse.ArgumentParser(
        description="Ingest approved Jamain Baco official website pages.",
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--no-crawl", action="store_true")
    args = parser.parse_args()

    try:
        result = OfficialWebsiteIngestionService().ingest(
            url=args.url,
            scope="company_common",
            crawl=not args.no_crawl,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
        )
    except OfficialWebIngestionError as error:
        raise SystemExit(f"Ingestion refused: {error}") from error

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
