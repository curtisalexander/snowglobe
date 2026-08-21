$ErrorActionPreference = "Stop"

Write-Host "Running complete development checks"
$checks = @(
    @("uv", "run", "ruff", "format", "--check", "."),
    @("uv", "run", "ruff", "check", "."),
    @("uv", "run", "ty", "check"),
    @("uv", "run", "pytest"),
    @("npm", "run", "lint"),
    @("npm", "run", "typecheck"),
    @("npm", "test"),
    @("npm", "run", "build")
)

foreach ($check in $checks) {
    $command = $check[0]
    $arguments = $check[1..($check.Length - 1)]
    & $command @arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
