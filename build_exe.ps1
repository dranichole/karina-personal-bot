# Build Karina.exe (onedir output in dist\Karina)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm karina.spec

Write-Host ""
Write-Host "Built: $PSScriptRoot\dist\Karina\Karina.exe"
Write-Host "Ollama is started automatically on first launch if it is installed."
