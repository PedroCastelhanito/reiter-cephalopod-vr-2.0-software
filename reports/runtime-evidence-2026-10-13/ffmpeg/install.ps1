$ErrorActionPreference = 'Stop'
$taskRepo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$taskCandidate = Join-Path $taskRepo '.tmp/ffmpeg-toolchain/extracted/ffmpeg-9.0.2-essentials_build'
$taskInstalled = 'C:\Dev\software\ffmpeg-9.0.2-essentials_build'
$taskActive = 'C:\Dev\software\ffmpeg-4.3.2-2021\bin'
$taskBackup = 'C:\Dev\software\ffmpeg-backup-20261013'
$taskAudit = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'audit.json') -Raw | ConvertFrom-Json
if (Get-Process ffmpeg,ffprobe -ErrorAction SilentlyContinue) { throw 'An FFmpeg tool is active; do not replace its executable.' }
if ((Get-Command ffmpeg).Source -ine (Join-Path $taskActive 'ffmpeg.exe')) { throw 'Active FFmpeg path changed since inspection.' }
if (Test-Path -LiteralPath $taskBackup) { throw 'Backup path already exists; preserve it.' }
if (Test-Path -LiteralPath $taskInstalled) { throw 'Install path already exists; preserve it.' }
$taskRecord = [ordered]@{ method='Explicit owner-authorized matched pair upgrade at existing PATH location; no environment/recording-settings change'; backup=$taskBackup; package=$taskInstalled; active_bin=$taskActive; files=@() }
foreach ($taskName in @('ffmpeg','ffprobe')) {
    $taskSource = Join-Path $taskCandidate ('bin\' + $taskName + '.exe')
    $taskExpected = $taskAudit.tools.$taskName.sha256
    if ((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) { throw 'Candidate changed since validation.' }
    $taskOriginal = Join-Path $taskActive ($taskName + '.exe')
    $taskRecord.files += [ordered]@{ name=$taskName; path=$taskOriginal; before_sha256=(Get-FileHash -LiteralPath $taskOriginal -Algorithm SHA256).Hash.ToLowerInvariant(); after_sha256=$taskExpected }
}
New-Item -ItemType Directory -Path $taskBackup | Out-Null
foreach ($taskName in @('ffmpeg','ffprobe')) { Copy-Item -LiteralPath (Join-Path $taskActive ($taskName + '.exe')) -Destination $taskBackup }
Copy-Item -LiteralPath $taskCandidate -Destination $taskInstalled -Recurse
try {
    foreach ($taskName in @('ffmpeg','ffprobe')) {
        Copy-Item -LiteralPath (Join-Path $taskInstalled ('bin\' + $taskName + '.exe')) -Destination (Join-Path $taskActive ($taskName + '.exe')) -Force
    }
    foreach ($taskFile in $taskRecord.files) {
        if ((Get-FileHash -LiteralPath $taskFile.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskFile.after_sha256) { throw 'Installed pair verification failed.' }
    }
} catch {
    foreach ($taskName in @('ffmpeg','ffprobe')) { Copy-Item -LiteralPath (Join-Path $taskBackup ($taskName + '.exe')) -Destination (Join-Path $taskActive ($taskName + '.exe')) -Force }
    throw
}
$taskRecord | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'install.json') -Encoding utf8
foreach ($taskName in @('ffmpeg','ffprobe')) { & (Join-Path $taskActive ($taskName + '.exe')) -version | Select-Object -First 1 }
