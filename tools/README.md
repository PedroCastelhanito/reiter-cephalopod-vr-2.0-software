# Developer commands

`generate_contracts.py` generates Python, type stubs and gRPC bindings from every
authoritative Protobuf source. `build_backend.py` invokes the same generator before
editable installations and wheel builds, then delegates packaging to setuptools.
These tools do not launch backend processes or change policy files.

See the [development guide](../docs/development.md) for existing setup/check
commands, [ARCH-002](../architecture.md#arch-002) for repository boundaries and
the [contract index](../contracts/README.md#verification-status) for existing
contract compilation instructions.
