param(
    [ValidateSet('preview-presentation-cleanup.json', 'replacement-cleanup.json', 'replacement-msix-cleanup.json')]
    [string]$InventoryName = 'preview-presentation-cleanup.json'
)
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$prefix = $workspace.TrimEnd('\') + '\'
$tracked = @(git -C $workspace ls-files)
$candidates = @()
foreach ($owner in @('src', 'tests', 'tools', 'scripts')) {
    $path = Join-Path $workspace $owner
    if (Test-Path -LiteralPath $path) {
        $candidates += Get-ChildItem -LiteralPath $path -Directory -Recurse -Force |
            Where-Object { $_.Name -eq '__pycache__' }
    }
}
foreach ($name in @('.pytest_cache', '.ruff_cache', '.mypy_cache')) {
    $path = Join-Path $workspace $name
    if (Test-Path -LiteralPath $path) { $candidates += Get-Item -LiteralPath $path -Force }
}
$removed = @()
foreach ($item in $candidates) {
    $absolute = (Resolve-Path -LiteralPath $item.FullName).Path
    if (-not $absolute.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Outside workspace: $absolute" }
    $relative = $absolute.Substring($prefix.Length).Replace('\', '/') + '/'
    if (@($tracked | Where-Object { $_.StartsWith($relative, [StringComparison]::OrdinalIgnoreCase) }).Count) { throw "Tracked target: $absolute" }
    $contents = @(Get-ChildItem -LiteralPath $absolute -Recurse -Force)
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        @($contents | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw "Reparse target: $absolute" }
    $files = @($contents | Where-Object { -not $_.PSIsContainer })
    $bytes = ($files | Measure-Object -Property Length -Sum).Sum
    $removed += [pscustomobject]@{path=$absolute; files=$files.Count; bytes=[long]$bytes}
    Remove-Item -LiteralPath $absolute -Recurse -Force
}
$inventory = Join-Path $PSScriptRoot $InventoryName
if (Test-Path -LiteralPath $inventory) { $removed = @(Get-Content -LiteralPath $inventory -Raw | ConvertFrom-Json) + $removed }
ConvertTo-Json -InputObject @($removed) -Depth 4 | Set-Content -LiteralPath $inventory -Encoding utf8
$fileTotal = ($removed | Measure-Object -Property files -Sum).Sum
$byteTotal = ($removed | Measure-Object -Property bytes -Sum).Sum
Write-Output "Verified disposable cache cleanup: $($removed.Count) targets / $fileTotal files / $byteTotal bytes."
