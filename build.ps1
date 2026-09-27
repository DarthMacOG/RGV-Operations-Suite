$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$outputDirectory = Join-Path $projectRoot "dist"
$iconPath = Join-Path $projectRoot "assets\rgv_icon.ico"
$assetSource = Join-Path $projectRoot "assets"

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "RGV Operations Suite" `
    --icon $iconPath `
    --add-data "$assetSource;assets" `
    --collect-all imageio_ffmpeg `
    --distpath $outputDirectory `
    (Join-Path $projectRoot "app.py")

Write-Host "Build complete: $outputDirectory\RGV Operations Suite.exe"
