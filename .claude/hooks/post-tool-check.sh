#!/usr/bin/env bash
# Post-tool hook for Claude Code - runs autofix on edited files
# This hook receives tool use info via stdin as JSON

set -e

# Read the tool use data from stdin
INPUT=$(cat)

# Extract the file path from the input JSON
# The input format depends on the tool (Write or Edit)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Get the root directory (where this script lives is .claude/hooks/)
ROOT_DIR=$(cd "$(dirname "$0")/../.." && pwd)

# Determine file type and run appropriate formatter
case "$FILE_PATH" in
    *.py)
        # Python file - run ruff
        cd "$ROOT_DIR"
        uv run ruff check --fix --quiet "$FILE_PATH" 2>/dev/null || true
        uv run ruff format --quiet "$FILE_PATH" 2>/dev/null || true
        ;;
    *.ts|*.tsx)
        # TypeScript file - run eslint and prettier
        if [[ "$FILE_PATH" == *"/frontend/"* ]] || [[ "$FILE_PATH" == "$ROOT_DIR/frontend/"* ]]; then
            cd "$ROOT_DIR/frontend"
            # Get relative path from frontend directory
            REL_PATH="${FILE_PATH#$ROOT_DIR/frontend/}"
            npx eslint --fix "$REL_PATH" 2>/dev/null || true
            npx prettier --write "$REL_PATH" 2>/dev/null || true
        fi
        ;;
    *.css|*.json)
        # CSS/JSON files - run prettier only
        if [[ "$FILE_PATH" == *"/frontend/"* ]] || [[ "$FILE_PATH" == "$ROOT_DIR/frontend/"* ]]; then
            cd "$ROOT_DIR/frontend"
            REL_PATH="${FILE_PATH#$ROOT_DIR/frontend/}"
            npx prettier --write "$REL_PATH" 2>/dev/null || true
        fi
        ;;
esac

exit 0
