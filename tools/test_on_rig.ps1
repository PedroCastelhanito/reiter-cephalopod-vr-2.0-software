# Run static and automated tests on Windows without starting the managed rig app.
# First use: .\tools\test_on_rig.ps1 -Install
# Later runs: .\tools\test_on_rig.ps1
# Hardware-marked tests run only with -Rig and only when such tests are collected.
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Rig,
    [switch]$BuildWindowsNative,
    [switch]$BuildTrackingNative,
    [switch]$BuildAcquisitionNative,
    [string]$NvofSdkRoot,
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venv = Join-Path $repo '.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
$python = $venvPython
$managedPython = Join-Path $venv 'Scripts\cephvr-python.exe'
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
    if (Test-Path $venvPython) {
        $base = $venvPython
        $prefix = @()
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $base = 'py'
        $prefix = @('-3.11')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $base = 'python'
        $prefix = @()
    } else {
        throw 'Install Python 3.11 (including its Windows launcher) before -Install.'
    }
    Assert-Python311 $base $prefix
    if (-not (Test-Path $venvPython)) {
        & $base @prefix -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 virtual environment creation failed.' }
    }
    Assert-Python311 $venvPython @()
    $before = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $venvPython -m pip install --editable '.[dev,acquisition,visual_stimulus,tracking]' 2>&1 |
            Tee-Object -FilePath (Join-Path $output 'install.log') | Out-Host
        $installExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $before
    }
    if ($installExit -ne 0) { throw "Dependency installation failed; see $output\install.log" }
    & $venvPython -m cephvr.platform.windows.python_runtime --prepare
    if ($LASTEXITCODE -ne 0) { throw 'Preparing the managed CephVR Python executable failed.' }
} elseif (-not (Test-Path $venvPython)) {
    throw "Missing $venvPython. Run this script once with -Install (network/package access required)."
}

if (-not (Test-Path $managedPython)) { throw "Missing $managedPython. Run this script with -Install." }
Assert-Python311 $python @()
& $managedPython -m cephvr.platform.windows.python_runtime --verify
if ($LASTEXITCODE -ne 0) { throw 'The prepared CephVR Python executable is stale; run -Install.' }

function Get-CMakeExecutable {
    $fromPath = Get-Command cmake -ErrorAction SilentlyContinue
    if ($fromPath) { return $fromPath.Source }

    $programFilesX86 = [Environment]::GetFolderPath('ProgramFilesX86')
    $vswhere = Join-Path $programFilesX86 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path $vswhere) {
        $found = & $vswhere -latest -products '*' `
            -requires Microsoft.VisualStudio.Component.VC.CMake.Project `
            -find 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
        foreach ($candidate in $found) {
            if (Test-Path $candidate) { return $candidate }
        }
    }
    throw 'CMake was not found on PATH or in the installed Visual Studio CMake component.'
}

if ($Install -or $BuildWindowsNative) {
    $cmake = Get-CMakeExecutable
    $atomicBuild = Join-Path $output 'windows-atomics'
    & $cmake -S (Join-Path $repo 'native\windows') -B $atomicBuild -A x64
    if ($LASTEXITCODE -ne 0) { throw 'Windows atomics configuration failed.' }
    & $cmake --build $atomicBuild --config Release
    if ($LASTEXITCODE -ne 0) { throw 'Windows atomics compilation failed.' }
    & $cmake --install $atomicBuild --config Release --prefix (Join-Path $repo 'src')
    if ($LASTEXITCODE -ne 0) { throw 'Windows atomics installation failed.' }
}

$atomicsDll = Join-Path $repo 'src\cephvr\platform\windows\cephvr_atomics.dll'
if (-not (Test-Path $atomicsDll)) {
    throw "Missing $atomicsDll. Run .\tools\test_on_rig.ps1 -BuildWindowsNative first."
}

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

if ($BuildAcquisitionNative) {
    & $python (Join-Path $repo 'tools/build_pylon_wait.py')
    if ($LASTEXITCODE -ne 0) { throw 'Acquisition native wait bridge compilation failed.' }
}

if ($BuildTrackingNative) {
    if (-not $NvofSdkRoot) { throw '-BuildTrackingNative requires -NvofSdkRoot with API 2.0 headers.' }
    $cmake = Get-CMakeExecutable
    $nativeBuild = Join-Path $output 'tracking-native'
    & $cmake -S (Join-Path $repo 'native\tracking') -B $nativeBuild -A x64 "-DNVOF_SDK_ROOT=$NvofSdkRoot"
    if ($LASTEXITCODE -ne 0) { throw 'Tracking native configuration failed.' }
    & $cmake --build $nativeBuild --config Release
    if ($LASTEXITCODE -ne 0) { throw 'Tracking native compilation failed.' }
    & $cmake --install $nativeBuild --config Release --prefix (Join-Path $repo 'src')
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
