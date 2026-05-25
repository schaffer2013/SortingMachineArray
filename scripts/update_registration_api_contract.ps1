param(
    [string]$Repository = "schaffer2013/magic-the-collecting",
    [string]$Branch = "main",
    [string]$SourcePath = "API.md",
    [string]$OutputPath = "docs/contracts/registration-service/API.md",
    [string]$MetadataPath = "docs/contracts/registration-service/API.source.json",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function ConvertTo-GitHubEncodedPath {
    param([string]$Path)
    return ($Path -split "/" | ForEach-Object { [System.Uri]::EscapeDataString($_) }) -join "/"
}

$headers = @{
    "Accept" = "application/vnd.github+json"
    "User-Agent" = "SortingMachineArray-contract-updater"
}

$encodedPath = ConvertTo-GitHubEncodedPath $SourcePath
$commitsUri = "https://api.github.com/repos/$Repository/commits?sha=$Branch&path=$encodedPath&per_page=1"
$latestCommit = Invoke-RestMethod -Uri $commitsUri -Headers $headers

if (-not $latestCommit -or $latestCommit.Count -eq 0) {
    throw "No commit found for $Repository/$SourcePath on $Branch"
}

$commitSha = if ($latestCommit -is [array]) { $latestCommit[0].sha } else { $latestCommit.sha }
$rawUri = "https://raw.githubusercontent.com/$Repository/$commitSha/$SourcePath"
$blobUri = "https://github.com/$Repository/blob/$commitSha/$SourcePath"

$existingCommit = $null
if (Test-Path $MetadataPath) {
    try {
        $existingMetadata = Get-Content -Raw -Path $MetadataPath | ConvertFrom-Json
        $existingCommit = $existingMetadata.source_commit
    }
    catch {
        Write-Warning "Could not parse existing metadata at $MetadataPath; refreshing it."
    }
}

if (-not $Force -and (Test-Path $OutputPath) -and $existingCommit -eq $commitSha) {
    Write-Host "$OutputPath is already current at $commitSha"
    exit 0
}

$outputDirectory = Split-Path -Parent $OutputPath
$metadataDirectory = Split-Path -Parent $MetadataPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $metadataDirectory | Out-Null

Invoke-WebRequest -Uri $rawUri -Headers @{ "User-Agent" = "SortingMachineArray-contract-updater" } -OutFile $OutputPath

$metadata = [ordered]@{
    repository = $Repository
    branch = $Branch
    path = $SourcePath
    source_commit = $commitSha
    source_url = $blobUri
    raw_url = $rawUri
    fetched_at_utc = (Get-Date).ToUniversalTime().ToString("o")
}

$metadata | ConvertTo-Json | Set-Content -Path $MetadataPath -Encoding UTF8

Write-Host "Updated $OutputPath from $blobUri"
Write-Host "Wrote metadata to $MetadataPath"
