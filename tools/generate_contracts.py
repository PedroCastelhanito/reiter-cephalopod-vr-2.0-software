"""Generate Python bindings from the authoritative versioned Protobuf sources."""

from __future__ import annotations

import argparse
from pathlib import Path

from grpc_tools import protoc


def generate(output: Path | None = None) -> int:
    """Generate all bindings for both local development and package builds."""
    root = Path(__file__).resolve().parents[1]
    contracts = root / "contracts"
    sources = sorted(contracts.glob("cephvr/**/*.proto"))
    if not sources:
        raise RuntimeError("Authoritative Protobuf sources are missing.")
    output = (output or root / "src").resolve()
    output.mkdir(parents=True, exist_ok=True)
    arguments = [
        "grpc_tools.protoc",
        f"-I{contracts}",
        f"--python_out={output}",
        f"--pyi_out={output}",
        f"--grpc_python_out={output}",
        *(str(path) for path in sources),
    ]
    result = protoc.main(arguments)
    if result:
        return result
    for source in sources:
        directory = output / source.relative_to(contracts).parent
        while directory != output:
            initializer = directory / "__init__.py"
            if not initializer.exists():
                initializer.write_text(
                    '"""Namespace for generated CephVR contract bindings."""\n',
                    encoding="utf-8",
                )
            directory = directory.parent
    print(f"Generated {len(sources)} Protobuf sources into {output}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return generate(parser.parse_args().output)


if __name__ == "__main__":
    raise SystemExit(main())
