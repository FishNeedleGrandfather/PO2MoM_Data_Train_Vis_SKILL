param(
    [switch]$DryRun
)

# Move existing per-variant dataset files into simulation_A/dataset.
# Run after simulation on this machine has finished. Missing variants are normal.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$destinationDir = Join-Path $root 'dataset'

if (-not $DryRun) {
    New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
}

$moved = 0
$missing = 0
$conflicts = 0
$errors = 0
$planned = 0
foreach ($caseNumber in 1..5) {
    $caseId = "case$caseNumber"
    foreach ($index in 1..20) {
        $variantId = '{0}_{1:D2}' -f $caseId, $index
        $variantDir = Join-Path (Join-Path $root $caseId) $variantId
        $datasetName = 'dataset{0}_{1:D2}.pt' -f $caseNumber, $index
        $source = Join-Path $variantDir $datasetName
        $target = Join-Path $destinationDir $datasetName

        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            $missing++
            continue
        }
        if (Test-Path -LiteralPath $target) {
            $conflicts++
            Write-Warning "Target already exists; kept source: $datasetName"
            continue
        }
        if ($DryRun) {
            $planned++
            Write-Host "DRY RUN move: $datasetName"
            continue
        }
        try {
            Move-Item -LiteralPath $source -Destination $target -ErrorAction Stop
            $moved++
            Write-Host "Moved: $datasetName"
        } catch {
            $errors++
            Write-Warning ("{0}: {1}" -f $variantId, $_.Exception.Message)
        }
    }
}

Write-Host ("Done: moved={0}, absent={1}, existing target={2}, errors={3}, planned={4}; destination={5}" -f `
    $moved, $missing, $conflicts, $errors, $planned, $destinationDir)
if ($conflicts -gt 0 -or $errors -gt 0) { exit 1 }
