$ErrorActionPreference = 'Stop'
$out = Join-Path $PSScriptRoot 'telemetry.jsonl'
$adapters = Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\DirectX' | ForEach-Object { Get-ItemProperty $_.PSPath } | Where-Object Description | Select-Object Description,AdapterLuid,VendorId,DeviceId
$adapters | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $PSScriptRoot 'adapter-map.json') -Encoding utf8
$paths = '\GPU Engine(*)\Utilization Percentage','\Processor(_Total)\% Processor Time'
Get-Counter $paths -SampleInterval 2 -MaxSamples 400 -ErrorAction Continue | ForEach-Object {
    $sample = $_
    $engines = @($sample.CounterSamples | Where-Object {$_.InstanceName -ne '_total'} | ForEach-Object { @{instance=$_.InstanceName;percent=$_.CookedValue;status=$_.Status} })
    $cpu = @($sample.CounterSamples | Where-Object InstanceName -eq '_total' | ForEach-Object CookedValue)
    $nv = @(nvidia-smi --query-gpu=timestamp,index,name,uuid,pci.bus_id,utilization.gpu,utilization.encoder,utilization.decoder,memory.used,power.draw,temperature.gpu --format=csv,noheader,nounits)
    $processes = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.ProcessName -in @('cephvr-python','ffmpeg','python')} | ForEach-Object { @{pid=$_.Id;name=$_.ProcessName;cpu_seconds=$_.CPU;working_set=$_.WorkingSet64} })
    @{utc=[DateTime]::UtcNow.ToString('o');counter_timestamp=$sample.Timestamp.ToUniversalTime().ToString('o');cpu_percent=$cpu;engines=$engines;nvidia_csv=$nv;processes=$processes} | ConvertTo-Json -Compress -Depth 6 | Add-Content $out -Encoding utf8
    if (Test-Path (Join-Path $PSScriptRoot 'stop-monitor')) { break }
}
