param(
    [Parameter(Mandatory)] [string]$WorkRoot,
    [ValidateSet('Stage', 'Check', 'Prepare', 'Solve')] [string]$Mode = 'Stage',
    [ValidatePattern('^case[1-5]_(0[1-9]|1[0-9]|20)$')] [string]$Variant,
    [switch]$Apply,
    [ValidateRange(1, 256)] [int]$Np = 6,
    [ValidateRange(1, 93)] [int]$LimitAngles = 2,
    [string]$FekoBin,
    [string]$Python = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$work = [IO.Path]::GetFullPath($WorkRoot)
if (-not [IO.Path]::IsPathRooted($WorkRoot) -or -not (Test-Path -LiteralPath $work -PathType Container)) {
    throw 'WorkRoot must be an existing absolute directory.'
}
$source = $PSScriptRoot
$relativeFiles = @(
    'simulation_A/run_variants.py',
    'simulation_A/prepare_meshes.ps1',
    'simulation_A/monitor_variants.ps1',
    'simulation_A/collect_datasets.ps1',
    'simulation_A/dataset/comb.py',
    'simulation_A/automation/setup_variants.py',
    'simulation_A/automation/prepare_variant.lua',
    'simulation_A/automation/verify_prepared_meshes.py',
    'simulation_smallbatch/run_simulations.py',
    'simulation_smallbatch/dataset_builder_AllAngle.py',
    'simulation_smallbatch/datasetbuilder_1ghz.py',
    'simulation_smallbatch/cluster_6d.py'
)

$missing = 0
foreach ($relative in $relativeFiles) {
    $src = Join-Path $source $relative
    $dst = Join-Path $work $relative
    if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { throw "Bundle incomplete: $src" }
    if (Test-Path -LiteralPath $dst) {
        if ((Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash -ne
            (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash) {
            throw "Existing code differs; inspect before changing: $dst"
        }
        continue
    }
    $missing++
    if ($Apply) {
        $parent = Split-Path -Parent $dst
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Copy-Item -LiteralPath $src -Destination $dst
        Write-Host "Staged $relative"
    } else {
        Write-Host "Would stage $relative"
    }
}
if (-not $Apply -and $missing -gt 0) {
    Write-Host "Preview: $missing code files would be staged; no solver started."
    if ($Mode -ne 'Stage') { throw 'Stage code with -Apply first, then run the selected mode.' }
    return
}
if ($Mode -eq 'Stage') { Write-Host "Code ready in $work"; return }
if (-not $Variant) { throw 'Check, Prepare, and Solve require -Variant.' }
if (($Mode -eq 'Prepare' -or $Mode -eq 'Solve') -and -not $Apply) {
    throw 'Prepare and Solve write outputs; pass -Apply.'
}
$runner = Join-Path $work 'simulation_A/run_variants.py'
$argv = @($runner, '--variant', $Variant)
switch ($Mode) {
    'Check' { $argv += '--check-inputs' }
    'Prepare' { $argv += @('--prepare-only', '--limit-angles', [string]$LimitAngles) }
    'Solve' {
        $argv += @('--np', [string]$Np)
        if ($FekoBin) { $argv += @('--feko-bin', $FekoBin) }
    }
}
& $Python @argv
if ($LASTEXITCODE -ne 0) { throw "$Mode failed with exit code $LASTEXITCODE" }
