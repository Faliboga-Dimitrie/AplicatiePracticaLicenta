param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPrefix,

    [string]$DockerImage = "brainlife/fsl:latest",

    [int]$Classes = 3,

    [int]$ImageType = 1,

    [string]$ContainerInputDir = "/data/in",

    [string]$ContainerOutputDir = "/data/out",

    [bool]$VerboseMode = $true
)

$ErrorActionPreference = "Stop"

# ---------- resolve and validate paths ----------
$inputItem = Get-Item -LiteralPath $InputPath
$inputFile = $inputItem.FullName
$inputDir  = Split-Path -Path $inputFile -Parent
$inputName = Split-Path -Path $inputFile -Leaf

$outputDir      = Split-Path -Path $OutputPrefix -Parent
$outputBasename = Split-Path -Path $OutputPrefix -Leaf

if (-not (Test-Path -LiteralPath $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

# ---------- FAST inside container ----------
$fastVerboseFlag = ""
if ($VerboseMode) {
    $fastVerboseFlag = "-v"
}

$bash = @"
set -euo pipefail

fast \
  -t "$IMAGE_TYPE" \
  -n "$FAST_CLASSES" \
  $fastVerboseFlag \
  -o "$CONTAINER_OUTPUT_DIR/$OUTPUT_BASENAME" \
  "$CONTAINER_INPUT_DIR/$INPUT_NAME"
"@ -replace "`r",""

Write-Host "Running FAST segmentation:"
Write-Host "  Input file     : $inputFile"
Write-Host "  Output prefix  : $OutputPrefix"
Write-Host "  Docker image   : $DockerImage"
Write-Host "  Classes        : $Classes"
Write-Host "  Image type     : $ImageType"
Write-Host "  Verbose        : $VerboseMode"

docker run --rm `
    -e INPUT_NAME="$inputName" `
    -e OUTPUT_BASENAME="$outputBasename" `
    -e FAST_CLASSES="$Classes" `
    -e IMAGE_TYPE="$ImageType" `
    -e CONTAINER_INPUT_DIR="$ContainerInputDir" `
    -e CONTAINER_OUTPUT_DIR="$ContainerOutputDir" `
    -v "${inputDir}:${ContainerInputDir}" `
    -v "${outputDir}:${ContainerOutputDir}" `
    $DockerImage `
    bash -lc "$bash"

if ($LASTEXITCODE -ne 0) {
    throw "docker FAST failed with exit code $LASTEXITCODE"
}

# ---------- verify expected outputs ----------
$expected = @(
    "${OutputPrefix}_mixeltype.nii.gz",
    "${OutputPrefix}_pve_0.nii.gz",
    "${OutputPrefix}_pve_1.nii.gz",
    "${OutputPrefix}_pve_2.nii.gz",
    "${OutputPrefix}_pve_seg.nii.gz",
    "${OutputPrefix}_seg.nii.gz"
)

$missing = @()
foreach ($f in $expected) {
    if (-not (Test-Path -LiteralPath $f)) {
        $missing += $f
    }
}

if ($missing.Count -gt 0) {
    throw ("FAST finished but some expected outputs are missing:`n" + ($missing -join "`n"))
}

Write-Host "FAST segmentation completed successfully."