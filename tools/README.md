# Developer commands

`generate_contracts.py` generates Python, type stubs and gRPC bindings from every
authoritative Protobuf source. `build_backend.py` invokes the same generator before
editable installations and wheel builds, then delegates packaging to setuptools.
These tools do not launch backend processes or change policy files.

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
