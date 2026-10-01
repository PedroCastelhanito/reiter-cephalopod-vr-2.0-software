"""Installed backend provider discovery without fabricated readiness."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import cast

from google.protobuf.message import Message

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.configuration import (
    BackendValidator,
)
from cephvr.controller.planning import (
    WriterSchema,
    WriterSchemaKey,
    build_schema,
)
from cephvr.controller.ports import BACKEND_NAMES, SpikeGLXPort


def _import_optional(module_name: str) -> ModuleType | None:
    """Import a module; None only when that exact module is absent."""
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            return None
        raise


def _installed_validators() -> dict[str, BackendValidator]:
    providers: dict[str, BackendValidator] = {}
    for name in ("acquisition", "visual_stimulus", "tracking", "synchronization"):
        module_name = f"cephvr.{name}.configuration"
        module = _import_optional(module_name)
        if module is None:
            continue
        validator = getattr(module, "validate_configuration", None)
        if not callable(validator):
            raise RuntimeError(f"{module_name} has no pure validate_configuration")
        providers[name] = validator
    return providers


def _installed_file_policies(
    software_root: Path, active_names: frozenset[str]
) -> dict[str, Message]:
    policies: dict[str, Message] = {}
    for name in ("acquisition", "visual_stimulus", "tracking"):
        if name not in active_names:
            continue
        module_name = f"cephvr.{name}.configuration"
        module = _import_optional(module_name)
        if module is None:
            continue
        loader = getattr(module, "load_file_policies", None)
        if loader is None:
            continue
        policy = loader(software_root)
        if not isinstance(policy, Message):
            raise RuntimeError(
                f"{module_name}.load_file_policies returned no Protobuf policy"
            )
        policies[name] = policy
    return policies


def _writer_schema(prepared: pb.PreparedSession) -> dict[str, object]:
    """Load only owning writers' pure schema definitions for enabled outputs."""
    definitions: dict[WriterSchemaKey, WriterSchema] = {}
    for name in sorted({output.backend.backend_name for output in prepared.outputs}):
        if name not in BACKEND_NAMES:
            raise RuntimeError("prepared output has an unsupported writer owner")
        module_name = f"cephvr.{name}.recording_schema"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name:
                raise
            raise RuntimeError(
                f"writer definitions unavailable: {module_name}"
            ) from exc
        provider = getattr(module, "get_writer_schemas", None)
        if not callable(provider):
            raise RuntimeError(f"{module_name} has no pure get_writer_schemas provider")
        supplied = provider()
        if not isinstance(supplied, Mapping):
            raise RuntimeError("writer schema provider must return a mapping")
        for key, value in supplied.items():
            if (
                not isinstance(key, tuple)
                or len(key) != 3
                or any(not isinstance(part, str) for part in key)
                or key[0] != name
                or not isinstance(value, WriterSchema)
            ):
                raise RuntimeError(
                    "writer schema provider returned foreign or invalid definitions"
                )
            definitions[cast(WriterSchemaKey, key)] = value
    return build_schema(prepared, definitions)


def _installed_spikeglx(software_root: Path, generation: str) -> SpikeGLXPort | None:
    """Bind the later synchronization stage's controller-owned remote client."""
    module_name = "cephvr.synchronization.client"
    module = _import_optional(module_name)
    if module is None:
        return None
    factory = getattr(module, "create_controller_client", None)
    if not callable(factory):
        raise RuntimeError("synchronization client factory unavailable")
    client = factory(software_root=software_root, controller_generation=generation)
    if any(
        not callable(getattr(client, method, None))
        for method in (
            "prepare",
            "verify_before_start",
            "start_and_verify_writing",
            "stop_expected_run",
        )
    ):
        raise RuntimeError(
            "synchronization client does not implement the controller port"
        )
    return cast(SpikeGLXPort, client)


def _installed_display_validator() -> Callable[[str], frozenset[str]] | None:
    module_name = "cephvr.visual_stimulus.configuration"
    module = _import_optional(module_name)
    if module is None:
        return None
    provider = getattr(module, "validate_display_profile", None)
    if not callable(provider):
        raise RuntimeError(
            "Visual Stimulus configuration module has no pure display validator"
        )

    def validate(profile_json: str) -> frozenset[str]:
        outputs = provider(profile_json)
        if (
            not isinstance(outputs, frozenset)
            or not outputs
            or any(not isinstance(value, str) or not value for value in outputs)
        ):
            raise ValueError(
                "Visual Stimulus display validator returned no exact output set"
            )
        return outputs

    return validate
