"""Renderer interface only; all plan payloads are artifact_models.PreparedTrial."""
from typing import Protocol
from artifact_models import PreparedTrial
class PreparedExecution(Protocol):
    def begin_trial(self, plan: PreparedTrial, start_host_ns: int) -> None:
        """Activate the already adopted/prepared artifact; no new I/O or compilation."""
        ...
    def advance_scheduled_state(self, trial_offset_ns: int) -> None:
        """Advance ordered boundaries once; consume prepared indexes, not authoring JSON."""
        ...
    def stop_trial(self, cutoff_offset_ns: int) -> None:
        """Seal at the actual cutoff, without executing future boundaries."""
        ...
