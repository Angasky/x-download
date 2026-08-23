$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
  & py -3 "$PSScriptRoot\scripts\bootstrap.py" @args
} else {
  & python "$PSScriptRoot\scripts\bootstrap.py" @args
}
exit $LASTEXITCODE
