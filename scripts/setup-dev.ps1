$ErrorActionPreference = "Stop"

foreach ($command in @("uv", "node", "npm")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command '$command' was not found on PATH."
    }
}

node -e 'const [major, minor] = process.versions.node.split(".").map(Number); if (major < 22 || (major === 22 && minor < 19)) process.exit(1);'
if ($LASTEXITCODE -ne 0) { throw "Node.js 22.19 or newer is required." }

Write-Host "Installing locked Python development dependencies with the Snowflake connector"
uv python install 3.12
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv sync --locked --extra snowflake
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Installing locked JavaScript development dependencies"
npm ci
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
