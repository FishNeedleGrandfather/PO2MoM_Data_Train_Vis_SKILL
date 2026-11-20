param(
    [ValidateRange(1, 3600)]
    [int]$IntervalSeconds = 5,
    [switch]$Once
)

# Read-only monitor. Run this in a second PowerShell window.
$Root = $PSScriptRoot
$LockPath = Join-Path $Root 'RUNNING.lock'
$StopPath = Join-Path $Root 'STOP_REQUESTED'

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try {
        return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Parse-Stamp {
    param($Value)
    if (-not $Value) { return [DateTimeOffset]::MinValue }
    try { return [DateTimeOffset]::Parse([string]$Value) }
    catch { return [DateTimeOffset]::MinValue }
}

function Show-Snapshot {
    $lockInfo = Read-JsonFile $LockPath
    $runner = $null
    $lockStart = [DateTimeOffset]::MinValue
    if ($lockInfo -and $lockInfo.pid) {
        $lockStart = Parse-Stamp $lockInfo.started_at
        try {
            $candidate = Get-Process -Id ([int]$lockInfo.pid) -ErrorAction Stop
            if ($candidate.ProcessName -match '^python(w)?$') { $runner = $candidate }
        } catch {}
    }

    $now = [DateTimeOffset]::Now
    Write-Host ("PO2MoM variant monitor   {0}" -f $now.ToString('yyyy-MM-dd HH:mm:ss'))
    if ($runner) {
        Write-Host ("Runner PID {0}; Python memory {1:N1} GiB; started {2}" -f `
            $runner.Id, ($runner.WorkingSet64 / 1GB), $lockStart.ToLocalTime().ToString('MM-dd HH:mm:ss'))
    } elseif (Test-Path -LiteralPath $LockPath) {
        Write-Host 'RUNNING.lock exists, but its Python PID is not running (possibly stale).' -ForegroundColor Yellow
    } else {
        Write-Host 'Runner: not running'
    }
    if (Test-Path -LiteralPath $StopPath) {
        Write-Host 'STOP_REQUESTED is present: workers will stop at a safe boundary.' -ForegroundColor Yellow
    }

    $total = @{ Archived = 0; Failed = 0; Active = 0; Partial = 0; Pending = 0 }
    $recentFailures = @()
    foreach ($caseNumber in 1..5) {
        $caseId = "case$caseNumber"
        $counts = @{ Archived = 0; Failed = 0; Active = 0; Partial = 0; Pending = 0 }
        $activeLines = @()
        foreach ($index in 1..20) {
            $variantId = '{0}_{1:D2}' -f $caseId, $index
            $directory = Join-Path (Join-Path $Root $caseId) $variantId
            $archive = Read-JsonFile (Join-Path $directory 'ARCHIVED.json')
            $failure = Read-JsonFile (Join-Path $directory 'failure.json')
            $status = Read-JsonFile (Join-Path $directory 'status.json')
            $statusTime = if ($status) { Parse-Stamp $status.updated_at } else { [DateTimeOffset]::MinValue }
            $failureTime = if ($failure) { Parse-Stamp $failure.time } else { [DateTimeOffset]::MinValue }
            $stage = if ($status) { [string]$status.stage } else { '' }

            if ($archive) {
                $state = 'Archived'
            } elseif ($failure -and $failureTime -ge $statusTime) {
                $state = 'Failed'
                $recentFailures += [pscustomobject]@{
                    Time = $failureTime; Id = $variantId; Stage = $failure.stage; Error = $failure.error
                }
            } elseif ($runner -and $status -and $statusTime -ge $lockStart -and
                      $stage -in @('preparing', 'solving', 'building_dataset', 'cleaning')) {
                $state = 'Active'
                $age = [Math]::Max(0, [Math]::Floor(($now - $statusTime).TotalSeconds))
                $method = if ($status.method) { [string]$status.method } else { '-' }
                $angle = if ($status.active) { [string]$status.active } else { '-' }
                $activeLines += ('  {0}: {1}/93  {2}  {3}  {4}  last update {5}s ago' -f `
                    $variantId, $status.completed_angles, $stage, $angle, $method, $age)
            } elseif ($status -and $stage -ne 'preparing') {
                $state = 'Partial'
            } else {
                $state = 'Pending'
            }
            $counts[$state]++
            $total[$state]++
        }
        Write-Host ('{0}: archived={1}/20  active={2}  failed={3}  partial={4}  pending={5}' -f `
            $caseId, $counts.Archived, $counts.Active, $counts.Failed, $counts.Partial, $counts.Pending)
        foreach ($line in $activeLines) { Write-Host $line -ForegroundColor Cyan }
    }

    Write-Host ('TOTAL: archived={0}/100  active={1}  failed={2}  partial={3}  pending={4}' -f `
        $total.Archived, $total.Active, $total.Failed, $total.Partial, $total.Pending)
    try {
        $driveRoot = [System.IO.Path]::GetPathRoot($Root)
        $drive = [System.IO.DriveInfo]::new($driveRoot)
        Write-Host ('Free space on {0}: {1:N1} GiB' -f $driveRoot, ($drive.AvailableFreeSpace / 1GB))
    } catch {}

    if ($recentFailures.Count -gt 0) {
        Write-Host 'Recent failed variants:' -ForegroundColor Yellow
        foreach ($item in ($recentFailures | Sort-Object Time -Descending | Select-Object -First 5)) {
            Write-Host ('  {0} [{1}] {2}' -f $item.Id, $item.Stage, $item.Error) -ForegroundColor Yellow
        }
    }
    Write-Host 'Status files show the current run; only a validated dataset plus ARCHIVED.json counts as archived.'
}

do {
    if (-not $Once) { Clear-Host }
    Show-Snapshot
    if ($Once) { break }
    Write-Host ("Refresh every {0}s. Ctrl+C or close this window to stop monitoring only." -f $IntervalSeconds)
    Start-Sleep -Seconds $IntervalSeconds
} while ($true)
