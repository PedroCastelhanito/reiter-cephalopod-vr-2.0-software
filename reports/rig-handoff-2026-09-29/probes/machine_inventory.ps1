$ErrorActionPreference='Stop'
$rigEvidence=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../evidence'))
$rigPnp=Get-PnpDevice -PresentOnly
$rigChains=@()
foreach($rigCamera in ($rigPnp | Where-Object FriendlyName -match 'Basler.*Camera')) {
  $rigChain=@(); $rigId=$rigCamera.InstanceId
  for($j=0;$j -lt 10 -and $rigId;$j++) {
    $rigDev=Get-PnpDevice -InstanceId $rigId -ErrorAction SilentlyContinue
    $rigChain += [pscustomobject]@{id=$rigId;name=$rigDev.FriendlyName;class=$rigDev.Class}
    $rigParent=Get-PnpDeviceProperty -InstanceId $rigId -KeyName DEVPKEY_Device_Parent -ErrorAction SilentlyContinue
    $rigId=$rigParent.Data
  }
  $rigChains += [pscustomobject]@{camera=$rigCamera.FriendlyName;chain=$rigChain}
}
$rigInventory=[ordered]@{
 captured_at=(Get-Date -Format o)
 os=Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture
 cpu=Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors
 board=Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product,Version
 memory=Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity,Speed,ConfiguredClockSpeed,Manufacturer,PartNumber
 disks=Get-PhysicalDisk | Select-Object FriendlyName,MediaType,BusType,Size,HealthStatus
 volumes=Get-Volume | Select-Object DriveLetter,FileSystem,Size,SizeRemaining
 gpu=Get-CimInstance Win32_PnPEntity | Where-Object PNPClass -eq 'Display' | Select-Object Name,PNPDeviceID,ConfigManagerErrorCode,Status
 devices=$rigPnp | Where-Object {$_.Class -in @('Monitor','Display','Ports','PylonUSB')} | Select-Object Class,FriendlyName,Status,InstanceId
 camera_usb_chains=$rigChains
 network=Get-NetAdapter | Select-Object Name,InterfaceDescription,Status,LinkSpeed,InterfaceGuid,ifIndex
 ethernet_ipv4=Get-NetIPAddress -AddressFamily IPv4 | Where-Object InterfaceAlias -match 'Ethernet' | Select-Object InterfaceAlias,IPAddress,PrefixLength
}
$rigInventory | ConvertTo-Json -Depth 9 | Set-Content -Encoding utf8 (Join-Path $rigEvidence 'machine.json')
$rigChains | ConvertTo-Json -Depth 6
& nvidia-smi --query-gpu=index,name,uuid,pci.bus_id,pci.device_id,driver_version,memory.total,compute_cap,pcie.link.gen.max,pcie.link.gen.current,pcie.link.width.max,pcie.link.width.current --format=csv | Set-Content -Encoding utf8 (Join-Path $rigEvidence 'nvidia-gpus.csv')
& powercfg /getactivescheme | Set-Content -Encoding utf8 (Join-Path $rigEvidence 'power-plan.txt')
