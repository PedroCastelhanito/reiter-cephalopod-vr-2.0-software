"""Statically check ARCH-002 backend dependency boundaries without running code.

Only assembly and RPC adapters may import a runtime coordinator. Feature modules
must depend on records and explicit operations. Size warnings require review;
they are not automatic evidence that a cohesive module should be split.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
ASSEMBLY = {
    "cephvr.tracking.main",
    "cephvr.tracking.transport.services",
    "cephvr.tracking.transport.server",
    "cephvr.visual_stimulus.main",
    "cephvr.visual_stimulus.worker.main",
    "cephvr.visual_stimulus.worker.runtime",
    "cephvr.visual_stimulus.transport.services",
    "cephvr.visual_stimulus.transport.server",
    "cephvr.controller.runtime",
    "cephvr.controller.service",
    "cephvr.controller.main",
    "cephvr.controller.startup.application",
    "cephvr.supervisor.runtime",
    "cephvr.supervisor.service",
    "cephvr.supervisor.main",
    "cephvr.supervisor.startup",
    "cephvr.acquisition.main",
    "cephvr.acquisition.worker.main",
    "cephvr.acquisition.worker.server",
    "cephvr.acquisition.worker.runtime",
    "cephvr.acquisition.transport.services",
    "cephvr.acquisition.transport.server",
}
ENTRY_MODULES = {
    f"cephvr.{backend}.{module}"
    for backend in (
        "controller",
        "supervisor",
        "acquisition",
        "visual_stimulus",
        "tracking",
    )
    for module in ("runtime", "service", "main")
} | {
    "cephvr.visual_stimulus.worker.main",
    "cephvr.visual_stimulus.worker.runtime",
    "cephvr.visual_stimulus.transport.services",
    "cephvr.acquisition.worker.main",
    "cephvr.acquisition.worker.runtime",
    "cephvr.acquisition.worker.server",
    "cephvr.acquisition.worker.service",
    "cephvr.acquisition.transport.services",
}


def inspect_module(path: Path) -> tuple[list[str], list[str]]:
    path_parts = path.relative_to(SOURCE).with_suffix("").parts
    is_package = path.name == "__init__.py"
    module_parts = path_parts[:-1] if is_package else path_parts
    module = ".".join(module_parts)
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    errors: list[str] = []
    warnings: list[str] = []
    for node in ast.walk(tree):
        dependencies: list[str] = []
        if isinstance(node, ast.Import):
            dependencies = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package_parts = list(module_parts if is_package else module_parts[:-1])
                parent = package_parts[: len(package_parts) - node.level + 1]
                base = ".".join(parent + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            dependencies = [base, *(f"{base}.{a.name}" for a in node.names)]
        if module not in ASSEMBLY and any(d in ENTRY_MODULES for d in dependencies):
            errors.append(
                f"{path.relative_to(ROOT)}:{node.lineno}: feature imports entry/coordination module"
            )
        if (
            module not in ASSEMBLY
            and isinstance(node, ast.Attribute)
            and node.attr in {"runtime", "_runtime"}
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        ):
            errors.append(
                f"{path.relative_to(ROOT)}:{node.lineno}: whole-runtime back-reference"
            )
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            if ast.unparse(node.value) in {"runtime", "self.runtime", "self._runtime"}:
                errors.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}: private runtime access"
                )
    line_count = len(text.splitlines())
    if line_count > 500:
        warnings.append(
            f"{path.relative_to(ROOT)}: {line_count} lines; review cohesion"
        )
    return errors, warnings


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    paths = [
        path
        for backend in (
            "controller",
            "supervisor",
            "acquisition",
            "visual_stimulus",
            "tracking",
        )
        for path in (SOURCE / "cephvr" / backend).rglob("*.py")
        if not path.name.endswith(("_pb2.py", "_pb2_grpc.py"))
    ]
    for path in sorted(paths):
        module_errors, module_warnings = inspect_module(path)
        errors.extend(module_errors)
        warnings.extend(module_warnings)
    for warning in warnings:
        print(f"REVIEW {warning}")
    for error in errors:
        print(f"ERROR {error}")
    print(f"Checked {len(paths)} backend modules; {len(errors)} boundary violations.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
