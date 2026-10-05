# SpikeGLX connection evidence — 2026-10-05

Source: rig checkout `fe1825fbe70625521fd77979ae19ee873fe57ba6` with
uncommitted changes. Official [SpikeGLX-CPP-SDK](https://github.com/billkarsh/SpikeGLX-CPP-SDK)
checkout `9169309e3f3cd0bfaa7c8dacc5b16288948bbfa3` was used in a disposable
workspace folder. The SDK DLL and Python wrapper were not installed into CephVR.

Method: `ipconfig` and `arp -a` identified rig interface `169.254.91.196` and
one peer `169.254.240.108` on that interface. A bounded Python TCP connection
from the rig to `169.254.240.108:4142` succeeded. The official SDK Python
wrapper then called only `connect`, `getVersion`, `isRunning`, `isSaving`,
`getRunName`, `getDataDir`, `close` and `destroyHandle` against that endpoint.
The second readback command exited zero and returned:

```text
connected=True
version=SpikeGLX v20251218 api v4.1.3
running=False
saving=False
run_name_error=sglx_getRunName: ERROR GETRUNNAME: Run parameters never validated.
data_dir=C:/SGL_DATA
```

Assessment: SDK readback confirms a live SpikeGLX command server and an idle,
not-saving acquisition at the observation time. `getRunName` could not supply
a run identity because the operator settings were not validated. The checked-in
[mapping reference](../../contracts/spikeglx_mapping_reference.json) names
SpikeGLX `v20260901`, so it does not match the installed `v20251218` build.
No `setRunName`, `startRun`, `stopRun` or other mutation was sent. The server
interface binding, firewall restriction, saved-channel inventory, writing gate,
stop confirmation and physical pulse capture remain unverified under E12/E15.

Follow-up: on 2026-10-05 the owner requested saving the observed command-server
endpoint. `config/backends/synchronization_config.toml` now records
`169.254.240.108:4142`. This does not validate the run settings or make the
unimplemented controller client available.

## Start/stop preflight after operator configuration

On 2026-10-05, the owner requested a start/stop attempt. A fresh official SDK
readback against the saved endpoint returned:

```text
version=SpikeGLX v20251218 api v4.1.3
initialized=True
running=False
saving=False
run_name=SP0001_20261004
data_dir=C:/SGL_DATA
params_count=70
gateMode=0
trigMode=0
manOvShowBut=true
manOvInitOff=true
snsRunName=SP0001_20261004
ni_streams=0
onebox_streams=1
onebox[0]_saved=14
imec_streams=0
```

The readback command exited zero. The acquisition settings are now validated,
and gate/trigger codes are both Immediate. However, the optional recording
button starts disabled, so `startRun` alone would not meet E12's writing gate.
No run mutation was sent. The owner was asked to change that operator setting
and use `Verify | Save` while leaving SpikeGLX idle.

Source review: official SpikeGLX tag `Release_v20251218-api4` at
`c936965dfb679c3d4ceec19956e633748c3cfea5` reports the installed version
in `Src-main/Version.h`. `Src-params/DAQ.h` and `DAQ.cpp` confirm the gate and
trigger code order and the five readback keys above; `CmdServer.cpp` implements
the queried commands. A focused diff against the checked-in mapping's source
revision `0cffa0b748a01f92e4418ed15ebdbfff7e9342c5` found no changes to
those keys or mode enumerations. This is a bounded source mapping review, not
full E12 mapping acceptance or runtime start/stop evidence.

## Bounded SDK start/stop smoke test

The operator then unchecked **Disable recording at run start** and used
`Verify | Save`. A fresh SDK preflight returned `manOvInitOff=false`,
`isRunning=false`, Immediate gate/trigger modes and the same OneBox stream
with 14 saved channels. A one-shot SDK script checked these values, set and
read back a unique test name, started once, checked `isSaving` and OneBox
sample progress, and sent `stopRun` only after rechecking the exact run name
and data directory. Its raw output was:

```text
version=SpikeGLX v20251218 api v4.1.3
preflight=idle,immediate,onebox_saved_14
test_run=CephVR_Test_20261005_163039
set_run_name_ms=0
start_run_ok=True
start_run_ms=360
initial_samples=0
saving=True
last_samples=4079
samples_advanced=True
stop_run_ok=True
stop_run_ms=0
stop_confirmed=False
RuntimeError: REMOTE STOP UNCONFIRMED; inspect SpikeGLX immediately
```

The script exited 1 because ten immediate `isRunning` polls over about two
seconds still returned true after `stopRun`. The agent immediately opened a
fresh SDK connection, which returned:

```text
running=False
saving=False
run_name=CephVR_Test_20261005_163039
data_dir=C:/SGL_DATA
```

Assessment: the exact test run eventually stopped, but confirmation took
longer than the script's two-second observation window; the precise stop
latency was not measured. The SDK returned success for `startRun` and
`stopRun`, and online saving/sample progress was observed. This is an SDK
control smoke test, not full E12 controller lifecycle acceptance. Native
file closure/content, the saved OneBox channel roles, pulse wiring,
interface/firewall restriction, and physical timing remain unverified.
The test run name remains selected in SpikeGLX and test data may exist under
`C:/SGL_DATA`; no remote files were removed.

## Controller-owned read-only diagnostic

Later on 2026-10-05, rig checkout `fe1825fbe70625521fd77979ae19ee873fe57ba6`
plus uncommitted edits used official SDK checkout
`9169309e3f3cd0bfaa7c8dacc5b16288948bbfa3` in ignored
`.local-spikeglx-sdk`, with its DLL beside `sglx.py`. The new controller
diagnostic called connect, version/state/name/directory reads and close using the
saved `169.254.240.108:4142` endpoint. It exited zero and returned:

```text
connected: true
address: "169.254.240.108"
port: 4142
version: "SpikeGLX v20251218 api v4.1.3"
run_name: "CephVR_Test_20261005_163039"
data_directory: "C:/SGL_DATA"
```

The absent false Proto3 Boolean fields mean `running=false` and `saving=false`.
No remote mutation occurred. Three focused GUI SpikeGLX tests and six
authenticated loopback/timeout tests passed. A first managed launch exited
during Windows job inspection (`QueryFullProcessImageNameW`, WinError 5); a
subsequent launch after concurrent startup fixes showed a connected live
Dashboard, but it exited before the button could be clicked. The agent's
computer-use tool read the window but could not click it. A further launch
ended with `JOB_INSPECTION_FAILED` in its emergency report; the launcher
receipt showed both child channels closed. The exact GUI button response
remains unverified. This readback does not validate saved
channels, pulse wiring or E12 Setup.
