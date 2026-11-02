# Windows: .\setup.ps1（追加機能は下のスイッチで導入）
param([switch]$WithBrowser, [switch]$WithFirecrawl, [switch]$CheckOnly)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-Checked {
  param([string]$Program, [string[]]$CommandArgs)
  & $Program @CommandArgs
  if ($LASTEXITCODE -ne 0) { throw "$Program の実行に失敗しました（終了コード: $LASTEXITCODE）" }
}

# 既存の専用環境を最優先する。PC全体のpythonが3.11でも作り直さない。
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
  if ($CheckOnly) { throw "専用環境がありません。まずsetup.ps1を実行してください" }
  if (Get-Command uv -ErrorAction SilentlyContinue) {
    Invoke-Checked -Program "uv" -CommandArgs @("venv", "--python", "3.12", ".venv")
  } elseif (Get-Command py -ErrorAction SilentlyContinue) {
    Invoke-Checked -Program "py" -CommandArgs @("-3.12", "-m", "venv", ".venv")
  } else {
    Invoke-Checked -Program "python" -CommandArgs @("-c", 'import sys; sys.exit(int(sys.version_info < (3, 12)))')
    Invoke-Checked -Program "python" -CommandArgs @("-m", "venv", ".venv")
  }
}
Invoke-Checked -Program $venvPython -CommandArgs @("-c", 'import sys; sys.exit(int(sys.version_info < (3, 12)))')
if ($CheckOnly) {
  Invoke-Checked -Program $venvPython -CommandArgs @("--version")
  Write-Host "専用環境を確認しました。インストール・接続は行っていません。"
  return
}
function Install-Requirements([string]$File) {
  if (Get-Command uv -ErrorAction SilentlyContinue) {
    Invoke-Checked -Program "uv" -CommandArgs @("pip", "install", "--python", $venvPython, "-r", $File)
  } else {
    Invoke-Checked -Program $venvPython -CommandArgs @("-m", "ensurepip", "--upgrade")
    Invoke-Checked -Program $venvPython -CommandArgs @("-m", "pip", "install", "-r", $File)
  }
}
$env:PYTHONUTF8 = "1"
Install-Requirements "requirements.txt"
if ($WithBrowser) {
  Invoke-Checked -Program "git" -CommandArgs @("submodule", "update", "--init", "--depth", "1", "vendor/browser-use")
  Install-Requirements "requirements-browser.txt"
}
if ($WithFirecrawl) {
  Invoke-Checked -Program "git" -CommandArgs @("submodule", "update", "--init", "--depth", "1", "vendor/firecrawl")
  Install-Requirements "requirements-firecrawl.txt"
}
if ($WithBrowser) { Invoke-Checked -Program $venvPython -CommandArgs @("-m", "playwright", "install", "chromium") }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Write-Host "完了。以後は .\.venv\Scripts\Activate.ps1 してから使います"
