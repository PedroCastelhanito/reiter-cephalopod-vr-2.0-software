# Developer commands

`generate_contracts.py` generates Python, type stubs and gRPC bindings from every
authoritative Protobuf source. `build_backend.py` invokes the same generator before
editable installations and wheel builds, then delegates packaging to setuptools.
These tools do not launch backend processes or change policy files.

`python tools/build_pylon_wait.py` builds the Windows camera control-event bridge
using SWIG 4.3.0, MSVC and the installed pylon 11 development headers/libraries.
Use `--sdk <Development-directory>` for another SDK location. Rebuild with the
repository Python 3.11 environment after changing that environment. Its generated
Python proxy and AMD64 `.pyd` are installed in the camera package and included in
Windows wheels; source distributions retain the bridge inputs and builder. The
bridge uses the SDK's duplicating HANDLE constructor and SWIG's typed module
interface, because stock pypylon 26.3.1 cannot accept an integer Windows handle.
Missing builds fail camera preparation explicitly. Native wake/GIL and device
checks are required after building; the tool does not start capture or pulses.
The rig runner exposes the same build with `-BuildAcquisitionNative` after installing
the development dependencies; use it when preparing or rebuilding camera support.

`check_backend_boundaries.py` inspects controller, supervisor, acquisition and Visual Stimulus imports
and flags whole-runtime dependencies. Its file-size warnings require a cohesion review;
zero boundary errors alone do not establish maintainability or correct behavior.

`test_on_rig.ps1` prepares a Windows Python 3.11 environment and records static,
contract, behavioral and package results. Use the
[acquisition rig handoff](../reports/rig-verification.md) for dependency
installation, deferred hardware inputs and result interpretation. E15 permits the requested lightweight local implementation and authenticated loopback
checks; Windows-native and hardware acceptance remain rig work.

See the [development guide](../docs/development.md) for existing setup/check
commands, [ARCH-002](../architecture.md#arch-002) for repository boundaries and
the [contract index](../contracts/README.md#verification-status) for existing
contract compilation instructions.

The runner builds the required 64-bit Windows shared-ring atomic helper during
`-Install`. To rebuild it in an existing environment, pass `-BuildWindowsNative`;
the DLL is installed beside the Windows platform package and included in
Windows x64 wheels. Building a wheel with native DLLs requires a 64-bit Windows
build host and validates each DLL's PE machine type. A source-only build without
the generated DLL remains pure Python; shared-ring operations report the missing
native helper until `-BuildWindowsNative` produces it.

`-Install` also prepares `.venv/Scripts/cephvr-python.exe`, its matching runtime DLL
and a provenance manifest for exact managed-child identity. This leaves the ordinary
virtual-environment interpreter available for tooling. Managed launches verify the
prepared files against the current base runtime and `pyvenv.cfg`, then use the
versioned module entry to retain required DLL-directory handles. Refresh with
`-Install` after a base interpreter/configuration change; missing or stale preparation
fails before managed launch instead of falling back to the Windows redirector.

For a fresh AMD64 Windows rig with Python 3.11, MSVC/CMake, CUDA and NVIDIA Optical
Flow API 2 headers available, run
`./tools/test_on_rig.ps1 -Install -Rig -BuildTrackingNative -NvofSdkRoot <actual-header-root>`.
The Tracking build remains explicit; locate the installed headers on that machine.
This automated command does not replace device/scientific/full-workload acceptance.
