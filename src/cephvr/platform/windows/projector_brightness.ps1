param(
    [ValidateRange(101, 2500)]
    [UInt16]$Current
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Write-Step($message) {
    Write-Output ("[{0:HH:mm:ss}] {1}" -f (Get-Date), $message)
}

function Load-TiAssembly($root, $name) {
    $path = Join-Path $root $name
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing TI DLL: $path"
    }
    Add-Type -Path $path
}

if ([Environment]::Is64BitProcess) {
    throw "This TI/Cypress stack must be run from 32-bit PowerShell. Use the .bat launcher next to this script."
}

$guiRoot = Join-Path $env:APPDATA 'Texas Instruments\DLP EVM GUI 3.2.0.6'
if (-not (Test-Path -LiteralPath $guiRoot)) {
    throw "Could not find the TI DLP EVM GUI install folder: $guiRoot"
}

# Native DLLs such as cyusbserial.dll are resolved relative to the current directory.
Set-Location -LiteralPath $guiRoot
$env:PATH = "$guiRoot;$env:PATH"

Load-TiAssembly $guiRoot 'DLPComposer.IO.dll'
Load-TiAssembly $guiRoot 'DLPComposer.IO.Communications.dll'
Load-TiAssembly $guiRoot 'DLPComposer.Registers.dll'
Load-TiAssembly $guiRoot 'DLPComposer.Commands.DLPC347x.dll'

if ([DLPComposer.IO.RegisterBase]::CommunicationManager -eq $null) {
    [DLPComposer.IO.RegisterBase]::CommunicationManager =
        [DLPComposer.IO.Communications.DLPC347xCommunicationManager]::new()
}

Write-Step "Discovering DLP3010 EVM I2C interfaces. Close the TI GUI if this stalls."
$interfaces = [DLPComposer.IO.DLPC34xx.I2CCommandInterface]::GetAvailableInterfaces()
Write-Step ("Found {0} interface(s)." -f $interfaces.Count)

if ($interfaces.Count -le 0) {
    throw "No DLP I2C interfaces found. Check USB cables/power, and close the TI GUI before retrying."
}

$limit = $interfaces.Count
$successCount = 0
$cleanupFailed = $false
$results = [System.Collections.Generic.List[object]]::new()

for ($index = 0; $index -lt $limit; $index++) {
    $iface = $interfaces[$index]
    $entry = [ordered]@{ index=$index; name=[string]$iface.Name; id=[string]$iface.Id;
        readback_ma=$null; clamped=$null; confirmed=$false; release_confirmed=$false; error='' }
    Write-Step ("Interface {0}: {1} / {2}" -f $index, $iface.Name, $iface.Id)

    try {
        $iface.Timeout = 500
        $iface.SlaveAddress = 0x36
        $iface.RequestAccessViaGpio = $true

        if ($iface.RequestAccessViaGpio) {
            try {
                $iface.RequestAccess()
            } catch {
                Write-Warning ("Interface {0}: GPIO access request failed: {1}" -f $index, $_.Exception.Message)
            }
        }

        $iface.Connect()
        if (-not $iface.IsConnected) {
            $entry.error = 'connect returned false'
            Write-Warning ("Interface {0}: connect returned false; skipping." -f $index)
            continue
        }

        [DLPComposer.Commands.DLPC347x.Command]::CommInterface = $iface

        $summary = [DLPComposer.Commands.DLPC347x.Command]::WriteLedOutputControlMethod(
            [DLPComposer.Commands.DLPC347x.LedControlMethod]::Manual
        )
        if (-not $summary.Successful) {
            $entry.error = 'failed to set manual LED control'
            Write-Warning ("Interface {0}: failed to set manual LED control: {1}" -f $index, $summary)
            continue
        }

        $summary = [DLPComposer.Commands.DLPC347x.Command]::WriteRgbLedCurrent($Current, $Current, $Current)
        if (-not $summary.Successful) {
            $entry.error = 'failed to set LED current'
            Write-Warning ("Interface {0}: failed to set LED current: {1}" -f $index, $summary)
            continue
        }

        $summary = [DLPComposer.Commands.DLPC347x.Command]::WriteRgbLedEnable($true, $true, $true)
        if (-not $summary.Successful) {
            $entry.error = 'failed to enable LEDs'
            Write-Warning ("Interface {0}: failed to enable LEDs: {1}" -f $index, $summary)
            continue
        }

        [UInt16]$red = 0
        [UInt16]$green = 0
        [UInt16]$blue = 0
        $summary = [DLPComposer.Commands.DLPC347x.Command]::ReadRgbLedCurrent(
            [ref]$red,
            [ref]$green,
            [ref]$blue
        )

        if ($summary.Successful) {
            Write-Step ("Interface {0}: readback R={1} G={2} B={3}" -f $index, $red, $green, $blue)

            $entry.readback_ma = [ordered]@{ red=[int]$red; green=[int]$green; blue=[int]$blue }
            $exactMatch = ($red -eq $Current -and $green -eq $Current -and $blue -eq $Current)
            $clampedHighMatch = ($Current -gt 1023 -and $red -eq 1023 -and $green -eq 1023 -and $blue -eq 1023)

            if ($exactMatch -or $clampedHighMatch) {
                $successCount++
                $entry.confirmed = $true
                $entry.clamped = [bool]$clampedHighMatch
                if ($clampedHighMatch) {
                    Write-Step ("Interface {0}: requested {1}; EVM/API readback is clamped at 1023." -f $index, $Current)
                }
            } else {
                $entry.error = 'readback differs from requested current'
                Write-Warning ("Interface {0}: requested {1}, but read back R={2} G={3} B={4}." -f $index, $Current, $red, $green, $blue)
            }
        } else {
            $entry.error = 'readback failed'
            Write-Warning ("Interface {0}: readback failed: {1}" -f $index, $summary)
        }
    } catch {
        $entry.error = [string]$_.Exception.Message
        Write-Warning ("Interface {0}: {1}" -f $index, $_.Exception.Message)
    } finally {
        $entry.release_confirmed = $true
        try {
            if ($iface -ne $null -and $iface.IsConnected) {
                $iface.Disconnect()
            }
        } catch {
            $cleanupFailed = $true
            $entry.release_confirmed = $false
            $entry.error += '; release failed: ' + $_.Exception.Message
            Write-Warning ("Interface {0}: release failed: {1}" -f $index, $_.Exception.Message)
        }

        try {
            if ($iface -ne $null -and $iface.RequestAccessViaGpio) {
                $iface.RelinquishAccess()
            }
        } catch {
            $cleanupFailed = $true
            $entry.release_confirmed = $false
            $entry.error += '; release failed: ' + $_.Exception.Message
            Write-Warning ("Interface {0}: release failed: {1}" -f $index, $_.Exception.Message)
        }
        $results.Add($entry)
    }
}

$structured = [ordered]@{ schema_version=1; requested_ma=[int]$Current;
    discovered_interfaces=[int]$limit; interfaces=@($results.ToArray());
    success=($successCount -eq $limit -and -not $cleanupFailed) }
Write-Output ('CEPHVR_BRIGHTNESS_RESULT=' + ($structured | ConvertTo-Json -Depth 6 -Compress))
Write-Step ("Done. {0} interface(s) confirmed at {1} mA." -f $successCount, $Current)

if ($cleanupFailed) { throw "Projector interface release failed; close the TI GUI and verify USB state." }
if ($successCount -ne $limit) {
    throw "Only $successCount of $limit projector interfaces confirmed the requested current."
}
