import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from integrations.odoo_connector import OdooConnector


def main():
    parser = argparse.ArgumentParser(
        description="Inspect the safe Odoo dynamic-read model catalog."
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    connector = OdooConnector()

    if connector.mock_mode:
        print("Odoo credentials are missing. Catalog inspection is unavailable.")
        return

    catalog = connector.get_model_catalog(force_refresh=args.refresh)
    shown = 0

    for item in sorted(catalog, key=lambda row: row.get("model") or ""):
        if shown >= args.limit:
            break

        model_name = item.get("model")
        allowed = bool(item.get("allowed"))
        safe_field_count = 0
        safe_field_names = []

        if allowed:
            try:
                safe_fields = connector.safe_dynamic_fields(model_name)
                safe_field_count = len(safe_fields)
                safe_field_names = sorted(safe_fields)[:12]
            except Exception:
                safe_field_count = 0
                safe_field_names = []

        print(
            f"{model_name}\t{item.get('name') or model_name}\t"
            f"allowed={allowed}\tsafe_fields={safe_field_count}\t"
            f"{', '.join(safe_field_names)}"
        )
        shown += 1


if __name__ == "__main__":
    main()
