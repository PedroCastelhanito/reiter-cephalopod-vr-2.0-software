"""Installed backend provider discovery without fabricated readiness."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import cast

from google.protobuf.message import Message

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.planning import (
    WriterSchema,
    WriterSchemaKey,
    build_schema,
)
from cephvr.controller.ports import BACKEND_NAMES, SpikeGLXPort
from cephvr.controller.validator_gate import BackendValidator
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.v1 import runtime_pb2 as visual_stimulus_pb


@dataclass(frozen=True)
class _VisualStimulusValidator:
    """Validate against the exact typed file policy held by the caller."""

    software_root: Path
    pure_validator: Callable[[pb.ExperimentConfiguration], pb.ValidationResult]
    policy_loader: Callable[[Path], Message]
    profile_resolver: Callable[..., DisplayProfile]

    def __call__(self, candidate: pb.ExperimentConfiguration) -> pb.ValidationResult:
        try:
            policy = self.policy_loader(self.software_root)
        except Exception as exc:
            return self._unavailable("FILE_POLICY_UNAVAILABLE", str(exc))
        return self.validate_with_file_policy(candidate, policy)

    def validate_with_file_policy(
        self, candidate: pb.ExperimentConfiguration, policy: Message | None
    ) -> pb.ValidationResult:
        backend = next(
            (
                item
                for item in candidate.backends
                if item.backend_name == "visual_stimulus" and item.enabled
            ),
            None,
        )
        if (
            backend is None
            or backend.WhichOneof("settings") != "visual_stimulus"
            or not backend.visual_stimulus.HasField("display")
        ):
            return self.pure_validator(candidate)
        if policy is None or policy.DESCRIPTOR.full_name != (
            "cephvr.visual_stimulus.v1.VisualStimulusFilePolicies"
        ):
            return self._unavailable(
                "FILE_POLICY_UNAVAILABLE", "Visual Stimulus file policy unavailable"
            )
        typed_policy = cast(visual_stimulus_pb.VisualStimulusFilePolicies, policy)
        try:
            resolved_candidate = pb.ExperimentConfiguration.FromString(
                candidate.SerializeToString()
            )
            resolved_backend = next(
                item
                for item in resolved_candidate.backends
                if item.backend_name == "visual_stimulus" and item.enabled
            )
            settings = resolved_backend.visual_stimulus
            display = self.profile_resolver(
                settings.display.profile_json,
                max_bytes=typed_policy.limits.max_document_bytes,
                refresh_hz=(
                    typed_policy.pacing_refresh_hz
                    if typed_policy.HasField("pacing_refresh_hz")
                    else None
                ),
                output_id=(
                    typed_policy.pacing_output_id
                    if typed_policy.HasField("pacing_output_id")
                    else None
                ),
            )
            settings.display.profile_json = display.model_dump_json()
            return self.pure_validator(resolved_candidate)
        except (ValueError, TypeError, AttributeError) as exc:
            return self._invalid(str(exc))

    @staticmethod
    def _unavailable(code: str, message: str) -> pb.ValidationResult:
        return pb.ValidationResult(
            completed=False,
            valid=False,
            component="visual_stimulus",
            configuration_module_version="visual-stimulus-v20-policy-overlay",
            unavailable_reason=pb.Failure(code=code, message=message),
        )

    @staticmethod
    def _invalid(message: str) -> pb.ValidationResult:
        result = pb.ValidationResult(
            completed=True,
            valid=False,
            component="visual_stimulus",
            configuration_module_version="visual-stimulus-v20-policy-overlay",
        )
        issue = result.issues.add(
            component="visual_stimulus",
            field_path="backends.visual_stimulus.display.profile_json",
        )
        issue.failure.code = "INVALID_DISPLAY_PROFILE"
        issue.failure.message = message
        return result


def _import_optional(module_name: str) -> ModuleType | None:
    """Import a module; None only when that exact module is absent."""
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            return None
        raise


def _installed_validators(software_root: Path) -> dict[str, BackendValidator]:
    providers: dict[str, BackendValidator] = {}
    for name in ("acquisition", "visual_stimulus", "tracking", "synchronization"):
        module_name = f"cephvr.{name}.configuration"
        module = _import_optional(module_name)
        if module is None:
            continue
        validator = getattr(module, "validate_configuration", None)
        if not callable(validator):
            raise RuntimeError(f"{module_name} has no pure validate_configuration")
        if name == "visual_stimulus":
            policy_loader = getattr(module, "load_file_policies", None)
            profile_resolver = getattr(module, "resolve_pacing_profile", None)
            if not callable(policy_loader) or not callable(profile_resolver):
                raise RuntimeError(
                    f"{module_name} has no V20 file-pacing validation binding"
                )

            providers[name] = _VisualStimulusValidator(
                software_root,
                validator,
                policy_loader,
                profile_resolver,
            )
        else:
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


def _installed_display_pacing_resolver() -> Callable[[str, Message], str] | None:
    """Bind startup Idle to the same file policy later carried into the worker."""
    module = _import_optional("cephvr.visual_stimulus.configuration")
    if module is None:
        return None
    provider = getattr(module, "resolve_pacing_profile", None)
    if not callable(provider):
        raise RuntimeError("Visual Stimulus pacing profile resolver unavailable")

    def resolve(profile_json: str, policy: Message) -> str:
        if policy.DESCRIPTOR.full_name != (
            "cephvr.visual_stimulus.v1.VisualStimulusFilePolicies"
        ):
            raise ValueError("Visual Stimulus file policies unavailable")
        typed_policy = cast(visual_stimulus_pb.VisualStimulusFilePolicies, policy)
        output = provider(
            profile_json,
            max_bytes=typed_policy.limits.max_document_bytes,
            refresh_hz=(
                typed_policy.pacing_refresh_hz
                if typed_policy.HasField("pacing_refresh_hz")
                else None
            ),
            output_id=(
                typed_policy.pacing_output_id
                if typed_policy.HasField("pacing_output_id")
                else None
            ),
        )
        return cast(str, output.model_dump_json())

    return resolve
