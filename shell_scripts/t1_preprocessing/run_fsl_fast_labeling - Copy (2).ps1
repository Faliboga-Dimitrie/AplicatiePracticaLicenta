# --- paths ---
$inFolder  = "C:/Users/Dimitrie_U/1Facultate/Anul3/Licenta_God_have_mercy/LerningModelAproach/ManualAttempt/FastAtlasTest"
$outFolder = Join-Path $inFolder "fast_out"
$reoFolder = Join-Path $outFolder "reo"
$segFolder = Join-Path $outFolder "fast"

New-Item -ItemType Directory -Path $reoFolder -Force | Out-Null
New-Item -ItemType Directory -Path $segFolder -Force | Out-Null

# enumerate ONLY original inputs (avoid accidentally picking derived files if they exist in inFolder)
$files = Get-ChildItem $inFolder -Filter *.nii.gz -File |
    Where-Object { $_.Name -notmatch '_reo\.nii\.gz$|_seg\.nii\.gz$|_pve_\d\.nii\.gz$|_bias\.nii\.gz$|_restore\.nii\.gz$|_mixeltype\.nii\.gz$' }

Write-Host "Found files:"
$files | ForEach-Object { Write-Host $_.FullName }

# bash script to run inside the container
$bash = @'
set -euo pipefail

# 1) Reorient to standard
fslreorient2std "/in/$inputf" "/reo/${basename}_reo.nii.gz"
'@ -replace "`r",""

foreach ($file in $files) {
    $inputf   = $file.Name
    $basename = $inputf -replace '\.nii\.gz$',''

    $time    = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logPath = Join-Path $outFolder ("{0}.docker.log" -f $basename)

    Write-Host "[$time] Processing $inputf ..."

    docker run --rm `
        -e inputf="$inputf" `
        -e basename="$basename" `
        -v "${inFolder}:/in" `
        -v "${reoFolder}:/reo" `
        -v "${segFolder}:/seg" `
        brainlife/fsl:latest `
        bash -lc "$bash" 2>&1 | Out-File -Append -FilePath $logPath

    if ($LASTEXITCODE -eq 0) {
        Write-Host "[$time] Completed $inputf"
    } else {
        Write-Host "[$time] Failed $inputf (exit code $LASTEXITCODE)" -ForegroundColor Red
    }
}