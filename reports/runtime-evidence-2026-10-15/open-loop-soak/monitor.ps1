param([Parameter(Mandatory=$true)][string]$Output, [Parameter(Mandatory=$true)][string]$StopFile)
$ErrorActionPreference = 'Stop'
$writer = [System.IO.StreamWriter]::new($Output, $false, [System.Text.UTF8Encoding]::new($false))
$watch = [System.Diagnostics.Stopwatch]::StartNew()
try {
  while (-not (Test-Path -LiteralPath $StopFile)) {
    $begin = $watch.ElapsedMilliseconds
    $row = @{utc=[DateTime]::UtcNow.ToString('o'); elapsed_ms=$begin; source='1s read-only Win32 performance counters; CPU process percent may exceed100 across cores'}
    try {
      $row.processes = @(Get-CimInstance Win32_Process | Where-Object {$_.Name -match 'python|cephvr|ffmpeg'} | Select-Object ProcessId,ParentProcessId,Name,CreationDate,ExecutablePath,CommandLine,WorkingSetSize,KernelModeTime,UserModeTime,ReadTransferCount,WriteTransferCount)
      $row.cpu = @(Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'" | Select-Object Name,PercentProcessorTime)
      $row.disk = @(Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk | Select-Object Name,DiskReadBytesPersec,DiskWriteBytesPersec,CurrentDiskQueueLength,PercentDiskTime)
      $row.space = @(Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'" | Select-Object DeviceID,FreeSpace,Size)
      $row.gpu = @(& nvidia-smi --query-gpu=timestamp,index,uuid,name,utilization.gpu,utilization.encoder,memory.used,power.draw --format=csv,noheader,nounits)
      if ($LASTEXITCODE -ne 0) {$row.gpu_error = $LASTEXITCODE}
    } catch {$row.error = $_.Exception.Message}
    $row.sample_duration_ms = $watch.ElapsedMilliseconds - $begin
    $writer.WriteLine(($row | ConvertTo-Json -Depth 5 -Compress)); $writer.Flush()
    $remaining = 1000 - ($watch.ElapsedMilliseconds - $begin)
    if ($remaining -gt 0) {Start-Sleep -Milliseconds $remaining}
  }
} finally {$writer.Dispose()}
