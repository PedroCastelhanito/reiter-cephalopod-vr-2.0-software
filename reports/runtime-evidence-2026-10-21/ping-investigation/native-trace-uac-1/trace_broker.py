"""Transient elevated WPR owner only: no runtime credentials or device access."""
import ctypes
import json
import subprocess
import time

from wpr_owner import OUT, WPR, TraceSession, record, stamp


def main():
    assert ctypes.windll.shell32.IsUserAnAdmin(), "WPR broker needs UAC elevation"
    trace = TraceSession()
    try:
        status = subprocess.run([WPR, "-status"], capture_output=True, text=True, timeout=10)
        assert status.returncode == 0 and "WPR is not recording" in status.stdout
        record("broker-ready.json", {"stamp": stamp(), "admin": True,
               "status": status.stdout, "scope": "fixed owned WPR CPU profile only"})
        waiting = time.perf_counter_ns()
        while not (OUT / "start.request").exists():
            if (OUT / "stop.request").exists():
                return
            if time.perf_counter_ns() - waiting >= 300_000_000_000:
                raise TimeoutError("no start request within five minutes")
            time.sleep(0.05)
        trace.start()
        record("broker-started.json", {"stamp": stamp()})
        started = time.perf_counter_ns()
        while not (OUT / "stop.request").exists():
            if time.perf_counter_ns() - started >= 180_000_000_000:
                break
            time.sleep(0.05)
    except BaseException as exc:
        record("broker-error.json", {"stamp": stamp(), "error": repr(exc)})
        raise
    finally:
        trace.stop()
        record("broker-exited.json", {"stamp": stamp()})


if __name__ == "__main__":
    main()
