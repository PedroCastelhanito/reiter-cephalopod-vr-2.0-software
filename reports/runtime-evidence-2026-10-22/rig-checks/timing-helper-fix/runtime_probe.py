"""Disposable bounded timing/GC probe; never changes scheduling or GC policy."""
import collections
import gc
import json
import threading
import time
from pathlib import Path


class Probe:
    def __init__(self, engine):
        self.engine = engine
        self.events = collections.deque(maxlen=4096)
        self.windows = collections.deque(maxlen=32)
        self.pending = collections.deque(maxlen=8)
        self.stages = {}
        self.restorers = []
        self.gc_starts = {}
        self.gc_callback = self.gc_event
        gc.callbacks.append(self.gc_callback)

    def active(self):
        return bool(self.engine._trial_id and not self.engine._stopped)

    def record(self, stage, start, end, cpu, trial, group, extra=None):
        event = {"stage": stage, "thread": threading.get_ident(),
                 "start_ns": start, "end_ns": end, "cpu_ns": cpu,
                 "trial": trial, "group": group}
        if extra:
            event.update(extra)
        self.events.append(event)
        values = self.stages.setdefault(stage, {"count": 0, "total_ns": 0, "max_ns": 0, "max_event": None})
        values["count"] += 1
        values["total_ns"] += end - start
        if end - start > values["max_ns"]:
            values["max_ns"] = end - start
            values["max_event"] = event
        for window in tuple(self.pending):
            window["after"].append(event)
            if len(window["after"]) == 128:
                self.pending.remove(window)
        if end - start > 25_000_000:
            window = {"slow": event, "before": list(self.events)[-128:], "after": []}
            self.windows.append(window)
            self.pending.append(window)

    def gc_event(self, phase, info):
        ident = threading.get_ident()
        if phase == "start":
            if self.active() and len(self.gc_starts) < 8:
                self.gc_starts[ident] = (time.perf_counter_ns(), time.thread_time_ns(), self.engine._trial_id, self.engine._group_id)
        elif ident in self.gc_starts:
            start, cpu, trial, group = self.gc_starts.pop(ident)
            self.record("gc", start, time.perf_counter_ns(), time.thread_time_ns() - cpu,
                        trial, group, dict(info))

    def timed(self, original, stage):
        def call(*args, **kwargs):
            if not self.active():
                return original(*args, **kwargs)
            start, cpu = time.perf_counter_ns(), time.thread_time_ns()
            trial, group = self.engine._trial_id, self.engine._group_id
            try:
                return original(*args, **kwargs)
            finally:
                self.record(stage, start, time.perf_counter_ns(), time.thread_time_ns() - cpu,
                            trial, group,
                            {"sync": bool(kwargs.get("sync", False))} if stage == "evidence.write_pending" else None)
        return call

    def wrap(self, obj, name, stage):
        original = getattr(obj, name)
        own = name in obj.__dict__
        raw = obj.__dict__.get(name)
        wrapped = self.timed(original, stage)
        if isinstance(raw, staticmethod):
            wrapped = staticmethod(wrapped)
        setattr(obj, name, wrapped)
        self.restorers.append((obj, name, own, raw))

    def restore(self):
        if self.gc_callback in gc.callbacks:
            gc.callbacks.remove(self.gc_callback)
        for obj, name, own, raw in reversed(self.restorers):
            if own:
                setattr(obj, name, raw)
            else:
                delattr(obj, name)
        self.restorers.clear()

    def flush(self):
        path = Path(__file__).with_name("probe-results.json")
        path.write_text(json.dumps({"diagnostic_perturbed": True,
            "group_semantics": "Observed current GL group at wrapper entry; recording stages correlate by time, not encoded-group identity",
            "limits": {"events": 4096, "windows": 32, "before_after": 128, "pending": 8},
            "stages": self.stages, "windows": list(self.windows), "tail": list(self.events)}, indent=2), encoding="utf-8")


def install(driver, port, recording):
    from cephvr.visual_stimulus.recording.evidence import EvidenceWriter
    from cephvr.visual_stimulus.recording.encoder_owner import EncoderTrialOwner
    from cephvr.visual_stimulus.rendering.image_residency import ImageResidency
    from cephvr.visual_stimulus.rendering.scene import ModernGLSceneRenderer

    probe = Probe(driver.engine)
    for name in ("render_tick", "_scene_state", "poll_diagnostics"):
        probe.wrap(driver.engine, name, "engine." + name)
    for name in ("before_render", "rendered", "diagnostics"):
        probe.wrap(recording, name, "recording." + name)
    for name in ("render", "present", "select_images", "capture_review_composite", "poll_review_capture"):
        probe.wrap(port, name, "port." + name)
    probe.wrap(ImageResidency, "service", "residency.service")
    probe.wrap(ModernGLSceneRenderer, "render_group", "scene.render_group")
    probe.wrap(EvidenceWriter, "_encode", "evidence.encode")
    probe.wrap(EvidenceWriter, "write_pending", "evidence.write_pending")
    probe.wrap(EncoderTrialOwner, "periodic_sync", "encoder.periodic_sync")
    cleanup = driver.cleanup
    def finish(*args, **kwargs):
        try:
            return cleanup(*args, **kwargs)
        finally:
            for diagnostic in (probe.restore, probe.flush):
                try:
                    diagnostic()
                except BaseException as error:
                    try:
                        import sys
                        print(f"timing probe diagnostic failure: {error!r}", file=sys.stderr)
                    except BaseException:
                        pass
    probe.restorers.append((driver, "cleanup", "cleanup" in driver.__dict__, driver.__dict__.get("cleanup")))
    driver.cleanup = finish
    return probe


if __name__ == "__main__":
    from types import SimpleNamespace
    engine = SimpleNamespace(_trial_id="self-check", _group_id=1, _stopped=False)
    callbacks = list(gc.callbacks)
    p = Probe(engine)
    assert p.timed(lambda x: x + 1, "return")(2) == 3
    error = ValueError("retained exception")
    def fail():
        raise error
    try:
        p.timed(fail, "exception")()
    except ValueError as observed:
        assert observed is error
    else:
        raise AssertionError("exception lost")
    gc.collect()
    p.restore()
    assert callbacks == gc.callbacks
    assert {"return", "exception", "gc"} <= p.stages.keys()
    assert len(p.events) <= 4096 and len(p.windows) <= 32
    print("probe return/exception/GC restoration and bounds self-check passed")

    # Failed diagnostic persistence must never replace a lifecycle outcome.
    for raises in (False, True):
        e = SimpleNamespace(_trial_id="self-check", _group_id=1, _stopped=False)
        for name in ("render_tick", "_scene_state", "poll_diagnostics"):
            setattr(e, name, lambda: None)
        port = SimpleNamespace(**{name: lambda: None for name in (
            "render", "present", "select_images", "capture_review_composite", "poll_review_capture")})
        recording = SimpleNamespace(**{name: lambda: None for name in (
            "before_render", "rendered", "diagnostics")})
        original_error = RuntimeError("original cleanup")
        def cleanup():
            if raises:
                raise original_error
            return 17
        d = SimpleNamespace(engine=e, cleanup=cleanup)
        installed = install(d, port, recording)
        def no_disk():
            raise OSError("diagnostic write unavailable")
        installed.flush = no_disk
        try:
            result = d.cleanup()
            assert not raises and result == 17
        except RuntimeError as observed:
            assert raises and observed is original_error
        assert gc.callbacks == callbacks
    print("diagnostic I/O failure preserves cleanup return/exception")
