"""V04 stale Fold bundle questions: non-blocking prompts, dismissed at Start."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine, Iterable
from typing import Any

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.control.snapshots import SnapshotPublisher
from cephvr.controller.state import (
    Attempt,
    ControlState,
    IncidentState,
    LifecycleState,
    LimitsState,
)
from cephvr.shared.deadlines import remaining_seconds

CHOICES = ("keep", "delete", "keep_all", "delete_all")
_DELETE_BATCH = 64


class StaleBundlePrompts:
    """Ask once per replaced bundle; unanswered keeps. Only Visual Stimulus deletes."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        incidents: IncidentState,
        control: ControlState,
        limit_state: LimitsState,
        publisher: SnapshotPublisher,
        spawn: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]],
        generation: str,
        clock: Callable[[], int],
    ) -> None:
        self.lifecycle = lifecycle
        self.incident_state = incidents
        self.control = control
        self.limit_state = limit_state
        self.publisher = publisher
        self.spawn = spawn
        self.generation = generation
        self.clock = clock
        self.bundles: dict[str, str] = {}  # prompt ID -> bundle ID

    def offer(self, attempt: Attempt, bundles: Iterable[pb.StaleImageBundle]) -> None:
        """Called under the lifecycle lock with accepted renderer Setup progress."""
        deletions = []
        for bundle in bundles:
            if attempt.stale_bundle_choice == "keep":
                continue
            if attempt.stale_bundle_choice == "delete":
                deletions.append(bundle.bundle_id)
                continue
            names = ", ".join(bundle.sources) or "an image"
            prompt = pb.Prompt(
                prompt_id=str(uuid.uuid4()),
                setup=attempt.context,
                operation=pb.OperationContext(command_id=str(uuid.uuid4())),
                explanation=(
                    f"{names} was baked again for the current calibration, placement "
                    f"or GPU. Delete its old Fold bundle {bundle.bundle_id}? "
                    "Unanswered questions keep the old bundle and close at Start."
                ),
                permitted_choices=CHOICES,
            )
            future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            self.incident_state.prompts[prompt.prompt_id] = (prompt, future, attempt)
            self.bundles[prompt.prompt_id] = bundle.bundle_id
            self.spawn(self._answer(attempt, prompt.prompt_id, future))
        if deletions:
            self.spawn(self._delete(attempt, deletions))

    def dismiss(self, attempt: Attempt) -> None:
        """Close this attempt's unanswered questions; their bundles are kept."""
        for prompt_id, (_, future, owner) in self.incident_state.prompts.items():
            if owner is attempt and prompt_id in self.bundles and not future.done():
                future.cancel()

    async def _answer(
        self, attempt: Attempt, prompt_id: str, future: asyncio.Future[str]
    ) -> None:
        try:
            choice = await future
        except asyncio.CancelledError:
            choice = "keep"
        async with self.lifecycle.lock:
            self.incident_state.prompts.pop(prompt_id, None)
            bundle_id = self.bundles.pop(prompt_id)
            deletions = [bundle_id] if choice in ("delete", "delete_all") else []
            if choice.endswith("_all"):
                attempt.stale_bundle_choice = choice.removesuffix("_all")
                for other, (_, pending, owner) in self.incident_state.prompts.items():
                    if (
                        owner is attempt
                        and other in self.bundles
                        and not pending.done()
                    ):
                        if choice == "delete_all":
                            deletions.append(self.bundles[other])
                        pending.cancel()
            self.publisher.publish()
        if deletions:
            await self._delete(attempt, deletions)

    async def _delete(self, attempt: Attempt, bundle_ids: list[str]) -> None:
        for start in range(0, len(bundle_ids), _DELETE_BATCH):
            chunk = bundle_ids[start : start + _DELETE_BATCH]
            error = ""
            try:
                await self._delete_chunk(attempt, chunk)
            except Exception as exc:
                error = str(exc) or "outcome unconfirmed"
            if error:
                async with self.lifecycle.lock:
                    self.control.add_warning(
                        "visual_stimulus",
                        f"old Fold bundle deletion failed ({', '.join(chunk)}): {error}",
                    )
                    self.publisher.publish()

    async def _delete_chunk(self, attempt: Attempt, bundle_ids: list[str]) -> None:
        backend = attempt.required.get("visual_stimulus")
        if backend is None:
            raise RuntimeError("Visual Stimulus is not part of this Setup")
        command = svc.BackendCommand(
            command_id=str(uuid.uuid4()),
            issuer=pb.ProcessIdentity(role="controller", generation=self.generation),
            target=backend.context,
            work=pb.WorkContext(session=attempt.context),
        )
        deadline = self.clock() + self.limit_state.current.recovery_ns
        async with asyncio.timeout(remaining_seconds(deadline, clock=self.clock)):
            admission = await backend.delete_stale_image_bundles(
                svc.StaleImageBundleDeletion(command=command, bundle_ids=bundle_ids),
                deadline_ns=deadline,
            )
            if admission.result != pb.COMMAND_RESULT_ACCEPTED:
                raise RuntimeError(admission.failure.message or "deletion rejected")
            query = svc.RetainedResultQuery(
                query=svc.BackendQuery(target=backend.context, work=command.work),
                command_id=command.command_id,
            )
            while True:
                result = await backend.get_retained_result(query, deadline_ns=deadline)
                operation = result.operation
                if result.found and operation.complete:
                    if operation.command != "DeleteStaleImageBundles":
                        raise RuntimeError("deletion result identity differs")
                    if not operation.succeeded:
                        raise RuntimeError(operation.failure.message or "failed")
                    return
                await asyncio.sleep(0.02)
