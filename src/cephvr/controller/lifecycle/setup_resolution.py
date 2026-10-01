"""E05 Setup adoption of resolved settings, trials and planned outputs."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from copy import deepcopy

from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.lifecycle.activity import activity_requirements
from cephvr.controller.lifecycle.evidence_wait import EvidenceWaiter
from cephvr.controller.lifecycle.preparation_context import PreparationContext
from cephvr.controller.state import Attempt


class SetupResolution:
    """Validate and adopt backend-resolved Setup results into the prepared session."""

    def __init__(
        self,
        *,
        clock: Callable[[], int],
        preparation_context: PreparationContext,
        evidence_waiter: EvidenceWaiter,
        validators: Mapping[
            str, Callable[[pb.ExperimentConfiguration], pb.ValidationResult]
        ],
        display_validator: Callable[[str], frozenset[str]] | None,
        output_planner: Callable[
            [pb.PreparedSession, Mapping[str, pb.ReadyReport]], list[pb.OutputPlan]
        ]
        | None,
    ) -> None:
        self.clock = clock
        self.preparation_context = preparation_context
        self.evidence_waiter = evidence_waiter
        self.validators = validators
        self.display_validator = display_validator
        self.output_planner = output_planner

    async def resolve_settings_and_outputs(
        self, attempt: Attempt, deadline: int
    ) -> None:
        """Validate exact resolved settings, display, trial plans and outputs."""
        effective = await self._adopt_resolved_settings(attempt, deadline)
        await self._adopt_resolved_trials(attempt, deadline, effective)
        self._plan_outputs(attempt)
        await self.evidence_waiter.wait_evidence(
            lambda: self.preparation_context.catalogues_match_ready(attempt),
            deadline,
            attempt,
        )

    async def _adopt_resolved_settings(
        self, attempt: Attempt, deadline: int
    ) -> pb.ExperimentConfiguration:
        """Overlay each Ready's exact settings, validate them and retain the result."""
        effective = deepcopy(attempt.prepared.configuration)
        for name in attempt.required:
            ready = attempt.ready[name]
            current = next(
                (item for item in effective.backends if item.backend_name == name),
                None,
            )
            resolved = ready.resolved_settings
            if (
                current is None
                or not current.enabled
                or resolved.backend_name != name
                or not resolved.enabled
                or resolved.WhichOneof("settings") != current.WhichOneof("settings")
            ):
                raise RuntimeError(f"{name} Ready lacks exact resolved settings")
            current.CopyFrom(resolved)
        results = await asyncio.wait_for(
            asyncio.gather(
                *(
                    asyncio.to_thread(validator, effective)
                    for validator in self.validators.values()
                )
            ),
            max(0, (deadline - self.clock()) / 1e9),
        )
        if not results or any(
            not result.completed or not result.valid for result in results
        ):
            raise RuntimeError("resolved effective settings failed pure validation")
        attempt.prepared.configuration.CopyFrom(effective)
        return effective

    async def _adopt_resolved_trials(
        self,
        attempt: Attempt,
        deadline: int,
        effective: pb.ExperimentConfiguration,
    ) -> None:
        """Validate the display and adopt Visual Stimulus's resolved trials."""
        visual_stimulus = attempt.ready.get("visual_stimulus")
        if visual_stimulus is None or len(visual_stimulus.resolved_trials) != len(
            attempt.prepared.trials
        ):
            raise RuntimeError("Visual Stimulus did not provide every resolved trial")
        if self.display_validator is None:
            raise RuntimeError("display output validator unavailable")
        visual_stimulus_settings = next(
            item.visual_stimulus
            for item in effective.backends
            if item.backend_name == "visual_stimulus" and item.enabled
        )
        attempt.visual_stimulus_output_ids = await asyncio.wait_for(
            asyncio.to_thread(
                self.display_validator, visual_stimulus_settings.display.profile_json
            ),
            max(0, (deadline - self.clock()) / 1e9),
        )
        if not attempt.visual_stimulus_output_ids:
            raise RuntimeError(
                "Visual Stimulus resolved display has no required outputs"
            )
        for index, resolved_trial in enumerate(visual_stimulus.resolved_trials):
            if (
                resolved_trial.context != attempt.prepared.trials[index].context
                or resolved_trial.definition
                != attempt.prepared.trials[index].definition
                or not resolved_trial.HasField("resolved_duration_ns")
                or resolved_trial.resolved_duration_ns < 60_000_000_000
            ):
                raise RuntimeError(
                    "Visual Stimulus resolved duration or trial identity invalid"
                )
            attempt.prepared.trials[index].CopyFrom(resolved_trial)

    def _plan_outputs(self, attempt: Attempt) -> None:
        """Plan and validate the required outputs for the prepared session."""
        if self.output_planner is None:
            raise RuntimeError("output reservation planner unavailable")
        outputs = self.output_planner(attempt.prepared, attempt.ready)
        if not outputs:
            raise RuntimeError("required output plan unavailable")
        for name in attempt.required:
            activity_requirements(attempt, name)
        seen: set[str] = set()
        for output in outputs:
            if (
                not output.output_key
                or output.output_key in seen
                or output.trial.session != attempt.context
            ):
                raise RuntimeError("output plan identity or key invalid")
            seen.add(output.output_key)
            attempt.prepared.outputs.add().CopyFrom(output)
