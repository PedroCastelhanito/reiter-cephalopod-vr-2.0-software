$ErrorActionPreference = 'Stop'

$Repository = 'C:\Dev\projects\reiter-cephalopod-vr\reiter-cephalopod-vr-2.0-software'
$Python = Join-Path $Repository '.venv\Scripts\python.exe'
$Evidence = Join-Path $Repository 'reports\rig-audit-2026-10-01'
$Scratch = Join-Path $Repository '.symlink-elevated-tmp'
$FocusedBase = Join-Path $Scratch 'focused'
$FullBase = Join-Path $Scratch 'full'
$TokenLog = Join-Path $Evidence 'python-runtime-elevated-final-token.log'
$PrepareLog = Join-Path $Evidence 'python-runtime-elevated-final-prepare.log'
$VerifyLog = Join-Path $Evidence 'python-runtime-elevated-final-verify.log'
$FocusedLog = Join-Path $Evidence 'python-runtime-elevated-final-focused.log'
$FocusedXml = Join-Path $Evidence 'python-runtime-elevated-final-focused.xml'
$FullLog = Join-Path $Evidence 'python-runtime-elevated-final-full.log'
$FullXml = Join-Path $Evidence 'python-runtime-elevated-final-full.xml'
$Completion = Join-Path $Evidence 'python-runtime-elevated-final-completion.json'
$PrepareExit = $null
$VerifyExit = $null
$FocusedExit = $null
$FullExit = $null
$Failure = $null
$PrepareCommand = "$Python -m cephvr.platform.windows.python_runtime --prepare"
$VerifyCommand = "$Python -m cephvr.platform.windows.python_runtime --verify"
$FullCommand = "$Python -m pytest tests -q -rs --basetemp=$FullBase --junitxml=$FullXml"
$FocusedCommand = "$Python -m pytest -q -rs --basetemp=$FocusedBase --junitxml=$FocusedXml tests/platform/test_windows_native_on_rig.py::test_prepared_python_runtime_rejects_stale_or_mismatched_files tests/platform/test_windows_native_on_rig.py::test_managed_python_entry_preserves_identity_prefix_and_bootstrap"
$Cleanup = [System.Collections.Generic.List[string]]::new()

function Remove-VerifiedTree([string]$Path, [string]$Parent) {
    $FullPath = [IO.Path]::GetFullPath($Path)
    $FullParent = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    if (-not $FullPath.StartsWith($FullParent, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing cleanup outside expected parent: $FullPath"
    }
    if (-not (Test-Path -LiteralPath $FullPath)) { return $false }
    $Entry = Get-Item -LiteralPath $FullPath -Force
    if (($Entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing recursive cleanup of reparse point: $FullPath"
    }
    Remove-Item -LiteralPath $FullPath -Recurse -Force
    return $true
}

Set-Location -LiteralPath $Repository
try {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
    $IsAdministrator = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $IsAdministrator) {
        throw 'This final runtime verification requires an elevated administrator token.'
    }
    & whoami.exe /all 2>&1 | Set-Content -LiteralPath $TokenLog -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "whoami /all failed with exit code $LASTEXITCODE" }

    & $Python -m cephvr.platform.windows.python_runtime --prepare 2>&1 |
        Tee-Object -FilePath $PrepareLog
    $PrepareExit = $LASTEXITCODE
    if ($PrepareExit -ne 0) { throw "runtime preparation failed with exit code $PrepareExit" }

    & $Python -m cephvr.platform.windows.python_runtime --verify 2>&1 |
        Tee-Object -FilePath $VerifyLog
    $VerifyExit = $LASTEXITCODE
    if ($VerifyExit -ne 0) { throw "runtime verification failed with exit code $VerifyExit" }

    New-Item -ItemType Directory -Path $FocusedBase -Force | Out-Null
    New-Item -ItemType Directory -Path $FullBase -Force | Out-Null

    & $Python -m pytest -q -rs "--basetemp=$FocusedBase" "--junitxml=$FocusedXml" `
        'tests/platform/test_windows_native_on_rig.py::test_prepared_python_runtime_rejects_stale_or_mismatched_files' `
        'tests/platform/test_windows_native_on_rig.py::test_managed_python_entry_preserves_identity_prefix_and_bootstrap' `
        2>&1 | Tee-Object -FilePath $FocusedLog
    $FocusedExit = $LASTEXITCODE
    if ($FocusedExit -ne 0) { throw "focused runtime proof failed with exit code $FocusedExit" }

    & $Python -m pytest tests -q -rs "--basetemp=$FullBase" "--junitxml=$FullXml" 2>&1 |
        Tee-Object -FilePath $FullLog
    $FullExit = $LASTEXITCODE
}
catch {
    $Failure = $_.Exception.Message
}
finally {
    try {
        $TempParent = Join-Path $Repository '.symlink-elevated-tmp'
        foreach ($Path in @($FocusedBase, $FullBase)) {
            $Removed = Remove-VerifiedTree $Path $TempParent
            $Cleanup.Add("workspace pytest temp $Path removed=$Removed")
        }
        if (Test-Path -LiteralPath $Scratch) {
            if ((Get-ChildItem -LiteralPath $Scratch -Force | Measure-Object).Count -ne 0) {
                throw "Refusing to remove nonempty owned scratch root: $Scratch"
            }
            Remove-Item -LiteralPath $Scratch -Force
            $Cleanup.Add("workspace scratch root $Scratch removed=True")
        }

        $DefaultRoot = 'C:\Users\ReiterU_PC\AppData\Local\Temp\pytest-of-ReiterU_PC'
        $AllowedTargets = @(
            [IO.Path]::GetFullPath((Join-Path $DefaultRoot 'pytest-17')),
            [IO.Path]::GetFullPath((Join-Path $DefaultRoot 'pytest-18'))
        )
        $CurrentLink = Get-Item -LiteralPath (Join-Path $DefaultRoot 'pytest-current') `
            -Force -ErrorAction SilentlyContinue
        if ($null -ne $CurrentLink -and
            ($CurrentLink.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            $TargetPath = [IO.Path]::GetFullPath(
                [IO.Path]::Combine($DefaultRoot, [string]$CurrentLink.Target)
            )
            if ($TargetPath -in $AllowedTargets) {
                Remove-Item -LiteralPath $CurrentLink.FullName -Force
                $Cleanup.Add("pytest-current link removed; exact target was $TargetPath")
            } else {
                $Cleanup.Add("pytest-current retained; target was $TargetPath")
            }
        } else {
            $Cleanup.Add('pytest-current absent or not a reparse point; retained')
        }
        foreach ($TargetPath in $AllowedTargets) {
            $Removed = Remove-VerifiedTree $TargetPath $DefaultRoot
            $Cleanup.Add("known pytest temp $TargetPath removed=$Removed")
        }
    }
    catch {
        $Cleanup.Add("cleanup error: $($_.Exception.Message)")
        if ($null -eq $Failure) { $Failure = "temporary cleanup failed: $($_.Exception.Message)" }
    }
    [ordered]@{
        administrator = $IsAdministrator
        prepare_command = $PrepareCommand
        prepare_exit_code = $PrepareExit
        verify_command = $VerifyCommand
        verify_exit_code = $VerifyExit
        focused_command = $FocusedCommand
        focused_exit_code = $FocusedExit
        full_command = $FullCommand
        full_exit_code = $FullExit
        failure = $Failure
        cleanup = @($Cleanup)
        completed_utc = [DateTime]::UtcNow.ToString('o')
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Completion -Encoding utf8
}
if ($null -ne $Failure) {
    Write-Error $Failure
    exit 1
}
if ($PrepareExit -ne 0 -or $VerifyExit -ne 0 -or $FocusedExit -ne 0 -or $FullExit -ne 0) {
    exit 1
}
exit 0
