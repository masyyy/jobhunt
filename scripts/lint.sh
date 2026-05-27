#!/usr/bin/env bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED=0
FIX_MODE=false

# Parse arguments
for arg in "$@"; do
    case $arg in
        --fix)
            FIX_MODE=true
            shift
            ;;
    esac
done

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT_DIR"

echo "🔍 Running all linters..."
if [ "$FIX_MODE" = true ]; then
    echo -e "${YELLOW}(Fix mode enabled)${NC}"
fi
echo ""

# ============================================
# Backend checks (Python)
# ============================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 Backend (Python)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Ruff linting
echo -n "  Ruff lint... "
if [ "$FIX_MODE" = true ]; then
    if uv run ruff check . --fix; then
        echo -e "${GREEN}✓ (fixed)${NC}"
    else
        echo -e "${RED}✗${NC}"
        FAILED=1
    fi
else
    if uv run ruff check .; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
        FAILED=1
    fi
fi

# Ruff formatting
echo -n "  Ruff format... "
if [ "$FIX_MODE" = true ]; then
    if uv run ruff format .; then
        echo -e "${GREEN}✓ (formatted)${NC}"
    else
        echo -e "${RED}✗${NC}"
        FAILED=1
    fi
else
    if uv run ruff format --check .; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
        echo -e "${YELLOW}  Run './scripts/lint.sh --fix' to fix formatting${NC}"
        FAILED=1
    fi
fi

# Pyright type checking
echo -n "  Pyright... "
if uv run pyright; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    FAILED=1
fi

# ============================================
# Frontend checks (TypeScript/React)
# ============================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌐 Frontend (TypeScript/React)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$ROOT_DIR/frontend"

# TypeScript type checking
echo -n "  TypeScript... "
if npm run typecheck 2>/dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    FAILED=1
fi

# ESLint
echo -n "  ESLint... "
if [ "$FIX_MODE" = true ]; then
    if npm run lint:fix 2>/dev/null; then
        echo -e "${GREEN}✓ (fixed)${NC}"
    else
        echo -e "${RED}✗${NC}"
        FAILED=1
    fi
else
    if npm run lint 2>/dev/null; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
        FAILED=1
    fi
fi

# Prettier format check
echo -n "  Prettier... "
if [ "$FIX_MODE" = true ]; then
    if npm run format 2>/dev/null; then
        echo -e "${GREEN}✓ (formatted)${NC}"
    else
        echo -e "${RED}✗${NC}"
        FAILED=1
    fi
else
    if npm run format:check 2>/dev/null; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
        echo -e "${YELLOW}  Run './scripts/lint.sh --fix' to fix formatting${NC}"
        FAILED=1
    fi
fi

cd "$ROOT_DIR"

# ============================================
# Final result
# ============================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $FAILED -eq 1 ]; then
    echo -e "${RED}❌ Some checks failed${NC}"
    exit 1
else
    echo -e "${GREEN}✅ All checks passed${NC}"
    exit 0
fi
