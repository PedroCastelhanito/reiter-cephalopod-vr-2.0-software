param([string]$ManifestName = 'cleanup.json')
$ErrorActionPreference = 'Stop'
if ([IO.Path]::GetFileName($ManifestName) -ne $ManifestName) { throw 'Manifest must be a filename within evidence' }
$rigRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$rigPrefix = $rigRoot.TrimEnd('\') + '\'
$rigTargets = [System.Collections.Generic.List[string]]::new()
$rigPending = [System.Collections.Generic.Stack[string]]::new()
$rigPending.Push($rigRoot)
$rigExcluded = @('.git', '.venv', '.agents', '.codex', '.vscode', '.local-spikeglx-sdk', 'cephvr-data', 'native')
$rigCaches = @('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache')
while ($rigPending.Count -gt 0) {
    $rigDirectory = $rigPending.Pop()
    foreach ($rigChild in Get-ChildItem -LiteralPath $rigDirectory -Directory -Force) {
        if (($rigChild.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
        if ($rigChild.Name -in $rigExcluded) { continue }
        if ($rigChild.Name -in $rigCaches) { $rigTargets.Add($rigChild.FullName) }
        else { $rigPending.Push($rigChild.FullName) }
    }
}
$rigPackages = Join-Path $PSScriptRoot 'automated/packages'
if (Test-Path -LiteralPath $rigPackages) {
    $rigArtifacts = @(Get-ChildItem -LiteralPath $rigPackages -File | ForEach-Object {
        @{ name = $_.Name; bytes = $_.Length; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    })
    ConvertTo-Json -InputObject $rigArtifacts -Depth 4 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'packaging-artifacts.json') -Encoding utf8
    $rigTargets.Add($rigPackages)
}
$rigRemoved = @()
if ($ManifestName -eq 'camera-selection-cleanup.json') {
    foreach ($rigTmpName in @('camera-selection-tmp', 'camera-selection-tmp-2', 'camera-selection-tmp-3', 'camera-selection-tmp-4')) {
        $rigTmpPath = Join-Path $PSScriptRoot $rigTmpName
        if (Test-Path -LiteralPath $rigTmpPath) { $rigTargets.Add($rigTmpPath) }
    }
}
if ($ManifestName -eq 'tracking-health-cleanup.json') {
    $rigTmpPath = Join-Path $PSScriptRoot 'tracking-health-tmp'
    if (Test-Path -LiteralPath $rigTmpPath) { $rigTargets.Add($rigTmpPath) }
}
if ($ManifestName -eq 'ino-upload-cleanup.json') {
    $rigTmpPath = Join-Path $PSScriptRoot 'ino-upload-tests-tmp'
    if (Test-Path -LiteralPath $rigTmpPath) { $rigTargets.Add($rigTmpPath) }
}
foreach ($rigTarget in $rigTargets) {
    $rigResolved = (Resolve-Path -LiteralPath $rigTarget).Path
    if (-not $rigResolved.StartsWith($rigPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Cleanup outside workspace: $rigResolved" }
    $rigItem = Get-Item -LiteralPath $rigResolved -Force
    if (($rigItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Cleanup target is a reparse point: $rigResolved" }
    $rigLinks = @(Get-ChildItem -LiteralPath $rigResolved -Recurse -Force | Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 })
    if ($rigLinks.Count -gt 0) { throw "Cleanup subtree contains a reparse point: $rigResolved" }
    $rigFiles = @(Get-ChildItem -LiteralPath $rigResolved -File -Recurse -Force)
    $rigBytes = ($rigFiles | Measure-Object Length -Sum).Sum
    Remove-Item -LiteralPath $rigResolved -Recurse -Force
    if (Test-Path -LiteralPath $rigResolved) { throw "Cleanup unconfirmed: $rigResolved" }
    $rigRemoved += @{ path = $rigResolved; files = $rigFiles.Count; bytes = $rigBytes; absent = $true }
}
ConvertTo-Json -InputObject @{ removed = $rigRemoved; scope = 'workspace Python/tool caches, this run''s reproducible packages and explicitly named camera-selection or Tracking-health test temporary directories only; preserve environments, SDK/native libraries, scientific data, raw evidence and emergency/recovery outputs' } -Depth 6 | Set-Content -LiteralPath (Join-Path $PSScriptRoot $ManifestName) -Encoding utf8
Write-Output "Removed $($rigRemoved.Count) verified workspace targets; retained package hashes and all unique evidence."
