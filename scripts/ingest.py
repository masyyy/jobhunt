"""Submit a file ingestion task to the backend.

Usage:
    uv run python scripts/ingest.py --file orders.csv
    uv run python scripts/ingest.py --file orders.csv --table orders
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:8000"


def submit_task(*, base_url: str, api_key: str, file_path: str, table: str | None) -> dict[str, str]:
    """POST to /internal/tasks/ingest-file and return the response."""
    url = f"{base_url}/internal/tasks/ingest-file"

    payload: dict[str, str] = {"file_path": file_path}
    if table:
        payload["table"] = table

    data = json.dumps(payload).encode()
    req = urllib.request.Request(  # noqa: S310
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit a file ingestion task to the backend.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  uv run python scripts/ingest.py --file orders.csv",
    )
    parser.add_argument(
        "--file",
        required=True,
        metavar="FILE",
        help="Path to the CSV or Excel file to ingest.",
    )
    parser.add_argument(
        "--table",
        metavar="TABLE",
        help="Delta table name (defaults to file stem, e.g. 'orders' for orders.csv).",
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    args = build_parser().parse_args()

    source_file = Path(args.file).resolve()
    if not source_file.exists():
        logger.error("File not found: %s", source_file)
        sys.exit(1)

    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")
    load_dotenv(project_root / ".env.local", override=True)

    base_url = os.environ.get("FULCRUM_API_URL", DEFAULT_BASE_URL)
    api_key = os.environ.get("INTERNAL_API_KEY", "dev-internal-key")

    try:
        result = submit_task(
            base_url=base_url,
            api_key=api_key,
            file_path=str(source_file),
            table=args.table,
        )
        logger.info("Task submitted: %s", result)
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        logger.error("HTTP %d: %s", e.code, body)
        sys.exit(1)
    except urllib.error.URLError as e:
        logger.error("Connection failed: %s", e.reason)
        sys.exit(1)


if __name__ == "__main__":
    main()
