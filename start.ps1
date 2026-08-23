$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
  & py -3 -X utf8 "$PSScriptRoot\scripts\bootstrap.py" --windows-menu @args
} else {
  & python -X utf8 "$PSScriptRoot\scripts\bootstrap.py" --windows-menu @args
}
exit $LASTEXITCODE
