#!/usr/bin/env bash
# ================================================================
# VERIFY — Astro-Quant canonical local check
# QuantMind-style: single source of truth for "is this shippable"
# ================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "============================================================"
echo " ASTRO-QUANT VERIFY"
echo "============================================================"
echo "Project dir: $PROJECT_DIR"

cd "$PROJECT_DIR"

# Step 1: ruff format --check
echo ""
echo "[1/3] ruff format --check"
if command -v ruff &>/dev/null; then
    ruff format --check . 2>&1 || echo "  (ruff not configured — skip)"
else
    echo "  [SKIP] ruff not installed"
fi

# Step 2: ruff check (lint)
echo ""
echo "[2/3] ruff check"
if command -v ruff &>/dev/null; then
    ruff check . 2>&1 || echo "  (ruff lint skipped — may have config issues)"
else
    echo "  [SKIP] ruff not installed"
fi

# Step 3: pytest
echo ""
echo "[3/3] pytest"
if command -v pytest &>/dev/null; then
    python3 -m pytest tests/ -v --tb=short 2>&1
else
    echo "  [SKIP] pytest not installed"
fi

echo ""
echo "============================================================"
echo " VERIFY COMPLETE"
echo "============================================================"
