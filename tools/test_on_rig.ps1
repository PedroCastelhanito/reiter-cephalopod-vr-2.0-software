# Run static and automated tests on Windows without starting the managed rig app.
# First use: .\tools\test_on_rig.ps1 -Install
# Later runs: .\tools\test_on_rig.ps1
# Hardware-marked tests run only with -Rig and only when such tests are collected.
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Rig,
    [switch]$BuildTrackingNative,
    [string]$NvofSdkRoot,
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
        & $python -m pip install --editable '.[dev,acquisition,visual_stimulus,tracking]' 2>&1 |
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
    & $python -c 'import grpc, google.protobuf, pytest, pytest_asyncio, pydantic, setuptools, numpy, serial, pypylon, cv2, onnx, onnxruntime; import cephvr.control.v1.services_pb2; import cephvr.visual_stimulus.v1.services_pb2; import moderngl, glfw, av, imagecodecs, tifffile, OpenGL.GL' 2>&1 |
        Tee-Object -FilePath (Join-Path $output 'prerequisites.log') | Out-Host
    $prerequisiteExit = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $before
}
if ($prerequisiteExit -ne 0) {
    throw "Virtual environment lacks CephVR, acquisition/Visual Stimulus/Tracking, or test dependencies; use -Install. See $output\prerequisites.log"
}

if ($BuildTrackingNative) {
    if (-not $NvofSdkRoot) { throw '-BuildTrackingNative requires -NvofSdkRoot with API 2.0 headers.' }
    if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) { throw 'Install CMake, MSVC x64 tools and the CUDA Toolkit first.' }
    $nativeBuild = Join-Path $output 'tracking-native'
    & cmake -S (Join-Path $repo 'native\tracking') -B $nativeBuild -A x64 "-DNVOF_SDK_ROOT=$NvofSdkRoot"
    if ($LASTEXITCODE -ne 0) { throw 'Tracking native configuration failed.' }
    & cmake --build $nativeBuild --config Release
    if ($LASTEXITCODE -ne 0) { throw 'Tracking native compilation failed.' }
    & cmake --install $nativeBuild --config Release --prefix (Join-Path $repo 'src')
    if ($LASTEXITCODE -ne 0) { throw 'Tracking native installation failed.' }
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

# DIAGNOSTIC ONLY (rig-verification.md, "Windows venv interpreter process tree"):
# a venv's Scripts\python.exe may be a redirector that starts the base
# interpreter as a child. Print the spawned process tree so the owner can see
# whether such a pair exists. Never fails the run.
function Show-InterpreterProcessTree {
    $log = Join-Path $output 'interpreter-process-tree.log'
    try {
        $probe = 'import sys,time; print(sys.executable, sys._base_executable); time.sleep(3)'
        $process = Start-Process -FilePath $python -ArgumentList @('-c', ('"' + $probe + '"')) -PassThru -WindowStyle Hidden
        Start-Sleep -Milliseconds 1500
        $all = @(Get-CimInstance Win32_Process)
        $known = @($process.Id)
        $tree = @()
        $grew = $true
        while ($grew) {
            $grew = $false
            foreach ($candidate in $all) {
                if (($known -contains $candidate.ParentProcessId) -or ($known -contains $candidate.ProcessId)) {
                    if ($known -notcontains $candidate.ProcessId) {
                        $known += $candidate.ProcessId
                        $grew = $true
                    }
                }
            }
        }
        $tree = @($all | Where-Object { $known -contains $_.ProcessId } |
            Select-Object ProcessId, ParentProcessId, ExecutablePath)
        $lines = @("configured python: $python", "processes in the spawned tree: $($tree.Count)")
        foreach ($entry in $tree) {
            $lines += ("pid={0} parent={1} image={2}" -f $entry.ProcessId, $entry.ParentProcessId, $entry.ExecutablePath)
        }
        $lines | Tee-Object -FilePath $log | Out-Host
        [void]$process.WaitForExit(10000)
    } catch {
        Write-Host "Interpreter process-tree diagnostic failed: $($_.Exception.Message)"
    }
}
Show-InterpreterProcessTree

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
[void](Invoke-Logged 'module-boundaries' @('tools/check_backend_boundaries.py'))
[void](Invoke-Logged 'mypy-win32' @('-m', 'mypy', '--platform', 'win32', 'src/cephvr'))
[void](Invoke-Logged 'contracts-tracking' @('-m', 'unittest', 'discover', '-s', 'contracts/tracking', '-p', 'test_*.py'))
[void](Invoke-Logged 'tracking-schema-drift' @('contracts/tracking/schema_check.py'))
[void](Invoke-Logged 'contracts-visual_stimulus' @('-m', 'unittest', 'discover', '-s', 'contracts/visual_stimulus/tests', '-p', 'test_*.py'))
[void](Invoke-Logged 'visual-stimulus-schema-drift' @('contracts/visual_stimulus/generate_schemas.py', '--check'))
# tests/visual_stimulus includes pure implementation and authenticated loopback checks. Installing
# the graphics extra does not turn these into physical rendering/encoding acceptance.
# Explicit hardware procedures remain in reports/rig-verification.md.
$junit = Join-Path $output 'pytest.xml'
$pytestArgs = @('-m', 'pytest', '-q', '--junitxml', $junit)
if (-not $Rig) { $pytestArgs += @('-m', 'not rig') }
$pytestArgs += 'tests'
[void](Invoke-Logged 'pytest' $pytestArgs)
$packageDirectory = Join-Path $output 'packages'
New-Item -ItemType Directory -Path $packageDirectory -Force | Out-Null
[void](Invoke-Logged 'package' @('-m', 'build', '--no-isolation', '--outdir', $packageDirectory))

$results | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $output 'summary.json')
Write-Host "Logs and JUnit: $output"
if (@($results | Where-Object { $_.exit_code -ne 0 }).Count -gt 0) { exit 1 }
exit 0
