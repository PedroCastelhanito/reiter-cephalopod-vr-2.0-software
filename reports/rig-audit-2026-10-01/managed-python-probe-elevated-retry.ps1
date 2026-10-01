$ErrorActionPreference = 'Stop'

$Repository = 'C:\Dev\projects\reiter-cephalopod-vr\reiter-cephalopod-vr-2.0-software'
$Python = Join-Path $Repository '.venv\Scripts\python.exe'
$Evidence = Join-Path $Repository 'reports\rig-audit-2026-10-01'
$TokenLog = Join-Path $Evidence 'symlink-elevated-retry-token.log'
$TestLog = Join-Path $Evidence 'symlink-elevated-retry-managed-python.log'
$TestXml = Join-Path $Evidence 'symlink-elevated-retry-managed-python.xml'
$Completion = Join-Path $Evidence 'symlink-elevated-retry-completion.json'
$ExitCode = $null
$Failure = $null
$Command = "$Python -m pytest -q -rs --junitxml=$TestXml tests/platform/test_windows_native_on_rig.py::test_managed_python_entry_preserves_identity_prefix_and_bootstrap"

Set-Location -LiteralPath $Repository
try {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
    $IsAdministrator = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $IsAdministrator) {
        throw 'This focused retry requires an elevated administrator token.'
    }
    & whoami.exe /all 2>&1 | Set-Content -LiteralPath $TokenLog -Encoding utf8
    if ($LASTEXITCODE -ne 0) {
        throw "whoami /all failed with exit code $LASTEXITCODE"
    }
    & $Python -m pytest -q -rs "--junitxml=$TestXml" `
        'tests/platform/test_windows_native_on_rig.py::test_managed_python_entry_preserves_identity_prefix_and_bootstrap' `
        2>&1 | Tee-Object -FilePath $TestLog
    $ExitCode = $LASTEXITCODE
}
catch {
    $Failure = $_.Exception.Message
}
finally {
    [ordered]@{
        administrator = $IsAdministrator
        command = $Command
        exit_code = $ExitCode
        failure = $Failure
        completed_utc = [DateTime]::UtcNow.ToString('o')
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Completion -Encoding utf8
}
if ($null -ne $Failure) {
    Write-Error $Failure
    exit 1
}
if ($ExitCode -ne 0) { exit 1 }
exit 0
