"""Controller-owned SpikeGLX serialization and typed inventory checks (E12)."""

from __future__ import annotations

import asyncio
import shutil
import threading
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from cephvr.control.v1 import services_pb2 as svc
from cephvr.control.v1 import types_pb2 as pb
from cephvr.controller.device.spikeglx_inventory import SpikeGLXInventory
from cephvr.controller.device.spikeglx_monitor import SpikeGLXProgressMonitor
from cephvr.controller.device.spikeglx_stop import SpikeGLXStopScheduler
from cephvr.controller.lifecycle.interruption import _spikeglx_stop_base_ns
from cephvr.controller.state import Attempt, ConfigurationState, LifecycleState
from cephvr.shared.clock import host_time_ns
from cephvr.synchronization import client as client_module
from cephvr.synchronization.client import (
    SpikeGLXControllerClient,
    _validate_inventory,
)
from cephvr.synchronization.configuration import validate_configuration
from cephvr.synchronization.inventory import read_inventory, update_inventory
from cephvr.synchronization.monitor import SpikeGLXProgressIO
from cephvr.synchronization.native import Readback
from cephvr.synchronization.sdk_io import SpikeGLXIOBusy, SpikeGLXIOOwner
from cephvr.synchronization.settings import HostSettings, load_host_settings
from cephvr.synchronization.v1 import spikeglx_pb2 as wire


def _unmapped_host_configuration(repository: Path) -> str:
    """Inventory fixtures are independent of the operator's saved wiring."""
    text = (repository / "config/backends/synchronization_config.toml").read_text()
    start = text.index("[pulse_inventory]")
    end = text.index("[monitor]", start)
    section = "".join(
        line
        for line in text[start:end].splitlines(keepends=True)
        if line.startswith("[") or not line.strip() or line.lstrip().startswith("#")
    )
    return text[:start] + section + text[end:]


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatched_readback", [False, True])
async def test_setup_sends_exact_reserved_session_folder_as_spikeglx_run_name(
    tmp_path: Path, mismatched_readback: bool
) -> None:
    from tests.controller.support_components import _attempt, _runtime

    runtime = _runtime(tmp_path, pb.BackendContext(backend_name="visual_stimulus"))
    attempt = _attempt(runtime, tmp_path, {})
    attempt.prepared.configuration.experiment = "different-experiment"
    attempt.prepared.configuration.subject = "different-subject"
    attempt.prepared.anchor_wall_time = "2026-10-19T10:20:30+09:00"
    expected = attempt.reservation.session_directory.name
    sent = []

    class Remote:
        async def prepare(self, configuration, session, run_name):
            sent.append((configuration, session, run_name))
            return wire.SpikeGLXPreparation(
                address="169.254.240.108",
                port=4142,
                run_name="wrong-session" if mismatched_readback else run_name,
                spikeglx_version="observed",
                sdk_version="unknown",
                mapping_id="verified-map",
                data_directory="C:/SGL_DATA",
                streams=[wire.NativeStream(family=wire.STREAM_FAMILY_ONEBOX)],
            )

    runtime.setup_execution.spikeglx = Remote()  # type: ignore[assignment]
    if mismatched_readback:
        with pytest.raises(RuntimeError, match="run identity"):
            await runtime.setup_execution._prepare_spikeglx(attempt, 1_000_000_000)
        assert not attempt.prepared.HasField("spikeglx")
    else:
        await runtime.setup_execution._prepare_spikeglx(attempt, 1_000_000_000)
        assert attempt.prepared.spikeglx.run_name == expected
    assert sent == [(attempt.prepared.configuration, attempt.context, expected)]


def test_paired_registration_keeps_preliminary_local_catalogues_unprepared(
    tmp_path: Path,
) -> None:
    from uuid import uuid4

    from tests.controller.support_components import _attempt, _runtime

    backend = pb.BackendContext(
        backend_name="visual_stimulus", backend_generation=str(uuid4())
    )
    runtime = _runtime(tmp_path, backend)
    attempt = _attempt(
        runtime, tmp_path, {"visual_stimulus": SimpleNamespace(context=backend)}
    )
    attempt.paired = True
    preparation = runtime.setup_execution.preparation_context
    preliminary = preparation.registration(attempt, str(uuid4()))
    assert preliminary.context.paired_spikeglx
    assert not preliminary.context.prepared_functions

    attempt.ready["visual_stimulus"] = pb.ReadyReport()
    final = preparation.registration(attempt, str(uuid4()))
    assert final.context.paired_spikeglx
    assert [f.resource_id for f in final.context.prepared_functions] == [
        "spikeglx_recording"
    ]
    assert final.context.prepared_functions[0].owner == final.context.controller


@pytest.mark.parametrize(
    ("settings", "enabled", "duplicate", "code"),
    [
        (None, True, False, ""),
        ("synchronization", True, False, ""),
        (None, False, False, ""),
        ("acquisition", True, False, "INVALID_SETTINGS"),
        (None, True, True, "DUPLICATE_BACKEND"),
    ],
)
def test_pure_pairing_configuration(settings, enabled, duplicate, code) -> None:
    candidate = pb.ExperimentConfiguration()
    backend = candidate.backends.add(backend_name="synchronization", enabled=enabled)
    if settings is not None:
        getattr(backend, settings).SetInParent()
    if duplicate:
        candidate.backends.add(backend_name="synchronization", enabled=True)
    before = candidate.SerializeToString()

    result = validate_configuration(candidate)

    assert result.completed
    assert result.valid == (not code)
    assert result.component == "synchronization"
    assert result.configuration_module_version
    assert [issue.failure.code for issue in result.issues] == ([code] if code else [])
    assert candidate.SerializeToString() == before
    assert validate_configuration(pb.ExperimentConfiguration()).valid


def test_installed_host_configuration_is_file_only_and_mapping_is_pinned() -> None:
    software_root = Path(__file__).resolve().parents[2]
    settings = load_host_settings(software_root)
    assert settings.address
    assert settings.port == 4142
    assert len(settings.file_sha256) == 64
    assert settings.mapping["mapping_id"] == "spikeglx-20251218-reference-v1"


def test_inventory_requires_all_source_roles_and_preserves_optional_bit_presence() -> (
    None
):
    streams = (
        wire.NativeStream(
            family=wire.STREAM_FAMILY_ONEBOX,
            index=0,
            acquired_channel_counts=(1, 2, 0),
            saved_channel_indices=(1, 2),
        ),
        wire.NativeStream(
            family=wire.STREAM_FAMILY_NI,
            index=0,
            acquired_channel_counts=(0, 0, 0, 5),
            saved_channel_indices=(4,),
        ),
    )
    mapping = load_host_settings(Path(__file__).resolve().parents[2]).mapping
    inventory = {
        "behavioral_camera": {
            "stream": "onebox",
            "stream_index": 0,
            "channel": 1,
            "bit": 0,
        },
        "eye_tracking_camera": {
            "stream": "onebox",
            "stream_index": 0,
            "channel": 1,
            "bit": 1,
        },
        "tracking_camera": {
            "stream": "onebox",
            "stream_index": 0,
            "channel": 2,
        },
        "photodiode": {"stream": "ni", "stream_index": 0, "channel": 4},
    }
    with pytest.raises(ValueError, match="mapping omits channel type order"):
        _validate_inventory(inventory, streams, {})
    result = _validate_inventory(inventory, streams, mapping)
    by_role = {wire.PulseRole.Name(item.role): item for item in result}
    assert by_role["PULSE_ROLE_BEHAVIORAL_CAMERA"].HasField("bit")
    assert by_role["PULSE_ROLE_BEHAVIORAL_CAMERA"].bit == 0
    assert not by_role["PULSE_ROLE_TRACKING_CAMERA"].HasField("bit")

    inventory.pop("photodiode")
    with pytest.raises(ValueError, match="missing required active roles"):
        _validate_inventory(inventory, streams, mapping)


def test_inventory_rejects_bit_outside_mapped_native_word() -> None:
    streams = (
        wire.NativeStream(
            family=wire.STREAM_FAMILY_ONEBOX,
            index=0,
            acquired_channel_counts=(2, 1, 1),
            saved_channel_indices=(0, 2, 3),
        ),
        wire.NativeStream(
            family=wire.STREAM_FAMILY_NI,
            index=0,
            acquired_channel_counts=(0, 0, 0, 3),
            saved_channel_indices=(2,),
        ),
    )
    mapping = load_host_settings(Path(__file__).resolve().parents[2]).mapping
    inventory = {
        "behavioral_camera": {
            "stream": "onebox",
            "stream_index": 0,
            "channel": 0,
            "bit": 16,
        },
        "eye_tracking_camera": {
            "stream": "onebox",
            "stream_index": 0,
            "channel": 2,
            "bit": 1,
        },
        "tracking_camera": {"stream": "onebox", "stream_index": 0, "channel": 2},
        "photodiode": {"stream": "ni", "stream_index": 0, "channel": 2},
    }
    with pytest.raises(ValueError, match="digital word"):
        _validate_inventory(inventory, streams, mapping)
    inventory["behavioral_camera"]["channel"] = 2
    inventory["behavioral_camera"]["bit"] = 12
    with pytest.raises(ValueError, match="digital word"):
        _validate_inventory(inventory, streams, mapping)


def test_inactive_retained_photodiode_does_not_require_a_saved_channel() -> None:
    mapping = load_host_settings(Path(__file__).resolve().parents[2]).mapping
    channel = wire.PulseChannel(
        role=wire.PULSE_ROLE_PHOTODIODE,
        family=wire.STREAM_FAMILY_NI,
        stream_index=0,
        channel_index=22,
    )
    assert _validate_inventory((channel,), (), mapping, required_roles=frozenset()) == (
        channel,
    )
    digital_word = wire.PulseChannel(
        role=wire.PULSE_ROLE_PHOTODIODE,
        family=wire.STREAM_FAMILY_NI,
        stream_index=0,
        channel_index=0,
        bit=0,
    )
    acquired_but_unsaved = wire.NativeStream(
        family=wire.STREAM_FAMILY_NI,
        index=0,
        acquired_channel_counts=(0, 0, 0, 1),
        saved_channel_indices=(),
    )
    assert _validate_inventory(
        (digital_word,),
        (acquired_but_unsaved,),
        mapping,
        required_roles=frozenset(),
    ) == (digital_word,)


def test_released_trial_without_started_uses_local_stopped_deadline() -> None:
    session = pb.SessionContext(
        controller_generation="be848407-e044-45cc-98ed-8908777f9dc5",
        session_id="724d476d-b9eb-4f52-8afb-30ae1b1014fd",
    )
    attempt = Attempt(
        session,
        pb.PreparedSession(context=session),
        None,  # type: ignore[arg-type]
        {},
        {},
    )
    attempt.trial_closure.released = True
    assert _spikeglx_stop_base_ns(attempt, 1_000, 100) == (1_000, False)
    # A stale phase flag during the inter-trial gap cannot override confirmed
    # trial-log closure, even though Started and Release remain in history.
    attempt.trial_log_finished = True
    assert _spikeglx_stop_base_ns(attempt, 1_000, 100, trial_active=True) == (100, True)
    assert _spikeglx_stop_base_ns(
        attempt, 1_000, 100, trial_active=True, trial_log_finished=True
    ) == (100, True)
    # Without a current active trial the same retained history is immediate.
    assert _spikeglx_stop_base_ns(attempt, 1_000, 100, trial_active=False) == (
        100,
        True,
    )

    no_trial = Attempt(
        session,
        pb.PreparedSession(context=session),
        None,  # type: ignore[arg-type]
        {},
        {},
    )
    assert _spikeglx_stop_base_ns(no_trial, 1_000, 100) == (100, True)


def test_monitor_treats_unknown_as_no_advance_and_resets_per_stream_clock() -> None:
    first, second = (wire.STREAM_FAMILY_NI, 0), (wire.STREAM_FAMILY_ONEBOX, 0)
    saved = (first, second)
    counts: dict[tuple[int, int], int] = {}
    progress = {first: 100, second: 100}
    unknown = wire.SpikeGLXRecordingView(
        phase=wire.SPIKEGLX_RECORDING_PHASE_UNKNOWN,
        failure_code="TIMEOUT",
    )
    assert (
        SpikeGLXProgressMonitor._fault(unknown, saved, counts, progress, 200, 10) == ""
    )
    assert (
        SpikeGLXProgressMonitor._fault(
            unknown, saved, counts, progress, 10_000_000_200, 10
        )
        == "NO_PROGRESS"
    )

    baseline = wire.SpikeGLXRecordingView(
        phase=wire.SPIKEGLX_RECORDING_PHASE_WRITING,
        running=True,
        saving=True,
        run_name_matches=True,
        progress=[
            wire.StreamProgress(family=first[0], index=first[1], sample_count=40),
            wire.StreamProgress(family=second[0], index=second[1], sample_count=50),
        ],
    )
    assert (
        SpikeGLXProgressMonitor._fault(
            baseline, saved, counts, progress, 10_500_000_000, 10
        )
        == "NO_PROGRESS"
    )
    recovered = wire.SpikeGLXRecordingView(
        phase=wire.SPIKEGLX_RECORDING_PHASE_WRITING,
        running=True,
        saving=True,
        run_name_matches=True,
        progress=[
            wire.StreamProgress(family=first[0], index=first[1], sample_count=50),
            wire.StreamProgress(family=second[0], index=second[1], sample_count=50),
        ],
    )
    assert (
        SpikeGLXProgressMonitor._fault(
            recovered, saved, counts, progress, 11_000_000_000, 10
        )
        == "NO_PROGRESS"
    )
    assert progress[first] == 11_000_000_000
    assert progress[second] == 100
    assert not SpikeGLXProgressMonitor._recovered(
        recovered, saved, progress, 10_500_000_000
    )
    recovered.progress[1].sample_count = 60
    assert (
        SpikeGLXProgressMonitor._fault(
            recovered, saved, counts, progress, 11_500_000_000, 10
        )
        == ""
    )
    assert SpikeGLXProgressMonitor._recovered(
        recovered, saved, progress, 10_500_000_000
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_code", ["TIMEOUT", "RuntimeError", ""])
async def test_monitor_loop_retains_gate_baseline_through_unknown_observation(
    failure_code: str,
) -> None:
    session = pb.SessionContext(
        controller_generation="be848407-e044-45cc-98ed-8908777f9dc5",
        session_id="724d476d-b9eb-4f52-8afb-30ae1b1014fd",
    )
    streams = (
        wire.NativeStream(
            family=wire.STREAM_FAMILY_NI, index=0, saved_channel_indices=(0,)
        ),
        wire.NativeStream(
            family=wire.STREAM_FAMILY_ONEBOX,
            index=0,
            saved_channel_indices=(0,),
        ),
    )
    attempt = Attempt(
        session,
        pb.PreparedSession(
            context=session,
            spikeglx=wire.SpikeGLXPreparation(streams=streams),
        ),
        None,  # type: ignore[arg-type]
        {},
        {},
        paired=True,
    )
    lifecycle = LifecycleState(
        session=pb.SessionState(phase=pb.SESSION_PHASE_RUNNING), attempt=attempt
    )

    class FakeSpikeGLX:
        def monitor_baseline(self) -> tuple[wire.StreamProgress, ...]:
            return (
                wire.StreamProgress(
                    family=wire.STREAM_FAMILY_NI,
                    index=0,
                    sample_count=100,
                    last_progress_monotonic_ns=100,
                ),
                wire.StreamProgress(
                    family=wire.STREAM_FAMILY_ONEBOX,
                    index=0,
                    sample_count=200,
                    last_progress_monotonic_ns=100,
                ),
            )

        def monitor_budgets(self) -> tuple[float, float, float]:
            return (0, 1, 10)

        async def observe_progress(
            self, deadline_ns: int
        ) -> wire.SpikeGLXRecordingView:
            del deadline_ns
            return wire.SpikeGLXRecordingView(
                phase=wire.SPIKEGLX_RECORDING_PHASE_UNKNOWN,
                failure_code=failure_code,
            )

    class FakeIncidents:
        async def observe_runtime_error(self, error: pb.ErrorReport) -> str | None:
            del error
            pytest.fail("a sub-threshold unknown query must not open an incident")

        async def resolve_recovered_incident(
            self, attempt: Attempt, incident_id: str, now: int
        ) -> bool:
            del attempt, incident_id, now
            return False

    class FakePublisher:
        def publish(self) -> None:
            attempt.spikeglx_monitor_stop.set()

    monitor = SpikeGLXProgressMonitor(
        lifecycle=lifecycle,
        spikeglx=FakeSpikeGLX(),  # type: ignore[arg-type]
        incidents=FakeIncidents(),  # type: ignore[arg-type]
        publisher=FakePublisher(),  # type: ignore[arg-type]
        generation=session.controller_generation,
        clock=lambda: 1_000,
    )
    await monitor.run(attempt)
    assert attempt.spikeglx_recording.failure_code == (
        failure_code or "OBSERVATION_UNCONFIRMED"
    )
    assert not attempt.spikeglx_recording.HasField("observed_monotonic_ns")
    assert not attempt.spikeglx_recording.HasField("running")
    assert not attempt.spikeglx_recording.HasField("saving")
    retained = {
        (item.family, item.index): item for item in attempt.spikeglx_recording.progress
    }
    assert retained[(wire.STREAM_FAMILY_NI, 0)].sample_count == 100
    assert retained[(wire.STREAM_FAMILY_NI, 0)].last_progress_monotonic_ns == 100
    assert retained[(wire.STREAM_FAMILY_ONEBOX, 0)].sample_count == 200


@pytest.mark.asyncio
async def test_recovered_spikeglx_fault_opens_a_new_episode_on_later_loss() -> None:
    session = pb.SessionContext(
        controller_generation="be848407-e044-45cc-98ed-8908777f9dc5",
        session_id="724d476d-b9eb-4f52-8afb-30ae1b1014fd",
    )
    streams = (
        wire.NativeStream(
            family=wire.STREAM_FAMILY_NI, index=0, saved_channel_indices=(0,)
        ),
        wire.NativeStream(
            family=wire.STREAM_FAMILY_ONEBOX,
            index=0,
            saved_channel_indices=(0,),
        ),
    )
    attempt = Attempt(
        session,
        pb.PreparedSession(
            context=session,
            spikeglx=wire.SpikeGLXPreparation(streams=streams),
        ),
        None,  # type: ignore[arg-type]
        {},
        {},
        paired=True,
    )
    lifecycle = LifecycleState(
        session=pb.SessionState(phase=pb.SESSION_PHASE_RUNNING), attempt=attempt
    )
    now = [100]

    def clock() -> int:
        now[0] += 100
        return now[0]

    class FakeSpikeGLX:
        observations = iter(((100, 200), (101, 201), (101, 201)))

        def monitor_baseline(self) -> tuple[wire.StreamProgress, ...]:
            return (
                wire.StreamProgress(
                    family=wire.STREAM_FAMILY_NI,
                    index=0,
                    sample_count=100,
                    last_progress_monotonic_ns=100,
                ),
                wire.StreamProgress(
                    family=wire.STREAM_FAMILY_ONEBOX,
                    index=0,
                    sample_count=200,
                    last_progress_monotonic_ns=100,
                ),
            )

        def monitor_budgets(self) -> tuple[float, float, float]:
            return (0, 1, 0.0000001)

        async def observe_progress(
            self, deadline_ns: int
        ) -> wire.SpikeGLXRecordingView:
            first, second = next(self.observations)
            return wire.SpikeGLXRecordingView(
                phase=wire.SPIKEGLX_RECORDING_PHASE_WRITING,
                running=True,
                saving=True,
                run_name_matches=True,
                observed_monotonic_ns=deadline_ns,
                progress=(
                    wire.StreamProgress(
                        family=wire.STREAM_FAMILY_NI,
                        index=0,
                        sample_count=first,
                    ),
                    wire.StreamProgress(
                        family=wire.STREAM_FAMILY_ONEBOX,
                        index=0,
                        sample_count=second,
                    ),
                ),
            )

    class FakeIncidents:
        episodes: list[str] = []

        async def observe_runtime_error(self, error: pb.ErrorReport) -> str | None:
            self.episodes.append(error.incident_episode_id)
            return f"incident-{len(self.episodes)}"

        async def resolve_recovered_incident(
            self, _attempt: Attempt, _incident_id: str, _now: int
        ) -> bool:
            return True

    class FakePublisher:
        calls = 0

        def publish(self) -> None:
            self.calls += 1
            if self.calls >= 3:
                attempt.spikeglx_monitor_stop.set()

    incidents, publisher = FakeIncidents(), FakePublisher()
    monitor = SpikeGLXProgressMonitor(
        lifecycle=lifecycle,
        spikeglx=FakeSpikeGLX(),  # type: ignore[arg-type]
        incidents=incidents,  # type: ignore[arg-type]
        publisher=publisher,  # type: ignore[arg-type]
        generation=session.controller_generation,
        clock=clock,
    )
    await monitor.run(attempt)
    assert len(incidents.episodes) == 2
    assert incidents.episodes[0] != incidents.episodes[1]


@pytest.mark.asyncio
async def test_spikeglx_stop_scheduler_waits_margin_and_tracks_stop_after_toggle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cephvr.controller.device import spikeglx_stop as stop_module

    now = [100]
    sleeps: list[int] = []

    async def advance_sleep(seconds: float) -> None:
        delta = int(seconds * 1e9)
        sleeps.append(delta)
        now[0] += delta

    monkeypatch.setattr(stop_module.asyncio, "sleep", advance_sleep)
    session = pb.SessionContext(
        controller_generation="be848407-e044-45cc-98ed-8908777f9dc5",
        session_id="724d476d-b9eb-4f52-8afb-30ae1b1014fd",
    )
    attempt = Attempt(
        session,
        pb.PreparedSession(context=session),
        None,  # type: ignore[arg-type]
        {},
        {},
        paired=True,
    )
    attempt.trial_operation = "trial-one"
    attempt.trial_index = 0
    attempt.end_ns = 100
    lifecycle = LifecycleState(
        session=pb.SessionState(phase=pb.SESSION_PHASE_RUNNING), attempt=attempt
    )

    class FakeSpikeGLX:
        def stop_margin_s(self) -> float:
            return 0.0000001

        def monitor_budgets(self) -> tuple[float, float, float]:
            return (0.01, 1.0, 10.0)

    stopped_at: list[int] = []
    stop_deadlines: list[int] = []

    async def stop_expected_run(candidate: Attempt, deadline_ns: int) -> bool:
        assert candidate is attempt
        assert deadline_ns > now[0]
        stopped_at.append(now[0])
        stop_deadlines.append(deadline_ns)
        return True

    scheduler = SpikeGLXStopScheduler(
        lifecycle=lifecycle,
        spikeglx=FakeSpikeGLX(),  # type: ignore[arg-type]
        clock=lambda: now[0],
        spawn=lambda coroutine: asyncio.create_task(coroutine),
        stop=stop_expected_run,
    )
    scheduler.arm(
        attempt,
        stopped_deadline_ns=100,
        final_trial=False,
    )
    cancelled_schedule = attempt.spikeglx_stop_task
    assert cancelled_schedule is not None
    assert not await cancelled_schedule
    assert sleeps == [100]
    assert not stopped_at

    scheduler.arm(
        attempt,
        stopped_deadline_ns=100,
        final_trial=False,
    )
    withdrawn_schedule = attempt.spikeglx_stop_task
    assert withdrawn_schedule is not None
    scheduler.withdraw(attempt)
    assert attempt.spikeglx_stop_task is None
    await asyncio.gather(withdrawn_schedule, return_exceptions=True)
    assert withdrawn_schedule.cancelled()

    attempt.trial_operation = "trial-two"
    attempt.trial_index = 1
    attempt.end_ns = 10_000
    lifecycle.session.stop_after_trial = True
    scheduler.arm(
        attempt,
        stopped_deadline_ns=11_000,
        final_trial=False,
    )
    next_trial_schedule = attempt.spikeglx_stop_task
    assert next_trial_schedule is not None
    assert attempt.spikeglx_stop_due_ns == 11_100
    assert await next_trial_schedule
    assert stopped_at == [11_100]
    assert stop_deadlines[-1] == 11_100 + 3_000_000_000

    attempt.spikeglx_stopped = False
    attempt.interrupted = True
    attempt.trial_operation = "trial-three"
    attempt.trial_index = 2
    attempt.end_ns = 99_000
    now[0] = 1_200
    lifecycle.session.stop_after_trial = False
    scheduler.arm(
        attempt,
        stopped_deadline_ns=1_250,
        final_trial=True,
    )
    old_normal_schedule = attempt.spikeglx_stop_task
    scheduler.arm(
        attempt,
        stopped_deadline_ns=1_250,
        final_trial=True,
        interruption=True,
    )
    interruption_schedule = attempt.spikeglx_stop_task
    assert interruption_schedule is not None
    assert attempt.spikeglx_stop_due_ns == 1_350
    assert old_normal_schedule is not interruption_schedule
    assert await interruption_schedule
    assert stopped_at[-1] == 1_350


@pytest.mark.asyncio
async def test_finalization_deadline_cancels_pending_stop_before_new_sdk_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cephvr.synchronization import client as client_module

    now = host_time_ns()
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    stop_calls: list[bool] = []
    client = SpikeGLXControllerClient(
        Path("."), controller_generation="test", clock=host_time_ns
    )
    settings = HostSettings("127.0.0.1", 4142, 1, 1, 0.1, 1, 0, (), {})
    client._prepared_settings = settings
    client._prepared = wire.SpikeGLXPreparation(
        run_name="managed", data_directory="D:/data"
    )

    read_calls: list[bool] = []

    def blocked_read(_root: Path, _settings: HostSettings) -> Readback:
        read_calls.append(True)
        entered.set()
        release.wait(2)
        returned.set()
        return Readback(
            "version",
            "D:/data",
            True,
            True,
            "managed",
            (),
            "digest",
            "immediate",
            "immediate",
            (),
        )

    monkeypatch.setattr(client_module, "read_sdk", blocked_read)

    class FakeSDK:
        @staticmethod
        def c_sglx_stopRun(_handle: int) -> bool:
            stop_calls.append(True)
            return True

    def with_sdk(_root: Path, _settings: HostSettings, operation: object) -> object:
        return operation(FakeSDK(), 1)  # type: ignore[operator]

    monkeypatch.setattr(client_module, "with_sdk", with_sdk)

    class FakeSpikeGLX:
        def stop_margin_s(self) -> float:
            return 0

        def monitor_budgets(self) -> tuple[float, float, float]:
            return (0.1, 1, 10)

    session = pb.SessionContext(
        controller_generation="be848407-e044-45cc-98ed-8908777f9dc5",
        session_id="724d476d-b9eb-4f52-8afb-30ae1b1014fd",
    )
    attempt = Attempt(
        session,
        pb.PreparedSession(context=session),
        None,  # type: ignore[arg-type]
        {},
        {},
        paired=True,
    )
    attempt.trial_operation = "trial-one"
    attempt.trial_index = 0
    attempt.end_ns = now
    attempt.finalization_deadline_ns = now + 30_000_000
    lifecycle = LifecycleState(
        session=pb.SessionState(phase=pb.SESSION_PHASE_FINALIZING), attempt=attempt
    )
    scheduler = SpikeGLXStopScheduler(
        lifecycle=lifecycle,
        spikeglx=FakeSpikeGLX(),  # type: ignore[arg-type]
        clock=host_time_ns,
        spawn=lambda coroutine: asyncio.create_task(coroutine),
        stop=lambda _attempt, deadline: client.stop_expected_run(deadline),
    )
    scheduler.arm(
        attempt,
        stopped_deadline_ns=now,
        final_trial=True,
    )
    assert await asyncio.to_thread(entered.wait, 1)
    assert not await scheduler.finish(attempt, attempt.finalization_deadline_ns)
    release.set()
    assert await asyncio.to_thread(returned.wait, 1)
    await asyncio.sleep(0.01)
    assert not stop_calls
    assert len(read_calls) == 1
    assert not attempt.spikeglx_stopped
    client.io_owner.close(wait=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("running", "saving"), [(True, False), (False, False), (True, True)]
)
async def test_preparation_is_read_only_and_requires_unsaved_acquisition(
    monkeypatch: pytest.MonkeyPatch,
    running: bool,
    saving: bool,
) -> None:
    settings = HostSettings(
        "10.0.0.1", 4142, 1, 1, 0.1, 0.5, 1, (), {"mapping_id": "source-reviewed-map"}
    )
    before = Readback(
        "observed-version",
        "D:/data",
        running,
        saving,
        "insertion",
        (),
        "params",
        "immediate",
        "immediate",
        (),
    )
    client = SpikeGLXControllerClient(Path("."), controller_generation="test")
    monkeypatch.setattr(client_module, "load_host_settings", lambda _root: settings)
    monkeypatch.setattr(client_module, "read_sdk", lambda *_args: before)
    monkeypatch.setattr(
        client_module, "_validate_inventory", lambda *_args, **_kwargs: ()
    )

    def forbid_mutation(*args):
        raise AssertionError("Setup must not mutate acquisition, name or saving")

    monkeypatch.setattr(client_module, "with_sdk", forbid_mutation)
    if not running or saving:
        with pytest.raises(RuntimeError, match="acquiring with saving OFF"):
            await client.prepare(
                pb.ExperimentConfiguration(), pb.SessionContext(), "managed_run"
            )
    else:
        prepared = await client.prepare(
            pb.ExperimentConfiguration(), pb.SessionContext(), "managed_run"
        )
        assert prepared.run_name == "managed_run"
        assert prepared.spikeglx_version == "observed-version"
        assert prepared.sdk_version == "unknown"
        assert client._acquisition_run_name == "insertion"
        assert await client.verify_before_start()
    client.io_owner.close(wait=True)


@pytest.mark.asyncio
async def test_late_sample_reply_cannot_pass_writing_gate() -> None:
    now = [100]
    client = SpikeGLXControllerClient(
        Path("."), controller_generation="test", clock=lambda: now[0]
    )
    settings = HostSettings("127.0.0.1", 4142, 1.0, 1.0, 0.1, 0.5, 1.0, {}, {})
    result = (
        Readback(
            "v", "dir", True, True, "run", (), "digest", "immediate", "immediate", ()
        ),
        (),
    )

    class LateOwner:
        async def run(self, operation: object, timeout_s: float) -> object:
            del operation, timeout_s
            now[0] = 200
            return result

    client.io_owner = LateOwner()  # type: ignore[assignment]

    with pytest.raises(TimeoutError, match="missed its deadline"):
        await client._sample_counts(settings, deadline_ns=150)


@pytest.mark.asyncio
async def test_writing_gate_rejects_changed_data_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [100]
    client = SpikeGLXControllerClient(
        Path("."), controller_generation="test", clock=lambda: now[0]
    )
    settings = HostSettings("127.0.0.1", 4142, 1, 1, 0.1, 1, 0.5, (), {})
    expected = wire.SpikeGLXPreparation(
        run_name="managed",
        data_directory="D:/expected",
        streams=(
            wire.NativeStream(
                family=wire.STREAM_FAMILY_NI,
                index=0,
                saved_channel_indices=(0,),
            ),
        ),
    )
    client._prepared_settings = settings
    client._prepared = expected
    progress_readback = Readback(
        "v",
        "D:/changed",
        True,
        True,
        "managed",
        (),
        "digest",
        "immediate",
        "immediate",
        (),
    )

    class FakeProgress:
        async def sample_counts(
            self, deadline_ns: int
        ) -> tuple[Readback, tuple[tuple[int, int, int], ...]]:
            del deadline_ns
            return progress_readback, ((1, 0, 1),)

    client._progress_io = FakeProgress()  # type: ignore[assignment]
    monkeypatch.setattr(client_module, "load_host_settings", lambda _root: settings)

    async def verify(*_args: object) -> bool:
        return True

    def with_start(_root: Path, _settings: HostSettings, operation: object) -> object:
        class SDK:
            @staticmethod
            def c_sglx_setRunName(_handle: int, _name: bytes) -> bool:
                return True

            @staticmethod
            def c_sglx_setRecordingEnable(_handle: int, _enable: bool) -> bool:
                return True

        return operation(SDK(), 1)  # type: ignore[operator]

    async def immediate(operation: object, timeout_s: float) -> object:
        del timeout_s
        return operation()  # type: ignore[operator]

    async def finish_sleep(seconds: float) -> None:
        now[0] += max(1, int(seconds * 1e9))

    monkeypatch.setattr(client, "_verify_before_start", verify)
    monkeypatch.setattr(client_module, "with_sdk", with_start)
    monkeypatch.setattr(client, "_run", immediate)
    client._sleep = finish_sleep
    assert not await client.start_and_verify_writing(deadline_ns=1_000_000)


@pytest.mark.asyncio
async def test_stop_uses_setup_endpoint_after_host_file_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SpikeGLXControllerClient(
        Path("."), controller_generation="test", clock=lambda: 100
    )
    prepared_settings = HostSettings("10.0.0.1", 4142, 1.0, 1.0, 0.1, 0.5, 1.0, {}, {})
    changed_settings = HostSettings("10.0.0.2", 4143, 1.0, 1.0, 0.1, 0.5, 1.0, {}, {})
    client._prepared_settings = prepared_settings
    client._prepared = wire.SpikeGLXPreparation(
        run_name="managed_run", data_directory="D:/data"
    )
    calls: list[HostSettings] = []
    client._recording_requested = True
    readbacks = iter((True, False))

    def read_sdk(root: Path, settings: HostSettings) -> Readback:
        del root
        calls.append(settings)
        return Readback(
            "v",
            "D:/data",
            True,
            next(readbacks),
            "managed_run",
            (),
            "digest",
            "immediate",
            "immediate",
            (),
        )

    class FakeSDK:
        @staticmethod
        def c_sglx_setRecordingEnable(handle: int, enable: bool) -> bool:
            assert not enable
            del handle
            return True

    def with_sdk(root: Path, settings: HostSettings, operation: object) -> object:
        del root
        calls.append(settings)
        return operation(FakeSDK(), 1)  # type: ignore[operator]

    async def immediate(operation: object, timeout_s: float) -> object:
        del timeout_s
        if callable(operation):
            return operation()
        raise AssertionError("expected native operation")

    monkeypatch.setattr(client_module, "read_sdk", read_sdk)
    monkeypatch.setattr(client_module, "with_sdk", with_sdk)
    monkeypatch.setattr(
        client_module, "load_host_settings", lambda _root: changed_settings
    )
    monkeypatch.setattr(client, "_run", immediate)

    assert await client.stop_expected_run(deadline_ns=10_000)
    assert calls and all(item.address == "10.0.0.1" for item in calls)
    assert all(item.port == 4142 for item in calls)


@pytest.mark.asyncio
async def test_prestart_rejects_stream_drift_outside_parameter_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = HostSettings("10.0.0.1", 4142, 1.0, 1.0, 0.1, 0.5, 1.0, {}, {})
    original_stream = wire.NativeStream(
        family=wire.STREAM_FAMILY_NI,
        index=0,
        sample_rate_hz=1000.0,
        acquired_channel_counts=(1, 2),
        saved_channel_indices=(1,),
    )
    changed_stream = wire.NativeStream.FromString(original_stream.SerializeToString())
    changed_stream.sample_rate_hz = 500.0
    client = SpikeGLXControllerClient(
        Path("."), controller_generation="test", clock=lambda: 100
    )
    client._prepared_settings = settings
    client._prepared = wire.SpikeGLXPreparation(
        run_name="managed_run",
        data_directory="D:/data",
        gate_mode="immediate",
        trigger_mode="immediate",
        streams=(original_stream,),
    )
    client._params_digest = "same-params"

    monkeypatch.setattr(client_module, "load_host_settings", lambda _root: settings)
    monkeypatch.setattr(
        client_module,
        "read_sdk",
        lambda _root, _settings: Readback(
            "v",
            "D:/data",
            False,
            False,
            "managed_run",
            (changed_stream,),
            "same-params",
            "immediate",
            "immediate",
            (),
        ),
    )

    async def immediate(operation: object, timeout_s: float) -> object:
        del timeout_s
        return operation()  # type: ignore[operator]

    monkeypatch.setattr(client, "_run", immediate)
    assert not await client.verify_before_start(deadline_ns=1_000)


def test_inventory_file_update_is_digest_guarded_and_preserves_other_settings(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[2]
    target = tmp_path / "config/backends/synchronization_config.toml"
    target.parent.mkdir(parents=True)
    target.write_text(_unmapped_host_configuration(repository))
    mapping_source = repository / "contracts/spikeglx_mapping_reference.json"
    mapping_target = tmp_path / "contracts/spikeglx_mapping_reference.json"
    mapping_target.parent.mkdir(parents=True)
    shutil.copyfile(mapping_source, mapping_target)
    root = tmp_path
    digest, empty = read_inventory(root)
    assert not empty
    channels = (
        wire.PulseChannel(
            role=wire.PULSE_ROLE_BEHAVIORAL_CAMERA,
            family=wire.STREAM_FAMILY_ONEBOX,
            stream_index=0,
            channel_index=1,
            bit=0,
        ),
        wire.PulseChannel(
            role=wire.PULSE_ROLE_TRACKING_CAMERA,
            family=wire.STREAM_FAMILY_ONEBOX,
            stream_index=0,
            channel_index=2,
        ),
        wire.PulseChannel(
            role=wire.PULSE_ROLE_PHOTODIODE,
            family=wire.STREAM_FAMILY_NI,
            stream_index=0,
            channel_index=4,
        ),
    )
    channels += (
        wire.PulseChannel(
            role=wire.PULSE_ROLE_EYE_TRACKING_CAMERA,
            family=wire.STREAM_FAMILY_ONEBOX,
            stream_index=0,
            channel_index=1,
            bit=1,
        ),
    )
    changed = update_inventory(
        root, expected_file_sha256=digest, pulse_channels=channels
    )
    assert changed != digest
    contents = target.read_text()
    assert "# E12: alignment role" in contents
    assert (
        'behavioral_camera = { stream = "onebox", stream_index = 0, channel = 1, bit = 0 }'
        in contents
    )
    assert "stop_margin_s = 1" in contents
    loaded_digest, loaded = read_inventory(root)
    assert loaded == channels
    assert loaded_digest == changed
    assert loaded[0].HasField("bit") and loaded[0].bit == 0
    assert not loaded[1].HasField("bit")
    with pytest.raises(ValueError, match="changed since inventory was read"):
        update_inventory(root, expected_file_sha256=digest, pulse_channels=channels)
    with pytest.raises(ValueError, match="source-mapped digital word"):
        update_inventory(
            root,
            expected_file_sha256=changed,
            pulse_channels=(
                wire.PulseChannel(
                    role=wire.PULSE_ROLE_BEHAVIORAL_CAMERA,
                    family=wire.STREAM_FAMILY_ONEBOX,
                    stream_index=0,
                    channel_index=1,
                    bit=16,
                ),
                *channels[1:],
            ),
        )

    empty_digest = update_inventory(
        root, expected_file_sha256=changed, pulse_channels=()
    )
    after_clear_digest, after_clear = read_inventory(root)
    assert after_clear_digest == empty_digest
    assert after_clear == ()


@pytest.mark.parametrize(
    "key, role",
    [
        ("behavioral_camera", wire.PULSE_ROLE_BEHAVIORAL_CAMERA),
        ("eye_tracking_camera", wire.PULSE_ROLE_EYE_TRACKING_CAMERA),
    ],
)
def test_inventory_update_preserves_valid_nested_table_comments(
    tmp_path: Path, key: str, role: int
) -> None:
    repository = Path(__file__).resolve().parents[2]
    config = tmp_path / "config/backends/synchronization_config.toml"
    config.parent.mkdir(parents=True)
    text = _unmapped_host_configuration(repository)
    text = text.replace(
        "[monitor]",
        f"""[pulse_inventory.{key}]
# Keep this operator note while changing the row.
stream = "onebox"
stream_index = 0
channel = 1
bit = 0

[monitor]""",
    )
    config.write_text(text)
    mapping = tmp_path / "contracts/spikeglx_mapping_reference.json"
    mapping.parent.mkdir(parents=True)
    shutil.copyfile(repository / "contracts/spikeglx_mapping_reference.json", mapping)
    digest, _ = read_inventory(tmp_path)
    updated = update_inventory(
        tmp_path,
        expected_file_sha256=digest,
        pulse_channels=(
            wire.PulseChannel(
                role=role,
                family=wire.STREAM_FAMILY_ONEBOX,
                stream_index=0,
                channel_index=3,
            ),
        ),
    )
    saved = config.read_text()
    assert "# Keep this operator note" in saved
    assert "channel = 3" in saved
    assert "bit = 0" not in saved
    assert "stop_margin_s = 1" in saved
    _, channels = read_inventory(tmp_path)
    assert channels[0].channel_index == 3
    assert not channels[0].HasField("bit")
    assert updated != digest


def test_inventory_delete_then_insert_custom_stays_in_pulse_table(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[2]
    config = tmp_path / "config/backends/synchronization_config.toml"
    config.parent.mkdir(parents=True)
    text = _unmapped_host_configuration(repository)
    text = text.replace(
        "[monitor]",
        """[pulse_inventory.behavioral_camera]
stream = "onebox"
stream_index = 0
channel = 1

[monitor]""",
    )
    config.write_text(text)
    mapping = tmp_path / "contracts/spikeglx_mapping_reference.json"
    mapping.parent.mkdir(parents=True)
    shutil.copyfile(repository / "contracts/spikeglx_mapping_reference.json", mapping)
    digest, _ = read_inventory(tmp_path)
    proposal = (
        wire.PulseChannel(
            role=wire.PULSE_ROLE_CUSTOM,
            family=wire.STREAM_FAMILY_NI,
            stream_index=0,
            channel_index=4,
            source_id="custom-input",
        ),
    )
    update_inventory(tmp_path, expected_file_sha256=digest, pulse_channels=proposal)
    saved = config.read_text()
    parsed = tomllib.loads(saved)
    assert parsed["pulse_inventory"] == {
        "custom_custom-input": {
            "stream": "ni",
            "stream_index": 0,
            "channel": 4,
            "source_id": "custom-input",
        }
    }
    assert parsed["monitor"]["stop_margin_s"] == 1
    assert "custom_custom-input" not in saved.split("[monitor]", 1)[1]
    assert "pulse_inventory.behavioral_camera" not in parsed


@pytest.mark.parametrize("value", ["nan", "inf", "+inf", "-inf"])
def test_host_monitor_budgets_reject_nonfinite_values(
    tmp_path: Path, value: str
) -> None:
    repository = Path(__file__).resolve().parents[2]
    config = tmp_path / "config/backends/synchronization_config.toml"
    config.parent.mkdir(parents=True)
    text = _unmapped_host_configuration(repository)
    config.write_text(
        text.replace("no_progress_timeout_s = 10", f"no_progress_timeout_s = {value}")
    )
    mapping = tmp_path / "contracts/spikeglx_mapping_reference.json"
    mapping.parent.mkdir(parents=True)
    shutil.copyfile(repository / "contracts/spikeglx_mapping_reference.json", mapping)
    with pytest.raises(ValueError, match="no_progress_timeout_s is invalid"):
        load_host_settings(tmp_path)


@pytest.mark.asyncio
async def test_monitor_publishes_known_not_saving_state_without_sample_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cephvr.synchronization import monitor as monitor_module

    settings = HostSettings("127.0.0.1", 4142, 1, 1, 0.1, 1, 0.5, (), {})
    expected = wire.SpikeGLXPreparation(
        run_name="managed",
        data_directory="D:/data",
        streams=(
            wire.NativeStream(
                family=wire.STREAM_FAMILY_NI, index=0, saved_channel_indices=(1,)
            ),
        ),
    )
    readback = Readback(
        "version",
        "D:/data",
        True,
        False,
        "managed",
        (),
        "digest",
        "immediate",
        "immediate",
        (),
    )
    monkeypatch.setattr(monitor_module, "read_sdk", lambda *_args: readback)

    class ImmediateOwner:
        async def run(self, operation: object, timeout_s: float) -> object:
            del timeout_s
            return operation()  # type: ignore[operator]

    monitor = SpikeGLXProgressIO(
        software_root=Path("."),
        settings=settings,
        expected=expected,
        io_owner=ImmediateOwner(),  # type: ignore[arg-type]
        clock=lambda: 100,
    )
    view = await monitor.observe(deadline_ns=200)
    assert view.HasField("observed_monotonic_ns")
    assert view.HasField("running") and view.running
    assert view.HasField("saving") and not view.saving
    assert view.phase == wire.SPIKEGLX_RECORDING_PHASE_UNKNOWN
    assert not view.progress


@pytest.mark.asyncio
async def test_inventory_controller_binds_lease_revision_and_file_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).resolve().parents[2]
    config = tmp_path / "config/backends/synchronization_config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(_unmapped_host_configuration(repository))
    mapping = tmp_path / "contracts/spikeglx_mapping_reference.json"
    mapping.parent.mkdir(parents=True)
    shutil.copyfile(repository / "contracts/spikeglx_mapping_reference.json", mapping)

    class Operations:
        def __init__(self) -> None:
            self.control = SimpleNamespace(operations={})

        def authorized(self, command: svc.OperatorCommand) -> str:
            return "" if command.operator.client_id == "operator" else "lease mismatch"

        @staticmethod
        def admission(command_id: str, *, error: str = "") -> pb.CommandAdmission:
            return pb.CommandAdmission(
                command_id=command_id,
                result=(
                    pb.COMMAND_RESULT_REJECTED if error else pb.COMMAND_RESULT_ACCEPTED
                ),
                **(
                    {"failure": pb.Failure(code="REJECTED", message=error)}
                    if error
                    else {}
                ),
            )

        def operation(
            self, command_id: str, name: str, **kwargs: object
        ) -> pb.OperationState:
            state = pb.OperationState(
                context=pb.OperationContext(command_id=command_id),
                command=name,
                progress=str(kwargs.get("progress", "accepted")),
            )
            self.control.operations[command_id] = state
            return state

        def complete_operation(self, command_id: str, **kwargs: object) -> None:
            state = self.control.operations[command_id]
            state.complete = True
            state.succeeded = bool(kwargs["success"])
            state.progress = str(kwargs["progress"])
            if kwargs.get("error"):
                state.failure.CopyFrom(pb.Failure(message=str(kwargs["error"])))

    operations = Operations()

    configuration = ConfigurationState(
        pb.ExperimentConfiguration(), pb.ControlPolicies()
    )
    configuration.current.backends.add(
        backend_name="visual_stimulus", enabled=True
    ).visual_stimulus.display.profile_json = '{"photodiode_enabled": true}'
    configuration.current.backends.add(backend_name="synchronization", enabled=True)
    lifecycle = LifecycleState()
    inventory = SpikeGLXInventory(
        software_root=tmp_path,
        lifecycle=lifecycle,
        configuration=configuration,
        operations=operations,  # type: ignore[arg-type]
        limits=SimpleNamespace(current=SimpleNamespace(validation_ns=1_000_000_000)),  # type: ignore[arg-type]
        publish=lambda: None,
    )
    command = svc.OperatorCommand(
        controller_generation="be848407-e044-45cc-98ed-8908777f9dc5",
        operator=pb.OperatorContext(
            client_id="operator",
            control_generation="control-generation",
            command_id="inventory-read",
        ),
    )
    snapshot, error = await inventory.read(
        svc.SpikeGLXInventoryRequest(
            command=command, expected_configuration_revision=configuration.revision
        )
    )
    assert not error and snapshot is not None
    expected_host = load_host_settings(tmp_path)
    assert snapshot.backend_enabled
    assert snapshot.address == expected_host.address
    assert snapshot.command_port == expected_host.port
    update = svc.SpikeGLXInventoryUpdateRequest(
        command=command,
        expected_configuration_revision=configuration.revision,
        expected_file_sha256=snapshot.file_sha256,
        pulse_channels=(
            wire.PulseChannel(
                role=wire.PULSE_ROLE_BEHAVIORAL_CAMERA,
                family=wire.STREAM_FAMILY_ONEBOX,
                stream_index=0,
                channel_index=3,
                bit=0,
            ),
            wire.PulseChannel(
                role=wire.PULSE_ROLE_PHOTODIODE,
                family=wire.STREAM_FAMILY_NI,
                stream_index=0,
                channel_index=4,
            ),
        ),
    )
    omitted_required = svc.SpikeGLXInventoryUpdateRequest.FromString(
        update.SerializeToString()
    )
    del omitted_required.pulse_channels[-1]
    rejected = await inventory.update(omitted_required)
    assert rejected.result == pb.COMMAND_RESULT_REJECTED
    assert "required active roles" in rejected.failure.message
    accepted = await inventory.update(update)
    assert accepted.result == pb.COMMAND_RESULT_ACCEPTED
    current, error = await inventory.read(
        svc.SpikeGLXInventoryRequest(
            command=command, expected_configuration_revision=configuration.revision
        )
    )
    assert not error and current is not None
    assert current.file_sha256 != snapshot.file_sha256
    assert current.pulse_channels[0].channel_index == 3

    from cephvr.controller.device import spikeglx_inventory as inventory_owner_module
    from cephvr.synchronization import inventory as inventory_module

    write_calls = 0
    write_inventory = inventory_module.update_inventory

    def count_write(*args: object, **kwargs: object) -> str:
        nonlocal write_calls
        write_calls += 1
        return write_inventory(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(inventory_owner_module, "update_inventory", count_write)
    mapping_entered, mapping_release = threading.Event(), threading.Event()
    load_mapping = inventory_owner_module._mapping

    def delayed_mapping(root: Path):
        mapping_entered.set()
        if not mapping_release.wait(2):
            raise TimeoutError("test mapping release was not signaled")
        return load_mapping(root)

    monkeypatch.setattr(inventory_owner_module, "_mapping", delayed_mapping)
    preflight_command = svc.OperatorCommand.FromString(command.SerializeToString())
    preflight_command.operator.command_id = "inventory-preflight"
    preflight_update = svc.SpikeGLXInventoryUpdateRequest(
        command=preflight_command,
        expected_configuration_revision=configuration.revision,
        expected_file_sha256=current.file_sha256,
        pulse_channels=tuple(current.pulse_channels),
    )
    preflight_result = asyncio.create_task(inventory.update(preflight_update))
    assert await asyncio.to_thread(mapping_entered.wait, 1)
    await asyncio.wait_for(lifecycle.lock.acquire(), 0.1)
    configuration.revision += 1
    lifecycle.lock.release()
    mapping_release.set()
    preflight_rejected = await preflight_result
    assert preflight_rejected.result == pb.COMMAND_RESULT_REJECTED
    assert "revision" in preflight_rejected.failure.message
    assert write_calls == 0
    monkeypatch.setattr(inventory_owner_module, "_mapping", load_mapping)
    current, error = await inventory.read(
        svc.SpikeGLXInventoryRequest(
            command=command, expected_configuration_revision=configuration.revision
        )
    )
    assert not error and current is not None
    update.expected_configuration_revision = configuration.revision

    entered, release = threading.Event(), threading.Event()

    def delayed_write(*args: object, **kwargs: object) -> str:
        nonlocal write_calls
        write_calls += 1
        entered.set()
        if not release.wait(2):
            raise TimeoutError("test write release was not signaled")
        return write_inventory(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(inventory_owner_module, "update_inventory", delayed_write)
    inventory.limits.current.validation_ns = 20_000_000
    inventory_clock = [inventory.clock()]
    inventory.clock = lambda: inventory_clock[0]
    late_command = svc.OperatorCommand.FromString(command.SerializeToString())
    late_command.operator.command_id = "inventory-late"
    late_update = svc.SpikeGLXInventoryUpdateRequest(
        command=late_command,
        expected_configuration_revision=configuration.revision,
        expected_file_sha256=current.file_sha256,
        pulse_channels=tuple(current.pulse_channels),
    )
    late_result = asyncio.create_task(inventory.update(late_update))
    assert await asyncio.to_thread(entered.wait, 1)
    acquired = await asyncio.wait_for(lifecycle.lock.acquire(), 0.1)
    assert acquired
    lifecycle.lock.release()
    assert lifecycle.inventory_update_pending
    timed_out = await late_result
    assert timed_out.result == pb.COMMAND_RESULT_ACCEPTED
    operation = operations.control.operations["inventory-late"]
    assert not operation.complete
    assert "unconfirmed" in operation.progress
    inventory_clock[0] += inventory.limits.current.validation_ns
    release.set()
    stop = asyncio.get_running_loop().time() + 2
    while (
        lifecycle.inventory_update_pending and asyncio.get_running_loop().time() < stop
    ):
        await asyncio.sleep(0.005)
    assert not lifecycle.inventory_update_pending
    assert operation.complete and operation.succeeded
    assert operation.progress == "inventory committed after deadline"

    stale = await inventory.update(update)
    assert stale.result == pb.COMMAND_RESULT_REJECTED
    assert "changed since inventory was read" in stale.failure.message
    lifecycle.session.phase = pb.SESSION_PHASE_READY
    ready_snapshot, error = await inventory.read(
        svc.SpikeGLXInventoryRequest(
            command=command, expected_configuration_revision=configuration.revision
        )
    )
    assert not error and ready_snapshot is not None
    ready_update = svc.SpikeGLXInventoryUpdateRequest(
        command=command,
        expected_configuration_revision=configuration.revision,
        expected_file_sha256=ready_snapshot.file_sha256,
        pulse_channels=(),
    )
    blocked = await inventory.update(ready_update)
    assert blocked.result == pb.COMMAND_RESULT_REJECTED
    assert "session phase" in blocked.failure.message
    _, error = await inventory.read(
        svc.SpikeGLXInventoryRequest(
            command=command,
            expected_configuration_revision=configuration.revision + 1,
        )
    )
    assert error == "configuration revision mismatch"
    command.operator.client_id = "other"
    _, error = await inventory.read(
        svc.SpikeGLXInventoryRequest(
            command=command, expected_configuration_revision=configuration.revision
        )
    )
    assert error == "lease mismatch"


@pytest.mark.asyncio
async def test_timed_out_sdk_call_keeps_ownership_until_native_return() -> None:
    owner = SpikeGLXIOOwner()
    entered, release = threading.Event(), threading.Event()

    def blocked() -> str:
        entered.set()
        release.wait(2)
        return "complete"

    first = asyncio.create_task(owner.run(blocked, 0.02))
    assert await asyncio.to_thread(entered.wait, 1)
    with pytest.raises(TimeoutError, match="SDK operation exceeded 0.02s"):
        await first
    with pytest.raises(SpikeGLXIOBusy):
        await owner.run(lambda: "must not run", 1)

    release.set()
    await asyncio.sleep(0.02)
    assert await owner.run(lambda: "next", 1) == "next"
    owner.close(wait=True)


@pytest.mark.asyncio
async def test_late_sdk_exception_is_consumed_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    owner = SpikeGLXIOOwner()
    entered, release = threading.Event(), threading.Event()

    def fail_late() -> str:
        entered.set()
        release.wait(2)
        raise RuntimeError("late SDK diagnostic")

    call = asyncio.create_task(owner.run(fail_late, 0.02))
    assert await asyncio.to_thread(entered.wait, 1)
    with pytest.raises(TimeoutError):
        await call
    with pytest.raises(SpikeGLXIOBusy):
        await owner.run(lambda: "must not run", 1)
    release.set()
    async with asyncio.timeout(1):
        while True:
            try:
                assert await owner.run(lambda: "next", 1) == "next"
                break
            except SpikeGLXIOBusy:
                await asyncio.sleep(0.005)
    assert "failed after its caller stopped waiting: late SDK diagnostic" in caplog.text
    owner.close(wait=True)


@pytest.mark.asyncio
async def test_cancelled_sdk_caller_keeps_native_ownership_and_late_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    owner = SpikeGLXIOOwner()
    entered, release = threading.Event(), threading.Event()

    def fail_late() -> str:
        entered.set()
        release.wait(2)
        raise RuntimeError("cancelled-call diagnostic")

    call = asyncio.create_task(owner.run(fail_late, 5))
    assert await asyncio.to_thread(entered.wait, 1)
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    with pytest.raises(SpikeGLXIOBusy):
        await owner.run(lambda: "must not run", 1)
    release.set()
    async with asyncio.timeout(1):
        while True:
            try:
                assert await owner.run(lambda: "next", 1) == "next"
                break
            except SpikeGLXIOBusy:
                await asyncio.sleep(0.005)
    assert (
        "failed after its caller stopped waiting: cancelled-call diagnostic"
        in caplog.text
    )
    owner.close(wait=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "unsaved",
        "wrong_family",
        "valid",
        "disabled",
        "free_running",
        "backend_disabled",
    ],
)
async def test_eye_mapping_setup_and_saved_preparation(
    case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from cephvr.acquisition.v1 import camera_pb2
    from cephvr.controller.metadata.documents import message_dict

    configuration = pb.ExperimentConfiguration()
    backend = configuration.backends.add(
        backend_name="acquisition", enabled=case != "backend_disabled"
    )
    eye = backend.acquisition.eye_tracking
    eye.enabled = case != "disabled"
    eye.device.frame_timing = (
        camera_pb2.FRAME_TIMING_FREE_RUNNING
        if case == "free_running"
        else camera_pb2.FRAME_TIMING_EXTERNAL_TRIGGER
    )
    channel = wire.PulseChannel(
        role=wire.PULSE_ROLE_EYE_TRACKING_CAMERA,
        family=wire.STREAM_FAMILY_NI
        if case == "wrong_family"
        else wire.STREAM_FAMILY_ONEBOX,
        stream_index=0,
        channel_index=1,
        bit=0,
    )
    inventory = (
        ()
        if case in {"missing", "disabled", "free_running", "backend_disabled"}
        else (channel,)
    )
    stream = wire.NativeStream(
        family=wire.STREAM_FAMILY_ONEBOX,
        index=0,
        acquired_channel_counts=(1, 1, 0),
        saved_channel_indices=() if case == "unsaved" else (1,),
    )
    settings = replace(
        load_host_settings(Path(__file__).resolve().parents[2]), inventory=inventory
    )
    monkeypatch.setattr(client_module, "load_host_settings", lambda _root: settings)
    run_name = "old"

    def readback(_root: Path, _settings: HostSettings) -> Readback:
        return Readback(
            "v",
            "D:/data",
            True,
            False,
            run_name,
            (stream,),
            "params",
            "immediate",
            "immediate",
            (),
        )

    monkeypatch.setattr(client_module, "read_sdk", readback)

    class SDK:
        @staticmethod
        def c_sglx_setRunName(handle: int, name: bytes) -> bool:
            nonlocal run_name
            run_name = name.decode()
            return True

    monkeypatch.setattr(
        client_module,
        "with_sdk",
        lambda _root, _settings, operation: operation(SDK(), 1),
    )
    client = SpikeGLXControllerClient(Path("."), controller_generation="test")

    async def immediate(operation: object, timeout_s: float) -> object:
        return operation()  # type: ignore[operator]

    monkeypatch.setattr(client, "_run", immediate)
    errors = {
        "missing": "missing required active roles.*EYE_TRACKING_CAMERA",
        "unsaved": "channel is not saved",
        "wrong_family": "OneBox",
    }
    if case in errors:
        with pytest.raises(ValueError, match=errors[case]):
            await client.prepare(configuration, pb.SessionContext(), "managed_run")
        assert run_name == "old"
    else:
        prepared = await client.prepare(
            configuration, pb.SessionContext(), "managed_run"
        )
        assert tuple(prepared.pulse_channels) == inventory
        if case == "valid":
            assert (
                message_dict(prepared)["pulse_channels"][0]["role"]
                == "PULSE_ROLE_EYE_TRACKING_CAMERA"
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "already_saving",
        "stopped",
        "foreign_name",
        "foreign_directory",
        "enable_timeout",
        "name_timeout",
        "saving_after_rename",
        "changed_before_stop",
    ],
)
async def test_saving_only_lifecycle_preserves_acquisition_and_foreign_recordings(
    monkeypatch, fault
):
    settings = HostSettings(
        "10.0.0.1", 4142, 1, 1, 0.01, 0.5, 0, (), {"mapping_id": "source-reviewed"}
    )
    state = SimpleNamespace(
        running=True, saving=False, name="insertion", directory="D:/data", count=1000
    )
    stream = wire.NativeStream(
        family=wire.STREAM_FAMILY_ONEBOX, index=0, saved_channel_indices=(0, 1)
    )
    calls = []

    def read(*args):
        return Readback(
            "observed",
            state.directory,
            state.running,
            state.saving,
            state.name,
            (stream,),
            "params",
            "immediate",
            "immediate",
            (),
        )

    class SDK:
        @staticmethod
        def c_sglx_setRunName(handle, name):
            assert state.running and not state.saving
            calls.append(("name", name.decode()))
            state.name = name.decode()
            if fault == "name_timeout":
                raise TimeoutError("rename outcome unknown")
            if fault == "saving_after_rename":
                state.saving = True
            return True

        @staticmethod
        def c_sglx_setRecordingEnable(handle, enable):
            assert state.running
            calls.append(("saving", enable))
            state.saving = enable
            if fault == "enable_timeout" and enable:
                raise TimeoutError("enable saving outcome unknown")
            return True

    monkeypatch.setattr(client_module, "load_host_settings", lambda root: settings)
    monkeypatch.setattr(client_module, "read_sdk", read)
    monkeypatch.setattr(
        client_module, "with_sdk", lambda root, settings, operation: operation(SDK(), 1)
    )

    async def sample(self, deadline):
        state.count += 10
        return read(), ((1, 0, state.count),)

    monkeypatch.setattr(SpikeGLXProgressIO, "sample_counts", sample)
    client = SpikeGLXControllerClient(Path("."), controller_generation="test")
    try:
        await client.prepare(
            pb.ExperimentConfiguration(), pb.SessionContext(), "session1"
        )
        assert not calls and state.name == "insertion" and state.running
        if fault == "already_saving":
            state.saving = True
        if fault == "stopped":
            state.running = False
        if fault == "foreign_name":
            state.name = "other"
        if fault == "foreign_directory":
            state.directory = "D:/other"
        started = await client.start_and_verify_writing()
        if fault in {"already_saving", "stopped", "foreign_name", "foreign_directory"}:
            assert not started and not calls
            if state.saving:
                assert not await client.stop_expected_run()
            else:
                assert await client.stop_expected_run()
            assert not calls
            return
        if fault in {"name_timeout", "saving_after_rename"}:
            assert not started and calls == [("name", "session1")]
            assert await client.stop_expected_run() is (fault == "name_timeout")
            assert calls == [("name", "session1")]
            assert state.running
            return
        assert started is (fault != "enable_timeout")
        assert calls == [("name", "session1"), ("saving", True)]
        if fault == "changed_before_stop":
            state.name = "other"
            assert not await client.stop_expected_run()
            assert state.saving and state.running and len(calls) == 2
            return
        assert await client.stop_expected_run()
        assert not state.saving and state.running
        assert calls[-1] == ("saving", False)
        if fault == "none":
            baseline = state.count
            await client.prepare(
                pb.ExperimentConfiguration(), pb.SessionContext(), "session2"
            )
            assert state.name == "session1" and state.running and not state.saving
            assert await client.start_and_verify_writing()
            assert (
                state.count > baseline
                and client.monitor_baseline()[0].sample_count > baseline
            )
            assert await client.stop_expected_run()
            assert state.running and not state.saving
    finally:
        client.io_owner.close(wait=True)
