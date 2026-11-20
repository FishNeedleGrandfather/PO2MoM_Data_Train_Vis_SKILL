param(
    [ValidateSet("case1", "case2", "case3", "case4", "case5")]
    [string]$CaseId,
    [string]$VariantId,
    [switch]$Force,
    [string]$FekoBin,
    [string]$Python = 'python'
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $FekoBin) {
    $FekoBin = @('E:\Altair\feko\2025\feko\bin', 'C:\Program Files\Altair\2025\feko\bin') |
        Where-Object { Test-Path -LiteralPath (Join-Path $_ 'cadfeko.exe') } |
        Select-Object -First 1
}
if (-not $FekoBin) { throw 'CADFEKO not found; pass -FekoBin.' }
$Cadfeko = Join-Path $FekoBin "cadfeko.exe"
if (-not (Test-Path -LiteralPath $Cadfeko)) {
    throw "CADFEKO was not found: $Cadfeko"
}

function Set-VariantStatus {
    param(
        [System.IO.DirectoryInfo]$Directory,
        [string]$Status,
        [string]$Message = ""
    )
    $metadataPath = Join-Path $Directory.FullName "variant_parameters.json"
    if (-not (Test-Path -LiteralPath $metadataPath)) { return }
    $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    $metadata.status = $Status
    $metadata | Add-Member -NotePropertyName "status_updated_at" -NotePropertyValue ((Get-Date).ToString("o")) -Force
    if ($Message) {
        $metadata | Add-Member -NotePropertyName "status_message" -NotePropertyValue $Message -Force
    } elseif ($metadata.PSObject.Properties.Name -contains "status_message") {
        $metadata.PSObject.Properties.Remove("status_message")
    }
    $metadata | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $metadataPath -Encoding UTF8
}

& $Python (Join-Path $Root "automation\setup_variants.py") --root $Root
if ($LASTEXITCODE -ne 0) { throw "Variant configuration generation failed" }

$cases = if ($CaseId) { @($CaseId) } else { @("case1", "case2", "case3", "case4", "case5") }
$prepared = 0
$skipped = 0
$failures = @()
foreach ($case in $cases) {
    $dirs = Get-ChildItem -LiteralPath (Join-Path $Root $case) -Directory |
        Where-Object { $_.Name -match "^${case}_\d{2}$" } |
        Sort-Object Name
    if ($VariantId) { $dirs = @($dirs | Where-Object Name -eq $VariantId) }
    foreach ($dir in $dirs) {
        $id = $dir.Name
        $cfm = Join-Path $dir.FullName "$id.cfm"
        $nas = Join-Path $dir.FullName "$id.nas"
        $map = Join-Path $dir.FullName "$id.map"
        if (-not $Force -and (Test-Path $cfm) -and (Test-Path $nas) -and (Test-Path $map) -and
            (Get-Item $cfm).Length -gt 0 -and (Get-Item $nas).Length -gt 0 -and (Get-Item $map).Length -gt 0) {
            Set-VariantStatus -Directory $dir -Status "mesh_prepared"
            Write-Output "${id}: mesh already complete"
            $skipped += 1
            continue
        }

        try {
            foreach ($name in @("$id.cfx", "$id.cfx.bak", "$id.pre", "$id.cfm", "$id.nas", "$id.map", "prepare.stdout.log", "prepare.stderr.log", "PREPARE_FAILED.json")) {
                $path = Join-Path $dir.FullName $name
                if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
            }

            Write-Output "${id}: applying parameters and meshing"
            $out = Join-Path $dir.FullName "prepare.stdout.log"
            $err = Join-Path $dir.FullName "prepare.stderr.log"
            $process = Start-Process -FilePath $Cadfeko `
                -ArgumentList @("--non-interactive", "--platform", "minimal", "--run-script", (Join-Path $dir.FullName "prepare_variant_run.lua")) `
                -WorkingDirectory $dir.FullName -RedirectStandardOutput $out -RedirectStandardError $err `
                -WindowStyle Hidden -Wait -PassThru
            if ($process.ExitCode -ne 0) {
                throw "CADFEKO failed with exit code $($process.ExitCode); see $out and $err"
            }
            foreach ($path in @($cfm, $nas, $map)) {
                if (-not (Test-Path -LiteralPath $path) -or (Get-Item $path).Length -eq 0) {
                    throw "Expected output is missing or empty: $path"
                }
            }
            Set-VariantStatus -Directory $dir -Status "mesh_prepared"
            Write-Output "${id}: mesh prepared"
            $prepared += 1
        } catch {
            $message = $_.Exception.Message
            $failureRecord = [ordered]@{
                variant_id = $id
                failed_at = (Get-Date).ToString("o")
                error = $message
                stdout_log = "prepare.stdout.log"
                stderr_log = "prepare.stderr.log"
            }
            $failureRecord | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dir.FullName "PREPARE_FAILED.json") -Encoding UTF8
            Set-VariantStatus -Directory $dir -Status "prepare_failed" -Message $message
            $failures += $id
            Write-Warning "${id}: $message"
        }
    }
}

Write-Output "Preparation summary: prepared=$prepared skipped=$skipped failed=$($failures.Count)"
if ($failures.Count -gt 0) {
    Write-Output ("Failed variants: " + ($failures -join ", "))
    exit 1
}
