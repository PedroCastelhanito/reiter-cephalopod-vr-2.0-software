# Run static and automated tests on Windows without starting the managed rig app.
# First use: .\tools\test_on_rig.ps1 -Install
# Later runs: .\tools\test_on_rig.ps1
# Hardware-marked tests run only with -Rig and only when such tests are collected.
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Rig,
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venv = Join-Path $repo '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
$runId = Get-Date -Format 'yyyyMMdd-HHmmss'
$output = if ($OutputDirectory) {
    [IO.Path]::GetFullPath($OutputDirectory)
} else {
    Join-Path $env:LOCALAPPDATA ("CephVR2\TestRuns\" + $runId)
}
New-Item -ItemType Directory -Path $output -Force | Out-Null
Set-Location $repo

function Assert-Python311([string]$Executable, [string[]]$Prefix) {
    $version = & $Executable @Prefix -c "import sys; print('%d.%d.%d' % sys.version_info[:3]); sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "CephVR requires Python 3.11; found '$version' from $Executable."
    }
    Write-Host "Python $version"
}

if ($Install) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $base = 'py'
        $prefix = @('-3.11')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $base = 'python'
        $prefix = @()
    } else {
        throw 'Install Python 3.11 (including its Windows launcher) before -Install.'
    }
    Assert-Python311 $base $prefix
    if (-not (Test-Path $python)) {
        & $base @prefix -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 virtual environment creation failed.' }
    }
    Assert-Python311 $python @()
    $before = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $python -m pip install --editable '.[dev]' 2>&1 |
            Tee-Object -FilePath (Join-Path $output 'install.log') | Out-Host
        $installExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $before
    }
    if ($installExit -ne 0) { throw "Dependency installation failed; see $output\install.log" }
} elseif (-not (Test-Path $python)) {
    throw "Missing $python. Run this script once with -Install (network/package access required)."
}

Assert-Python311 $python @()
$before = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $python -c 'import grpc, google.protobuf, pytest, pytest_asyncio, pydantic, setuptools; import cephvr.control.v1.services_pb2' 2>&1 |
        Tee-Object -FilePath (Join-Path $output 'prerequisites.log') | Out-Host
    $prerequisiteExit = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $before
}
if ($prerequisiteExit -ne 0) {
    throw "Virtual environment lacks CephVR/test dependencies; use -Install. See $output\prerequisites.log"
}

$results = @()
function Invoke-Logged([string]$Name, [string[]]$Arguments) {
    $log = Join-Path $output ($Name + '.log')
    Write-Host "Running $Name; log: $log"
    $before = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $python @Arguments 2>&1 | Tee-Object -FilePath $log | Out-Host
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $before
    }
    $script:results += [pscustomobject]@{ step = $Name; exit_code = $code; log = $log }
    Write-Host "$Name exit code: $code"
    return $code
}

if ($Rig) {
    $collected = Invoke-Logged 'rig-collection' @('-m', 'pytest', '--collect-only', '-q', '-m', 'rig', 'tests')
    if ($collected -ne 0) {
        $results | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $output 'summary.json')
        throw "No runnable rig-marked tests were collected (or collection failed). Hardware tests were not started. See $output"
    }
}

[void](Invoke-Logged 'syntax' @('-m', 'compileall', '-q', 'src', 'tests'))
[void](Invoke-Logged 'ruff' @('-m', 'ruff', 'check', 'src', 'tests', 'tools'))
[void](Invoke-Logged 'format' @('-m', 'ruff', 'format', '--check', 'src', 'tests', 'tools'))
[void](Invoke-Logged 'mypy-win32' @('-m', 'mypy', '--platform', 'win32', 'src/cephvr'))
[void](Invoke-Logged 'contracts-tracking' @('-m', 'unittest', 'discover', '-s', 'contracts/tracking', '-p', 'test_*.py'))
[void](Invoke-Logged 'contracts-vr' @('-m', 'unittest', 'discover', '-s', 'contracts/vr/tests', '-p', 'test_*.py'))
$junit = Join-Path $output 'pytest.xml'
$pytestArgs = @('-m', 'pytest', '-q', '--junitxml', $junit)
if (-not $Rig) { $pytestArgs += @('-m', 'not rig') }
$pytestArgs += 'tests'
[void](Invoke-Logged 'pytest' $pytestArgs)
[void](Invoke-Logged 'package' @('-m', 'build', '--no-isolation', '--outdir', (Join-Path $output 'packages')))

$results | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $output 'summary.json')
Write-Host "Logs and JUnit: $output"
if (@($results | Where-Object { $_.exit_code -ne 0 }).Count -gt 0) { exit 1 }
exit 0
