#!/usr/bin/env python3
"""Ontology view linter for pre-commit.

Validates that SQL view files in data/datasets/views/ follow the conventions
required by the DuckDB view parser (parse_view_file) and the ontology guide.

Checks:
1. First non-whitespace line is a `-- description: ...` comment
2. Uses `CREATE OR REPLACE VIEW` (the parser skips files without it)
3. View name matches the filename (stem)

Usage:
    uv run python scripts/check_ontology.py
    uv run python scripts/check_ontology.py data/datasets/views/customers.sql
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "data" / "datasets" / "views"

_DESCRIPTION_RE = re.compile(r"^--\s*description:\s*(.+)", re.IGNORECASE)
_CREATE_VIEW_RE = re.compile(
    r"CREATE\s+OR\s+REPLACE\s+VIEW\s+"
    r"(?:\w+\.)?"
    r'(?:"([^"]+)"|(\w+))',
    re.IGNORECASE,
)


def _green(msg: str) -> str:
    return f"\033[32m\u2713 {msg}\033[0m"


def _red(msg: str) -> str:
    return f"\033[31m\u2717 {msg}\033[0m"


def _strip_sql_comments(sql: str) -> str:
    """Remove SQL comments while preserving comment-like text inside quotes."""
    out: list[str] = []
    quote: str | None = None  # tracks current quote char (' or ")
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if quote:
            out.append(ch)
            # Escaped single quote ('')
            if ch == "'" and quote == "'" and i + 1 < n and sql[i + 1] == "'":
                out.append(sql[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "-" and i + 1 < n and sql[i + 1] == "-":
            while i < n and sql[i] != "\n":
                i += 1
            continue
        elif ch == "/" and i + 1 < n and sql[i + 1] == "*":
            i += 2
            while i + 1 < n and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i += 2  # skip */
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def check_view_file(path: Path) -> list[str]:
    """Check a single .sql view file. Returns errors."""
    errors: list[str] = []
    name = path.name

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        errors.append(f"{name}: file is empty")
        return errors

    first_line = text.lstrip().split("\n", 1)[0]

    # 1. Description on first non-whitespace line
    if not _DESCRIPTION_RE.match(first_line):
        errors.append(
            f"{name}: missing `-- description:` on first non-whitespace line\n"
            f"  The parser reads only the first line. Add:\n"
            f"  -- description: One row per <grain>. <What this view represents>."
        )

    # 2. Must use CREATE OR REPLACE VIEW (parser skips files without it)
    # Strip SQL line comments so a commented-out CREATE VIEW doesn't pass,
    # but preserve `--` inside quoted strings (e.g. "order--totals").
    uncommented = _strip_sql_comments(text)
    vm = _CREATE_VIEW_RE.search(uncommented)
    if not vm:
        errors.append(
            f"{name}: parser requires `CREATE OR REPLACE VIEW <name>`\n"
            f"  Files without this exact form are silently skipped at runtime.\n"
            f"  `CREATE VIEW` alone is not enough."
        )
    else:
        # 3. View name matches filename
        view_name = vm.group(1) or vm.group(2)
        expected_name = path.stem
        if view_name != expected_name:
            errors.append(
                f"{name}: view name `{view_name}` does not match filename `{expected_name}`\n"
                f"  Rename the view or the file so they match."
            )

    return errors


def main() -> int:
    # Accept explicit file paths (from pre-commit) or scan the whole directory
    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:] if p.endswith(".sql")]
    elif VIEWS_DIR.is_dir():
        paths = sorted(VIEWS_DIR.glob("*.sql"))
    else:
        # No views directory yet — nothing to check
        print(_green("No views directory found — nothing to check"))
        return 0

    if not paths:
        print(_green("No .sql view files to check"))
        return 0

    all_errors: list[str] = []

    for path in paths:
        all_errors.extend(check_view_file(path))

    for e in all_errors:
        print(_red(e))

    if all_errors:
        print()
        print(f"  {len(all_errors)} error(s)")
        return 1

    file_count = len(paths)
    print(_green(f"Ontology views ({file_count} file{'s' if file_count != 1 else ''})"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
