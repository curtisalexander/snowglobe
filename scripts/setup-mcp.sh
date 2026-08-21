#!/usr/bin/env bash
set -euo pipefail

command -v uv >/dev/null

echo "Installing locked MCP runtime dependencies with the Snowflake connector"
uv python install 3.12
uv sync --locked --no-dev --extra snowflake
