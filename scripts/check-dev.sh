#!/usr/bin/env bash
set -euo pipefail

echo "Running complete development checks"
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
npm run lint
npm run typecheck
npm test
npm run build
