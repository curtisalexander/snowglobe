$ErrorActionPreference = "Stop"

if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    throw "Required command 'uv' was not found on PATH."
}

Write-Host "Installing locked MCP runtime dependencies with the Snowflake connector"
uv python install 3.12
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv sync --locked --no-dev --extra snowflake
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
