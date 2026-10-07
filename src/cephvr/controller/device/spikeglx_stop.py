"""Owned, trial-bound delayed stop for controller-owned SpikeGLX (E12)."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Coroutine
from typing import Any

from cephvr.controller.ports import SpikeGLXPort
from cephvr.controller.state import Attempt, LifecycleState


class SpikeGLXStopScheduler:
    """Schedule stop against exact Stopped evidence and one frozen margin."""

    def __init__(
        self,
        *,
        lifecycle: LifecycleState,
        spikeglx: SpikeGLXPort | None,
        clock: Callable[[], int],
        spawn: Callable[[Coroutine[Any, Any, bool]], asyncio.Task[bool]],
        stop: Callable[[Attempt, int], Coroutine[Any, Any, bool]],
    ) -> None:
        self.lifecycle = lifecycle
        self.spikeglx = spikeglx
        self.clock = clock
        self.spawn = spawn
        self.stop = stop

    def arm(
        self,
        attempt: Attempt,
        *,
        stopped_deadline_ns: int,
        final_trial: bool,
        interruption: bool = False,
        immediate: bool = False,
    ) -> None:
        if not attempt.paired or self.spikeglx is None:
            return
        margin_ns = self._margin_ns()
        if margin_ns is None:
            return
        due_ns = stopped_deadline_ns if immediate else stopped_deadline_ns + margin_ns
        operation = attempt.trial_operation
        trial_index = attempt.trial_index
        trial_end_ns = attempt.end_ns
        task = attempt.spikeglx_stop_task
        if task is not None and not task.done():
            if attempt.spikeglx_stop_started:
                return
            binding_changed = (
                attempt.spikeglx_stop_trial_operation != operation
                or attempt.spikeglx_stop_trial_index != trial_index
                or attempt.spikeglx_stop_trial_end_ns != trial_end_ns
            )
            supersedes = interruption or due_ns < attempt.spikeglx_stop_due_ns
            if not binding_changed and not supersedes:
                return
            task.cancel()
        attempt.spikeglx_stop_due_ns = due_ns
        attempt.spikeglx_stop_trial_operation = operation
        attempt.spikeglx_stop_trial_index = trial_index
        attempt.spikeglx_stop_trial_end_ns = trial_end_ns
        attempt.spikeglx_stop_final_trial = final_trial
        attempt.spikeglx_stop_started = False
        attempt.spikeglx_stop_task = self.spawn(
            self._run(
                attempt,
                due_ns=due_ns,
                final_trial=final_trial,
                interruption=interruption,
                operation=operation,
                trial_index=trial_index,
                trial_end_ns=trial_end_ns,
            )
        )

    def withdraw(self, attempt: Attempt) -> None:
        task = attempt.spikeglx_stop_task
        if (
            task is None
            or task.done()
            or attempt.spikeglx_stop_started
            or attempt.spikeglx_stop_final_trial
        ):
            return
        task.cancel()
        attempt.spikeglx_stop_task = None
        attempt.spikeglx_stop_due_ns = 0
        attempt.spikeglx_stop_trial_operation = ""
        attempt.spikeglx_stop_trial_index = -1
        attempt.spikeglx_stop_trial_end_ns = 0
        attempt.spikeglx_stop_final_trial = False

    async def finish(self, attempt: Attempt, deadline_ns: int) -> bool:
        task = attempt.spikeglx_stop_task
        if task is None:
            return await self.stop(attempt, deadline_ns)
        try:
            if task.done():
                result = task.result()
            else:
                result = await asyncio.wait_for(
                    task, max(0, (deadline_ns - self.clock()) / 1e9)
                )
        except TimeoutError:
            return False
        except asyncio.CancelledError:
            if not attempt.spikeglx_stop_started:
                return await self.stop(attempt, deadline_ns)
            raise
        except Exception:
            return False
        if result or attempt.spikeglx_stopped:
            return result or attempt.spikeglx_stopped
        if attempt.spikeglx_stop_started or self.clock() >= deadline_ns:
            return False
        return await self.stop(attempt, deadline_ns)

    async def _run(
        self,
        attempt: Attempt,
        *,
        due_ns: int,
        final_trial: bool,
        interruption: bool,
        operation: str,
        trial_index: int,
        trial_end_ns: int,
    ) -> bool:
        await asyncio.sleep(max(0, (due_ns - self.clock()) / 1e9))
        async with self.lifecycle.lock:
            same_trial = (
                attempt.trial_operation == operation
                and attempt.trial_index == trial_index
                and attempt.end_ns == trial_end_ns
            )
            should_stop = self.lifecycle.attempt is attempt and (
                (interruption and attempt.interrupted)
                or (
                    not interruption
                    and same_trial
                    and (final_trial or self.lifecycle.session.stop_after_trial)
                )
            )
            if should_stop:
                attempt.spikeglx_stop_started = True
        if not should_stop or self.spikeglx is None:
            return False
        try:
            _, call_timeout_s, _ = self.spikeglx.monitor_budgets()
            deadline_ns = due_ns + int(3 * call_timeout_s * 1e9)
            if attempt.finalization_deadline_ns:
                deadline_ns = min(deadline_ns, attempt.finalization_deadline_ns)
        except Exception:
            return False
        if self.clock() >= deadline_ns:
            return False
        return await self.stop(attempt, deadline_ns)

    def _margin_ns(self) -> int | None:
        if self.spikeglx is None:
            return None
        try:
            margin = self.spikeglx.stop_margin_s()
            if not math.isfinite(margin) or margin < 0:
                return None
            return int(margin * 1e9)
        except Exception:
            return None
