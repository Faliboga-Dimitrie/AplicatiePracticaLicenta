param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [string]$DockerImage = "brainlife/fsl:latest"
)

$ErrorActionPreference = "Stop"

# Resolve paths
$inputItem = Get-Item -LiteralPath $InputPath
$inputFile = $inputItem.FullName
$inputDir  = Split-Path -Path $inputFile -Parent
$inputName = Split-Path -Path $inputFile -Leaf

$outputDir  = Split-Path -Path $OutputPath -Parent
$outputName = Split-Path -Path $OutputPath -Leaf

if (-not (Test-Path -LiteralPath $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

# Small bash payload to run inside the container
$bash = @'
set -euo pipefail
fslreorient2std "/in/$INPUT_NAME" "/out/$OUTPUT_NAME"
'@ -replace "`r",""

Write-Host "Running reorientation:"
Write-Host "  Input : $inputFile"
Write-Host "  Output: $OutputPath"
Write-Host "  Image : $DockerImage"

docker run --rm `
    -e INPUT_NAME="$inputName" `
    -e OUTPUT_NAME="$outputName" `
    -v "${inputDir}:/in" `
    -v "${outputDir}:/out" `
    $DockerImage `
    bash -lc "$bash"

if ($LASTEXITCODE -ne 0) {
    throw "docker reorientation failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path -LiteralPath $OutputPath)) {
    throw "Reorientation finished but output file was not created: $OutputPath"
}

Write-Host "Reorientation completed successfully."