# --- paths ---
$inFolder = "C:/Users/Dimitrie_U/1Facultate/Anul3/Licenta_God_have_mercy/LerningModelAproach/ManualAttempt/FastAtlasTest"
$outFolder = Join-Path $inFolder "fast_out"
New-Item -ItemType Directory -Path $outFolder -Force | Out-Null

# enumerate ONLY the original inputs
$files = Get-ChildItem $inFolder -Filter *.nii.gz -File |
    Where-Object { $_.Name -notmatch '_OUT|_seg|_prob_\d' }

Write-Host "Found files:"
$files | ForEach-Object { Write-Host $_.FullName }

$bash = @'
set -e

FSLDIR="$(cd "$(dirname "$(command -v flirt)")/.." && pwd)"
export FSLDIR
MNI="$FSLDIR/data/standard/MNI152_T1_1mm.nii.gz"

fslreorient2std "/in/$inputf" "/out/${basename}_reo.nii.gz"

flirt -in "/out/${basename}_reo.nii.gz" -ref "$MNI" -omat "/out/${basename}_T1_to_MNI_aff.mat" -dof 12

fnirt --in="/out/${basename}_reo.nii.gz" --aff="/out/${basename}_T1_to_MNI_aff.mat" --ref="$MNI" \
      --cout="/out/${basename}_T1_to_MNI_warpcoef.nii.gz" --iout="/out/${basename}_T1_in_MNI.nii.gz"

invwarp -w "/out/${basename}_T1_to_MNI_warpcoef.nii.gz" -r "/out/${basename}_reo.nii.gz" -o "/out/${basename}_MNI_to_T1_warp.nii.gz"

applywarp -i "/usr/share/data/harvard-oxford-atlases/HarvardOxford/HarvardOxford-cortl-maxprob-thr25-1mm.nii.gz" \
          -r "/out/${basename}_reo.nii.gz" \
          -w "/out/${basename}_MNI_to_T1_warp.nii.gz" \
          --interp=nn \
          -o "/out/${basename}_HO_cortL_thr25_in_T1.nii.gz"
'@

$bash_region_labeling =@'
set -e

FSLDIR="$(cd "$(dirname "$(command -v flirt)")/.." && pwd)"
export FSLDIR

# Cortical (both hemispheres)
applywarp -i "/usr/share/data/harvard-oxford-atlases/HarvardOxford/HarvardOxford-cort-maxprob-thr25-1mm.nii.gz" \
          -r "/out/${basename}_reo.nii.gz" \
          -w "/out/${basename}_MNI_to_T1_warp.nii.gz" \
          --interp=nn \
          -o "/out/${basename}_HO_cort_thr25_in_T1.nii.gz"

# Subcortical
applywarp -i "/usr/share/data/harvard-oxford-atlases/HarvardOxford/HarvardOxford-sub-maxprob-thr25-1mm.nii.gz" \
          -r "/out/${basename}_reo.nii.gz" \
          -w "/out/${basename}_MNI_to_T1_warp.nii.gz" \
          --interp=nn \
          -o "/out/${basename}_HO_sub_thr25_in_T1.nii.gz"
'@

# Strip CR characters just in case
$bash = $bash -replace "`r",""
$bash_region_labeling = $bash_region_labeling -replace "`r",""

foreach ($file in $files) {
    $inputf = $file.Name
    $basename = $inputf -replace '\.nii\.gz$',''
    $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$time] Processing $inputf ..."

    docker run --rm `
        -e inputf="$inputf" `
        -e basename="$basename" `
        -v "${inFolder}:/in" `
        -v "${outFolder}:/out" `
        brainlife/fsl:latest `
        bash -c "$bash_region_labeling"

    if ($LASTEXITCODE -eq 0) {
        Write-Host "[$time] Completed $inputf"
    }
    else {
        Write-Host "[$time] Failed $inputf (exit code $LASTEXITCODE)" -ForegroundColor Red
    }
}
