# --- paths ---
$inFolder = "C:/Users/Dimitrie_U/1Facultate/Anul3/Licenta_God_have_mercy/LerningModelAproach/ManualAttempt/FastAtlasTest"
$outFolder = Join-Path $inFolder "fast_out"
New-Item -ItemType Directory -Path $outFolder -Force | Out-Null

# enumerate ONLY the original inputs
$files = Get-ChildItem $inFolder -Filter *.nii.gz -File |
    Where-Object { $_.Name -notmatch '_OUT|_seg|_prob_\d' }

Write-Host "Found files:"
$files | ForEach-Object { Write-Host $_.FullName }

foreach ($file in $files) {
    $inputf = $file.Name
    $basename = $inputf -replace '\.nii\.gz$',''
    $outPrefix = "/out/$basename"
    $logPath = Join-Path $outFolder ("{0}.docker.log" -f $basename)
    $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$time] Processing $inputf ..."

    # Docker command as single string for PowerShell
    docker run --rm `
        -v "${inFolder}:/in" `
        -v "${outFolder}:/out" `
        brainlife/fsl:latest `
        fast -t 1 -n 3 -o "$outPrefix" "/in/$inputf" 2>&1 | Out-File -Append -FilePath $logPath

    if ($LASTEXITCODE -eq 0) {
        Write-Host "[$time] Completed $inputf"
    }
    else {
        Write-Host "[$time] Failed $inputf (exit code $LASTEXITCODE)" -ForegroundColor Red
    }
}
