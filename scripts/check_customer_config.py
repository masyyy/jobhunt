# ruff: noqa: PLC0415, PERF401
#!/usr/bin/env python3
"""Customer configuration consistency checker.

Validates that frontend and backend toolbox definitions stay in sync:
- Enum parity between Python and TypeScript
- Tool/task registry completeness
- Prompt file presence
- Frontend registry completeness

Usage:
    uv run python scripts/check_customer_config.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Make repo root importable so we can reach `tests.evals.customer` (the eval
# cases live under tests/, not as an installed package).
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _green(msg: str) -> str:
    return f"\033[32m\u2713 {msg}\033[0m"


def _red(msg: str) -> str:
    return f"\033[31m\u2717 {msg}\033[0m"


def check_enum_parity() -> list[str]:
    """Check that Python and TypeScript Toolbox enums have the same values."""
    errors: list[str] = []

    # Parse Python enum
    py_path = ROOT / "backend" / "customer" / "toolboxes.py"
    if not py_path.exists():
        errors.append(f"Python toolbox file not found: {py_path}")
        return errors

    py_content = py_path.read_text()
    py_values = set(re.findall(r'=\s*"([^"]+)"', py_content))

    # Parse TypeScript enum
    ts_path = ROOT / "frontend" / "src" / "customer" / "toolboxes.ts"
    if not ts_path.exists():
        errors.append(f"TypeScript toolbox file not found: {ts_path}")
        return errors

    ts_content = ts_path.read_text()
    # Extract the Toolbox block (enum or const object), then parse values from it
    toolbox_block = re.search(r"(?:export\s+(?:enum|const)\s+Toolbox\s*[={])(.*?)(?:})", ts_content, re.DOTALL)
    if not toolbox_block:
        errors.append("Could not find Toolbox definition in TypeScript file")
        return errors
    block_text = toolbox_block.group(1)
    # Match values: either `= 'value'` (enum) or `: 'value'` (const object)
    ts_values = set(re.findall(r"[=:]\s*'([^']+)'", block_text))

    # Compare
    py_only = py_values - ts_values
    ts_only = ts_values - py_values

    for v in py_only:
        errors.append(
            f"Toolbox mismatch: `{v}`\n"
            f"  Present in:  backend/customer/toolboxes.py\n"
            f"  Missing in:  frontend/src/customer/toolboxes.ts"
        )
    for v in ts_only:
        errors.append(
            f"Toolbox mismatch: `{v}`\n"
            f"  Present in:  frontend/src/customer/toolboxes.ts\n"
            f"  Missing in:  backend/customer/toolboxes.py"
        )

    return errors


def check_query_parity() -> list[str]:
    """Check that Python and TypeScript DashboardQuery registries have the same values."""
    errors: list[str] = []

    # Parse Python query enum
    py_path = ROOT / "backend" / "customer" / "queries.py"
    if not py_path.exists():
        errors.append(f"Python query registry not found: {py_path}")
        return errors

    py_content = py_path.read_text()
    py_values = set(re.findall(r'=\s*"([^"]+)"', py_content))

    # Parse TypeScript query const object
    ts_path = ROOT / "frontend" / "src" / "customer" / "queries.ts"
    if not ts_path.exists():
        errors.append(f"TypeScript query registry not found: {ts_path}")
        return errors

    ts_content = ts_path.read_text()
    query_block = re.search(r"export\s+const\s+DashboardQuery\s*=\s*\{(.*?)\}", ts_content, re.DOTALL)
    if not query_block:
        errors.append("Could not find DashboardQuery definition in TypeScript file")
        return errors
    block_text = query_block.group(1)
    ts_values = set(re.findall(r"[=:]\s*'([^']+)'", block_text))

    # Compare
    py_only = py_values - ts_values
    ts_only = ts_values - py_values

    for v in py_only:
        errors.append(
            f"DashboardQuery mismatch: `{v}`\n"
            f"  Present in:  backend/customer/queries.py\n"
            f"  Missing in:  frontend/src/customer/queries.ts"
        )
    for v in ts_only:
        errors.append(
            f"DashboardQuery mismatch: `{v}`\n"
            f"  Present in:  frontend/src/customer/queries.ts\n"
            f"  Missing in:  backend/customer/queries.py"
        )

    return errors


def check_agent_config_registry() -> list[str]:
    """Check that TOOLBOX_AGENT_CONFIG has entries for all toolboxes."""
    errors: list[str] = []

    try:
        from backend.customer import TOOLBOX_AGENT_CONFIG, Toolbox

        for tb in Toolbox:
            if tb not in TOOLBOX_AGENT_CONFIG:
                errors.append(f"Missing TOOLBOX_AGENT_CONFIG entry for toolbox `{tb.value}`")
            elif not TOOLBOX_AGENT_CONFIG[tb].tools:
                errors.append(f"Warning: TOOLBOX_AGENT_CONFIG[{tb.value}].tools is empty (no tools)")
    except ImportError as e:
        errors.append(f"Failed to import backend.customer: {e}")

    return errors


def check_prompt_key_parity() -> list[str]:
    """Check that Python and TypeScript PromptKey registries have the same values."""
    errors: list[str] = []

    py_path = ROOT / "backend" / "customer" / "prompt_keys.py"
    if not py_path.exists():
        errors.append(f"Python prompt key registry not found: {py_path}")
        return errors

    py_content = py_path.read_text()
    py_values = set(re.findall(r'=\s*"([^"]+)"', py_content))

    ts_path = ROOT / "frontend" / "src" / "customer" / "promptKeys.ts"
    if not ts_path.exists():
        errors.append(f"TypeScript prompt key registry not found: {ts_path}")
        return errors

    ts_content = ts_path.read_text()
    pk_block = re.search(r"export\s+const\s+PromptKey\s*=\s*\{(.*?)\}", ts_content, re.DOTALL)
    if not pk_block:
        errors.append("Could not find PromptKey definition in TypeScript file")
        return errors
    block_text = pk_block.group(1)
    ts_values = set(re.findall(r"[=:]\s*'([^']+)'", block_text))

    py_only = py_values - ts_values
    ts_only = ts_values - py_values

    for v in py_only:
        errors.append(
            f"PromptKey mismatch: `{v}`\n"
            f"  Present in:  backend/customer/prompt_keys.py\n"
            f"  Missing in:  frontend/src/customer/promptKeys.ts"
        )
    for v in ts_only:
        errors.append(
            f"PromptKey mismatch: `{v}`\n"
            f"  Present in:  frontend/src/customer/promptKeys.ts\n"
            f"  Missing in:  backend/customer/prompt_keys.py"
        )

    return errors


def check_accepted_prompt_keys_valid() -> list[str]:
    """Check that every accepted_prompt_keys entry references a real PromptKey member."""
    errors: list[str] = []

    try:
        from backend.customer import TOOLBOX_AGENT_CONFIG
        from backend.customer.prompt_keys import PromptKey
    except ImportError as e:
        errors.append(f"Failed to import backend.customer: {e}")
        return errors

    valid_keys = {pk.value for pk in PromptKey}
    for tb, config in TOOLBOX_AGENT_CONFIG.items():
        for key in config.accepted_prompt_keys:
            if key not in valid_keys:
                errors.append(
                    f"Toolbox `{tb.value}` lists accepted_prompt_keys=`{key}` "
                    f"which is not a member of PromptKey in backend/customer/prompt_keys.py"
                )

    return errors


def check_external_tools_parity() -> list[str]:
    """Check that BE external_tools and FE externalToolRenderers stay in sync.

    Each tool name registered as an ExternalToolset entry in
    ``TOOLBOX_AGENT_CONFIG[...].external_tools`` must have a matching renderer
    in ``frontend/src/customer/externalTools.ts`` — otherwise the FE has no UI
    to surface the prompt and the user can't supply the result.
    """
    errors: list[str] = []

    try:
        from backend.customer import TOOLBOX_AGENT_CONFIG
    except ImportError as e:
        errors.append(f"Failed to import backend.customer: {e}")
        return errors

    backend_tool_names: set[str] = set()
    for config in TOOLBOX_AGENT_CONFIG.values():
        for tool_def in config.external_tools:
            backend_tool_names.add(tool_def.name)

    ts_path = ROOT / "frontend" / "src" / "customer" / "externalTools.ts"
    if not ts_path.exists():
        if backend_tool_names:
            errors.append(f"Frontend external tool registry not found: {ts_path}")
        return errors

    ts_content = ts_path.read_text()
    registry_block = re.search(
        r"externalToolRenderers\s*:\s*ExternalToolRenderer\[\]\s*=\s*\[(.*?)\]",
        ts_content,
        re.DOTALL,
    )
    if not registry_block:
        if backend_tool_names:
            errors.append("Could not find externalToolRenderers definition in TypeScript file")
        return errors

    block_text = registry_block.group(1)
    frontend_tool_names = set(re.findall(r"toolName\s*:\s*'([^']+)'", block_text))

    backend_only = backend_tool_names - frontend_tool_names
    frontend_only = frontend_tool_names - backend_tool_names

    for name in backend_only:
        errors.append(
            f"External tool `{name}` is registered in TOOLBOX_AGENT_CONFIG but has no\n"
            f"  matching renderer in frontend/src/customer/externalTools.ts"
        )
    for name in frontend_only:
        errors.append(
            f"External tool renderer `{name}` exists in frontend/src/customer/externalTools.ts\n"
            f"  but no matching ToolDefinition in any TOOLBOX_AGENT_CONFIG.external_tools"
        )

    return errors


def check_seed_prompt_files() -> list[str]:
    """Check that every PromptKey member has a corresponding seeds/{key}.md file."""
    errors: list[str] = []

    if _is_blob_storage_active():
        return errors

    try:
        from backend.customer.prompt_keys import PromptKey
    except ImportError as e:
        errors.append(f"Failed to import PromptKey enum: {e}")
        return errors

    seeds_dir = ROOT / "backend" / "prompts" / "seeds"
    for pk in PromptKey:
        seed_file = seeds_dir / f"{pk.value}.md"
        if not seed_file.exists():
            errors.append(f"Missing seed prompt for PromptKey `{pk.value}`\n  Expected: {seed_file}")

    return errors


def check_task_registry() -> list[str]:
    """Check that TOOLBOX_TASKS has entries for all toolboxes."""
    errors: list[str] = []

    try:
        from backend.customer import TOOLBOX_TASKS, Toolbox

        for tb in Toolbox:
            if tb not in TOOLBOX_TASKS:
                errors.append(f"Missing TOOLBOX_TASKS entry for toolbox `{tb.value}`")
    except ImportError as e:
        errors.append(f"Failed to import backend.customer: {e}")

    return errors


def check_task_runnable() -> list[str]:
    """Check that every task name in TOOLBOX_TASKS is registered in the task registry."""
    errors: list[str] = []

    try:
        from types import SimpleNamespace

        from backend.customer.tasks import TOOLBOX_TASKS, build_task_registry

        # build_task_registry only uses deps to construct the task closures.
        # We don't invoke the tasks, so a sentinel with the right attribute names
        # is enough to enumerate the registered task names.
        sentinel = SimpleNamespace(
            task_output_repo_factory=None,
            ingestion_service=None,
            ingestion_log_repo_factory=None,
            ingestion_allowed_dir=None,
            on_ingestion_complete=lambda: None,
        )
        registered = set(build_task_registry(sentinel).keys())  # type: ignore[arg-type]
    except ImportError as e:
        errors.append(f"Failed to import customer task registry: {e}")
        return errors

    for tb, task_names in TOOLBOX_TASKS.items():
        for name in task_names:
            if name not in registered:
                errors.append(
                    f"Toolbox `{tb.value}` references task `{name}` that is not registered in "
                    f"build_task_registry() in backend/customer/tasks/__init__.py"
                )

    return errors


def _is_blob_storage_active() -> bool:
    """Check if Azure Blob Storage is configured for prompts (via env or .env files)."""
    import os

    if os.environ.get("AZURE_STORAGE_ACCOUNT_NAME"):
        return True
    # Also check .env files that the app reads
    for env_file in [ROOT / ".env", ROOT / ".env.local"]:
        if env_file.exists():
            for raw_line in env_file.read_text().splitlines():
                stripped = raw_line.strip()
                if stripped.startswith("#") or "=" not in stripped:
                    continue
                key, _, value = stripped.partition("=")
                if key.strip() == "AZURE_STORAGE_ACCOUNT_NAME" and value.strip():
                    return True
    return False


def check_prompt_files() -> list[str]:
    """Check that prompt files exist for each toolbox.

    Environment-aware: checks local filesystem when prompts are served
    locally, skips with a note when Azure Blob Storage is active.
    """
    errors: list[str] = []

    if _is_blob_storage_active():
        # Blob storage is the prompt source — filesystem check doesn't apply.
        # A full blob check would require azure-storage-blob SDK + credentials,
        # which is out of scope for a fast pre-commit check.
        return errors

    prompts_dir = ROOT / "backend" / "prompts"

    # Check system.md
    if not (prompts_dir / "system.md").exists():
        errors.append(f"Missing prompt file: {prompts_dir / 'system.md'}")

    # Check per-toolbox prompt files
    try:
        from backend.customer.toolboxes import Toolbox

        for tb in Toolbox:
            prompt_file = prompts_dir / f"{tb.value}.md"
            if not prompt_file.exists():
                errors.append(f"Missing prompt file for toolbox `{tb.value}`\n  Expected: {prompt_file}")
    except ImportError as e:
        errors.append(f"Failed to import Toolbox enum: {e}")

    return errors


def check_eval_coverage() -> list[str]:
    """Check that every toolbox has at least one EvalCase.

    Skipped silently if `tests/evals/customer/` does not exist (forks may
    legitimately remove it if they don't want eval coverage gating).
    """
    errors: list[str] = []

    if not (ROOT / "tests" / "evals" / "customer" / "__init__.py").exists():
        return errors

    try:
        from backend.customer import Toolbox
        from tests.evals.customer import ALL_CASES
    except ImportError as e:
        errors.append(f"Failed to import customer eval cases: {e}")
        return errors

    cases_per_toolbox: dict[str, int] = {}
    for case in ALL_CASES:
        cases_per_toolbox[case.toolbox.value] = cases_per_toolbox.get(case.toolbox.value, 0) + 1

    for tb in Toolbox:
        if cases_per_toolbox.get(tb.value, 0) == 0:
            errors.append(f"Toolbox `{tb.value}` has no eval cases in tests/evals/customer/")

    return errors


def check_frontend_registry() -> list[str]:
    """Check that the frontend toolbox registry references existing files."""
    errors: list[str] = []
    ts_path = ROOT / "frontend" / "src" / "customer" / "toolboxes.ts"

    if not ts_path.exists():
        errors.append(f"Frontend toolbox registry not found: {ts_path}")
        return errors

    content = ts_path.read_text()

    # Find all import paths
    imports = re.findall(r"from\s+'(\.[^']+)'", content)
    customer_dir = ts_path.parent

    for import_path in imports:
        # Resolve relative import to file path
        resolved = (customer_dir / import_path).resolve()
        # Try with .tsx and .ts extensions
        candidates = [resolved.with_suffix(".tsx"), resolved.with_suffix(".ts")]
        if not any(c.exists() for c in candidates):
            errors.append(f"Frontend registry imports missing file: {import_path}")

    return errors


def main() -> int:
    blob_active = _is_blob_storage_active()
    prompt_label = (
        "Prompt file presence (blob storage active, skipped)" if blob_active else "Prompt file presence (filesystem)"
    )
    seed_label = (
        "Seed prompt file presence (blob storage active, skipped)"
        if blob_active
        else "Seed prompt file presence (filesystem)"
    )

    checks = [
        ("Enum parity (Python ↔ TypeScript)", check_enum_parity),
        ("Query registry parity (Python ↔ TypeScript)", check_query_parity),
        ("PromptKey parity (Python ↔ TypeScript)", check_prompt_key_parity),
        ("Agent config registry completeness", check_agent_config_registry),
        ("External tools parity (Python ↔ TypeScript)", check_external_tools_parity),
        ("Accepted prompt keys reference valid PromptKey members", check_accepted_prompt_keys_valid),
        ("Task registry completeness", check_task_registry),
        ("Task names registered in task queue", check_task_runnable),
        (prompt_label, check_prompt_files),
        (seed_label, check_seed_prompt_files),
        ("Frontend registry completeness", check_frontend_registry),
        ("Eval coverage per toolbox", check_eval_coverage),
    ]

    total_pass = 0
    total_fail = 0

    for name, check_fn in checks:
        errors = check_fn()
        if errors:
            total_fail += 1
            print(_red(name))
            for err in errors:
                for line in err.split("\n"):
                    print(f"    {line}")
        else:
            total_pass += 1
            print(_green(name))

    print()
    print(f"  {total_pass} passed, {total_fail} failed")

    return 1 if total_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
