"""Preserve installed-provider identity and file-policy validation through gates."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast

from google.protobuf.message import Message

from cephvr.control.v1 import types_pb2 as pb

BackendValidator = Callable[[pb.ExperimentConfiguration], pb.ValidationResult]
_BACKENDS = frozenset({"acquisition", "visual_stimulus", "tracking", "synchronization"})


@dataclass(frozen=True)
class ControllerBackendValidator:
    """Apply active-backend gating while retaining the held file policy."""

    name: str
    provider: BackendValidator | None

    def __call__(self, candidate: pb.ExperimentConfiguration) -> pb.ValidationResult:
        return self._validate(candidate, None, use_file_policy=False)

    def validate_with_file_policy(
        self, candidate: pb.ExperimentConfiguration, policy: Message | None
    ) -> pb.ValidationResult:
        return self._validate(candidate, policy, use_file_policy=True)

    def _validate(
        self,
        candidate: pb.ExperimentConfiguration,
        policy: Message | None,
        *,
        use_file_policy: bool,
    ) -> pb.ValidationResult:
        enabled = any(
            item.backend_name == self.name and item.enabled
            for item in candidate.backends
        )
        if not enabled:
            return pb.ValidationResult(
                completed=True,
                valid=True,
                component=self.name,
                configuration_module_version="inactive",
            )
        provider = self.provider
        if provider is None:
            return pb.ValidationResult(
                completed=False,
                valid=False,
                component=self.name,
                unavailable_reason=pb.Failure(
                    code="VALIDATOR_UNAVAILABLE",
                    message=f"{self.name} configuration validator is not installed",
                ),
            )
        policy_validator = getattr(provider, "validate_with_file_policy", None)
        result = (
            policy_validator(candidate, policy)
            if use_file_policy and callable(policy_validator)
            else provider(candidate)
        )
        if result.component != self.name or not result.configuration_module_version:
            raise ValueError(f"{self.name} validator identity/version mismatch")
        return result


def gate_backend_validators(
    available: Mapping[str, BackendValidator],
    experiment_validator: BackendValidator,
) -> dict[str, BackendValidator]:
    unknown = set(available) - _BACKENDS
    if unknown:
        raise ValueError(f"unknown backend validator names: {sorted(unknown)}")
    result: dict[str, BackendValidator] = {"experiment": experiment_validator}
    for name in sorted(_BACKENDS):
        result[name] = cast(
            BackendValidator, ControllerBackendValidator(name, available.get(name))
        )
    return result
