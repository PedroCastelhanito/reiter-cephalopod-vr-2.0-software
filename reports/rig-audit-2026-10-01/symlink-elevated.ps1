$ErrorActionPreference = 'Stop'

$Repository = 'C:\Dev\projects\reiter-cephalopod-vr\reiter-cephalopod-vr-2.0-software'
$Python = Join-Path $Repository '.venv\Scripts\python.exe'
$Evidence = Join-Path $Repository 'reports\rig-audit-2026-10-01'
$TokenLog = Join-Path $Evidence 'symlink-elevated-token.log'
$FocusedLog = Join-Path $Evidence 'symlink-elevated-focused.log'
$FocusedXml = Join-Path $Evidence 'symlink-elevated-focused.xml'
$FullLog = Join-Path $Evidence 'symlink-elevated-full.log'
$FullXml = Join-Path $Evidence 'symlink-elevated-full.xml'
$Completion = Join-Path $Evidence 'symlink-elevated-completion.json'
$FocusedExit = $null
$FullExit = $null
$Failure = $null
$FocusedCommand = "$Python -m pytest -q -rs --junitxml=$FocusedXml tests/controller/test_configuration_transactions.py::test_setup_rejects_unset_or_invalid_recording_root[symlink] tests/controller/test_storage.py::test_existing_lock_symlink_is_never_followed tests/platform/test_windows_native_on_rig.py::test_reparse_lock_target_is_rejected_when_symlinks_are_available tests/shared/test_recovery.py::test_unverified_exit_and_unsafe_pointer_cannot_authorize_recovery"
$FullCommand = "$Python -m pytest tests -q -rs --junitxml=$FullXml"

Set-Location -LiteralPath $Repository
try {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
    $IsAdministrator = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $IsAdministrator) {
        throw 'This evidence run requires an elevated administrator token.'
    }

    & whoami.exe /all 2>&1 | Set-Content -LiteralPath $TokenLog -Encoding utf8
    if ($LASTEXITCODE -ne 0) {
        throw "whoami /all failed with exit code $LASTEXITCODE"
    }

    & $Python -m pytest -q -rs "--junitxml=$FocusedXml" `
        'tests/controller/test_configuration_transactions.py::test_setup_rejects_unset_or_invalid_recording_root[symlink]' `
        'tests/controller/test_storage.py::test_existing_lock_symlink_is_never_followed' `
        'tests/platform/test_windows_native_on_rig.py::test_reparse_lock_target_is_rejected_when_symlinks_are_available' `
        'tests/shared/test_recovery.py::test_unverified_exit_and_unsafe_pointer_cannot_authorize_recovery' `
        2>&1 | Tee-Object -FilePath $FocusedLog
    $FocusedExit = $LASTEXITCODE

    & $Python -m pytest tests -q -rs "--junitxml=$FullXml" 2>&1 |
        Tee-Object -FilePath $FullLog
    $FullExit = $LASTEXITCODE
}
catch {
    $Failure = $_.Exception.Message
}
finally {
    $Record = [ordered]@{
        administrator = $IsAdministrator
        focused_command = $FocusedCommand
        focused_exit_code = $FocusedExit
        full_command = $FullCommand
        full_exit_code = $FullExit
        failure = $Failure
        completed_utc = [DateTime]::UtcNow.ToString('o')
    }
    $Record | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Completion -Encoding utf8
}

if ($null -ne $Failure) {
    Write-Error $Failure
    exit 1
}
if ($FocusedExit -ne 0 -or $FullExit -ne 0) {
    exit 1
}
exit 0
