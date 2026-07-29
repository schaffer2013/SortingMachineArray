param(
    [int]$IntervalMinutes = 30,
    [string]$ApiUrl = 'http://sortingmachine.local:8000/api/system?refresh=true',
    [string]$StatePath = "$env:LOCALAPPDATA\SortingMachineArray\visual-index-watch-state.json",
    [string]$LogPath = "$env:LOCALAPPDATA\SortingMachineArray\logs\visual-index-watch.log"
)

$ErrorActionPreference = 'Stop'

function Ensure-ParentDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
}

function Write-Log {
    param([Parameter(Mandatory = $true)][string]$Message)
    Ensure-ParentDirectory -Path $LogPath
    $timestamp = (Get-Date).ToString('s')
    Add-Content -LiteralPath $LogPath -Value "[$timestamp] $Message"
}

function Read-State {
    if (-not (Test-Path -LiteralPath $StatePath)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Save-State {
    param([Parameter(Mandatory = $true)]$Payload)
    Ensure-ParentDirectory -Path $StatePath
    $Payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $StatePath
}

function Get-HeartbeatAgeMinutes {
    param([Parameter(Mandatory = $true)][object]$IsoValue)
    if (-not $IsoValue) {
        return $null
    }
    try {
        $heartbeat = [DateTimeOffset]::Parse([string]$IsoValue)
        return [math]::Round(((Get-Date).ToUniversalTime() - $heartbeat.UtcDateTime).TotalMinutes, 1)
    } catch {
        return $null
    }
}

try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $ApiUrl -TimeoutSec 60
    $status = $response.Content | ConvertFrom-Json
} catch {
    Write-Log "ERROR unable to query $ApiUrl : $($_.Exception.Message)"
    exit 1
}

$visual = $status.visual_index
$previous = Read-State
$heartbeatAge = Get-HeartbeatAgeMinutes -IsoValue $visual.last_heartbeat_at_utc
$progress = if ($visual.progress_message) { [string]$visual.progress_message } else { 'no progress message' }
$summary = "sha=$($status.current_sha) version=$($status.version) refreshing=$($visual.refreshing) current=$($visual.progress_current)/$($visual.progress_total) phase=$($visual.progress_phase) stage=$($visual.progress_stage) heartbeat_age_min=$heartbeatAge message=$progress"

Write-Log $summary

$stalled = $false
if ($visual.refreshing -and $previous) {
    $previousCurrent = $previous.visual_index.progress_current
    $previousHeartbeat = Get-HeartbeatAgeMinutes -IsoValue $previous.visual_index.last_heartbeat_at_utc
    if ($visual.progress_current -eq $previousCurrent -and $heartbeatAge -ne $null) {
        if (($previousHeartbeat -ne $null -and $heartbeatAge -gt $previousHeartbeat) -or $heartbeatAge -ge 45) {
            $stalled = $true
        }
    }
}

if ($stalled) {
    Write-Log "WARN possible stall detected: progress has not advanced since the prior check."
}

Save-State @{
    checked_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    stalled = $stalled
    api_url = $ApiUrl
    status = $status
}

