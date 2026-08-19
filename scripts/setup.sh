#!/usr/bin/env bash
set -euo pipefail

command -v uv >/dev/null
command -v node >/dev/null
command -v npm >/dev/null

node -e '
const [major, minor] = process.versions.node.split(".").map(Number);
if (major < 22 || (major === 22 && minor < 12)) process.exit(1);
'

echo "Installing locked Python dependencies with the Snowflake connector"
uv python install 3.12
uv sync --locked --extra snowflake

echo "Installing locked viewer dependencies"
npm ci
