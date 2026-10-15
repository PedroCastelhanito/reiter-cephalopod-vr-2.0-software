param([switch]$Apply)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$taskRoot = (Resolve-Path -LiteralPath '.').Path
$taskExpected = 'C:\Dev\projects\reiter-cephalopod-vr\reiter-cephalopod-vr-2.0-software'
if ($taskRoot -ne $taskExpected) { throw 'Wrong workspace' }
$taskTmp = Join-Path $taskRoot '.tmp'
$taskReports = Join-Path $taskRoot 'reports'
$taskEvidence = Join-Path $taskReports 'runtime-evidence-2026-10-15\repo-cleanup'
$taskManifestPath = Join-Path $taskEvidence 'manifest.json'
if ($Apply -and (Test-Path -LiteralPath $taskManifestPath)) { throw 'Removal manifest already exists' }
if (@(git ls-files -- .tmp).Count) { throw 'Tracked files exist under .tmp' }
if ($LASTEXITCODE -ne 0) { throw 'Git inventory failed' }

function Assert-Path([string]$taskPath, [string]$taskBoundary) {
    $taskFull = [IO.Path]::GetFullPath($taskPath)
    if (-not $taskFull.StartsWith($taskBoundary + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Path outside allowed root: $taskFull" }
    $taskCursor = Get-Item -LiteralPath $taskFull -Force
    while ($null -ne $taskCursor) {
        if ($taskCursor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked path: $taskFull" }
        $taskCursor = if ($taskCursor -is [IO.DirectoryInfo]) { $taskCursor.Parent } else { $taskCursor.Directory }
    }
}

$taskRows = [Collections.Generic.List[object]]::new()
$taskSelected = @{}
function Add-Candidate([IO.FileInfo]$taskFile, [string]$taskReason, [string]$taskRetained = '') {
    Assert-Path $taskFile.FullName $taskTmp
    if ($taskSelected.ContainsKey($taskFile.FullName)) { return }
    $taskHash = (Get-FileHash -LiteralPath $taskFile.FullName -Algorithm SHA256).Hash
    if ($taskRetained) {
        Assert-Path $taskRetained $taskReports
        if ((Get-FileHash -LiteralPath $taskRetained -Algorithm SHA256).Hash -ne $taskHash) { throw 'Retained duplicate mismatch' }
    }
    $taskRows.Add([pscustomobject]@{path=$taskFile.FullName;bytes=$taskFile.Length;sha256=$taskHash;modified_utc=$taskFile.LastWriteTimeUtc.ToString('o');reason=$taskReason;retained_copy=$taskRetained;removed=$false})
    $taskSelected[$taskFile.FullName] = $true
}

# Only known, completed fixture trees, untouched for at least one hour.
$taskFixtureNames = @('astra-reader-review','no-tracking-owners','no-tracking-permitted','no-tracking-tests','rig-build-temp')
$taskPruneRoots = [Collections.Generic.List[string]]::new()
foreach ($taskName in $taskFixtureNames) {
    $taskPath = Join-Path $taskTmp $taskName
    if (-not (Test-Path -LiteralPath $taskPath)) { continue }
    Assert-Path $taskPath $taskTmp
    $taskItems = @(Get-ChildItem -LiteralPath $taskPath -Recurse -Force)
    if (@($taskItems | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Linked fixture descendant' }
    $taskFiles = @($taskItems | Where-Object { -not $_.PSIsContainer })
    if (@($taskFiles | Where-Object { $_.LastWriteTimeUtc -gt [DateTime]::UtcNow.AddHours(-1) }).Count) { throw 'Recently modified fixture; preserve it' }
    if ($taskName -ne 'rig-build-temp' -and @(Get-ChildItem -LiteralPath $taskPath -Force | Where-Object { $_.Name -notlike 'test_*' }).Count) { throw 'Unexpected fixture contents' }
    foreach ($taskFile in $taskFiles) { Add-Candidate $taskFile 'Completed regenerable test fixture' }
    $taskPruneRoots.Add($taskPath)
}

# Exact hash duplicates only: the retained reports tree is never a deletion target.
$taskReportFiles = @(Get-ChildItem -LiteralPath $taskReports -Recurse -File -Force | Where-Object { $_.Extension -in '.py','.ps1','.json','.jsonl','.txt','.log','.whl','.gz' -and $_.FullName -notlike "$taskEvidence\*" })
$taskBySize = @{}
foreach ($taskFile in $taskReportFiles) {
    $taskSizeKey = [string]$taskFile.Length
    if (-not $taskBySize.ContainsKey($taskSizeKey)) { $taskBySize[$taskSizeKey] = [Collections.Generic.List[object]]::new() }
    $taskBySize[$taskSizeKey].Add($taskFile)
}
$taskDuplicates = @(Get-ChildItem -LiteralPath $taskTmp -File -Force)
foreach ($taskName in 'rig-encoding-current','rig-packages') {
    $taskPath = Join-Path $taskTmp $taskName
    if (Test-Path -LiteralPath $taskPath) {
        Assert-Path $taskPath $taskTmp
        $taskItems = @(Get-ChildItem -LiteralPath $taskPath -Recurse -Force)
        if (@($taskItems | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Linked duplicate descendant' }
        $taskDuplicates += @($taskItems | Where-Object { -not $_.PSIsContainer })
        $taskPruneRoots.Add($taskPath)
    }
}
foreach ($taskFile in $taskDuplicates) {
    if ($taskSelected.ContainsKey($taskFile.FullName)) { continue }
    $taskSizeKey = [string]$taskFile.Length
    if (-not $taskBySize.ContainsKey($taskSizeKey)) { continue }
    $taskHash = (Get-FileHash -LiteralPath $taskFile.FullName -Algorithm SHA256).Hash
    foreach ($taskCopy in $taskBySize[$taskSizeKey]) {
        if ((Get-FileHash -LiteralPath $taskCopy.FullName -Algorithm SHA256).Hash -eq $taskHash) {
            Add-Candidate $taskFile 'Exact duplicate of retained dated evidence/package' $taskCopy.FullName
            break
        }
    }
}

# Finished one-shot documentation edits; final text/history is authoritative.
foreach ($taskName in @('check-reconciled-rig-todos.py','reconcile-completed-rig-todos.py','consolidate-resumed-acquisition.py','consolidate-rig-records.py','finish-paused-records.py','finish-rig-records.py','pause-open-loop-records.py','resume-open-loop-records.py','start-open-loop-records.py','reconcile-open-loop-progress.py','reconcile-rig-todo.py','record-rig-owner-deferral.py','update-rig-reports.py')) {
    $taskPath = Join-Path $taskTmp $taskName
    if (Test-Path -LiteralPath $taskPath) { Add-Candidate (Get-Item -LiteralPath $taskPath) 'Obsolete completed one-shot documentation editor; final documents and LOG retained' }
}

# Separate initial synthetic warm-up, not real camera media or the earlier 51-file cleanup.
$taskWarm = Join-Path $taskTmp 'rig-encoding-warmup'
Assert-Path $taskWarm $taskTmp
$taskInputs = Get-Content -LiteralPath (Join-Path $taskWarm 'inputs.json') -Raw | ConvertFrom-Json
if ($taskInputs.scope -ne 'synthetic lavfi encoder throughput, not capture/pipes or scientific fidelity') { throw 'Warm-up is not synthetic' }
$taskResults = @(Get-Content -LiteralPath (Join-Path $taskWarm 'summary.json') -Raw | ConvertFrom-Json)
if ($taskResults.Count -ne 3 -or @(Compare-Object @('behavioral','tracking','stimulus') @($taskResults.source)).Count) { throw 'Unexpected warm-up source set' }
foreach ($taskResult in $taskResults) {
    if ($taskResult.exit_code -ne 0 -or $taskResult.error -or $taskResult.frame_count_matches -ne $true -or $taskResult.video.ffprobe_exit -ne 0 -or $taskResult.video.decode_exit -ne 0 -or $taskResult.video.ffprobe_error -or $taskResult.video.decode_error) { throw 'Warm-up verification failed' }
    if ([long]$taskResult.video.ffprobe.streams[0].nb_read_frames -ne [long]$taskResult.requested_frames) { throw 'Warm-up count differs' }
    $taskCommand = @(Get-Content -LiteralPath (Join-Path $taskWarm "$($taskResult.source)-command.json") -Raw | ConvertFrom-Json)
    $taskInputIndex = [Array]::IndexOf($taskCommand,'-i')
    $taskFormatIndex = [Array]::IndexOf($taskCommand,'-f')
    $taskMedia = Get-Item -LiteralPath (Join-Path $taskWarm "$($taskResult.source).mp4")
    if (@($taskCommand | Where-Object { $_ -eq '-i' }).Count -ne 1 -or $taskInputIndex -lt 0 -or $taskFormatIndex -lt 0 -or $taskCommand[$taskFormatIndex+1] -ne 'lavfi' -or $taskCommand[$taskInputIndex+1] -notlike 'testsrc2=*' -or [IO.Path]::GetFullPath((Join-Path $taskRoot $taskCommand[-1])) -ne $taskMedia.FullName -or $taskMedia.Length -ne $taskResult.video.size_bytes) { throw 'Unrecognized warm-up media recipe/path/size' }
    Add-Candidate $taskMedia 'Passed regenerable 10-second lavfi warm-up; original command/count/decode metadata retained'
}
$taskWarmRetained = Join-Path $taskReports 'runtime-evidence-2026-10-15\projector-free-rig\encoding-initial-warmup'
$taskWarmMeta = @(Get-ChildItem -LiteralPath $taskWarm -File | Where-Object Extension -In '.json','.txt')
if ($taskWarmMeta.Count -ne 14 -or @(Get-ChildItem -LiteralPath $taskWarm -File).Count -ne 17) { throw 'Unexpected warm-up inventory' }
if ($Apply) {
    New-Item -ItemType Directory -Path $taskWarmRetained -Force | Out-Null
    Assert-Path $taskWarmRetained $taskReports
    foreach ($taskFile in $taskWarmMeta) {
        $taskDestination = Join-Path $taskWarmRetained $taskFile.Name
        if (-not (Test-Path -LiteralPath $taskDestination)) { Copy-Item -LiteralPath $taskFile.FullName -Destination $taskDestination }
        Add-Candidate $taskFile 'Warm-up metadata retained in dated evidence' $taskDestination
    }
}
$taskPruneRoots.Add($taskWarm)
$taskSummary = [pscustomobject]@{files=$taskRows.Count;bytes=($taskRows|Measure-Object bytes -Sum).Sum;categories=@($taskRows|Group-Object reason|Select-Object Name,Count);warmup_metadata_to_retain=$taskWarmMeta.Count;preserved='Source, config, .git, .venv, generated/native runtime components, FFmpeg toolchain, merge backup, real recordings/emergency reports, recent root caches and active placement artifacts'}
if (-not $Apply) {
    $taskSummary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskEvidence 'audit.json') -Encoding utf8
    $taskSummary | ConvertTo-Json -Depth 5
    return
}
$taskRecord = [pscustomobject]@{observed_utc=[DateTime]::UtcNow.ToString('o');workspace=$taskRoot;summary=$taskSummary;files=@($taskRows);empty_directories_removed=@();complete=$false}
$taskRecord | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $taskManifestPath -Encoding utf8
foreach ($taskRow in $taskRows) {
    Assert-Path $taskRow.path $taskTmp
    $taskCurrent = Get-Item -LiteralPath $taskRow.path -Force
    if ($taskCurrent.Length -ne $taskRow.bytes -or $taskCurrent.LastWriteTimeUtc.ToString('o') -ne $taskRow.modified_utc -or (Get-FileHash -LiteralPath $taskRow.path -Algorithm SHA256).Hash -ne $taskRow.sha256) { throw 'Deletion target changed; preserved' }
    if ($taskRow.retained_copy) {
        Assert-Path $taskRow.retained_copy $taskReports
        if ((Get-FileHash -LiteralPath $taskRow.retained_copy -Algorithm SHA256).Hash -ne $taskRow.sha256) { throw 'Retained copy changed; preserved' }
    }
    Remove-Item -LiteralPath $taskRow.path -Force
    $taskRow.removed = -not (Test-Path -LiteralPath $taskRow.path)
}
foreach ($taskTree in $taskPruneRoots) {
    $taskDirs = @(Get-ChildItem -LiteralPath $taskTree -Directory -Recurse -Force | Sort-Object { $_.FullName.Length } -Descending)
    $taskDirs += Get-Item -LiteralPath $taskTree
    foreach ($taskDir in $taskDirs) {
        Assert-Path $taskDir.FullName $taskTmp
        if (@(Get-ChildItem -LiteralPath $taskDir.FullName -Force).Count -eq 0) {
            Remove-Item -LiteralPath $taskDir.FullName -Force
            $taskRecord.empty_directories_removed += $taskDir.FullName
        }
    }
}
$taskRecord.complete = $true
$taskRecord | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $taskManifestPath -Encoding utf8
$taskSummary | ConvertTo-Json -Depth 5
