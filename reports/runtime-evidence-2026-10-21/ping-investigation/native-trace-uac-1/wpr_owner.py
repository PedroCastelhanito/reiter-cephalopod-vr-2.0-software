"""Own one bounded WPR instance; preserve ETL even if the Setup helper exits."""
import ctypes
import datetime
import json
import msvcrt
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

OUT = Path(__file__).resolve().parent
INSTANCE = "CephVRNativeTraceUAC20261021_1"
LIMIT_SECONDS = 180
WPR = "C:/Windows/System32/wpr.exe"


def stamp():
    counter, frequency = ctypes.c_longlong(), ctypes.c_longlong()
    ctypes.windll.kernel32.QueryPerformanceCounter(ctypes.byref(counter))
    ctypes.windll.kernel32.QueryPerformanceFrequency(ctypes.byref(frequency))
    return {"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "perf_counter_ns": time.perf_counter_ns(), "qpc": counter.value,
            "qpc_frequency": frequency.value}


def record(name, data):
    temporary = OUT / f".{name}.{uuid4().hex}.tmp"
    temporary.write_text(json.dumps(data, indent=2))
    os.replace(temporary, OUT / name)


def stop(who):
    with (OUT / "trace-stop.lock").open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return
        try:
            _stop_locked(who)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def _stop_locked(who):
    if not (OUT / "trace-started.json").exists():
        return
    claim_ns = time.perf_counter_ns()
    latest = OUT / "trace-stop-result.json"
    if latest.exists():
        prior = json.loads(latest.read_text())
        if prior.get("confirmed"):
            return
    record("trace-stop-claimed.json", {"who": who, "host_ns": claim_ns})
    command = [WPR, "-stop", str(OUT / "owned.etl"),
               "CephVR single full-protocol Setup noStart cancel", "-skipPdbGen",
               "-instancename", INSTANCE]
    before = stamp()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        outcome = {"who": who, "before": before,
               "after": stamp(), "command": command, "returncode": result.returncode,
               "stdout": result.stdout, "stderr": result.stderr}
    except Exception as exc:
        outcome = {"who": who, "before": before,
                   "after": stamp(), "error": repr(exc)}
    try:
        status = subprocess.run([WPR, "-status", "-instancename", INSTANCE],
                               capture_output=True, text=True, timeout=10)
        outcome["status"] = {"returncode": status.returncode,
                             "stdout": status.stdout, "stderr": status.stderr}
        outcome["confirmed"] = status.returncode == 0 and "WPR is not recording" in status.stdout
    except Exception as exc:
        outcome["status"] = {"error": repr(exc)}
        outcome["confirmed"] = False
    record(f"trace-stop-result-{claim_ns}.json", outcome)
    record("trace-stop-result.json", outcome)


class TraceSession:
    def start(self):
        assert not (OUT / "trace-started.json").exists(), "trace already consumed"
        status = subprocess.run([WPR, "-status"], capture_output=True, text=True, timeout=10)
        record("immediate-wpr-status.json", {"returncode": status.returncode,
               "stdout": status.stdout, "stderr": status.stderr})
        assert status.returncode == 0 and "WPR is not recording" in status.stdout
        temp = OUT / "wpr-temp"
        temp.mkdir(exist_ok=True)
        command = [WPR, "-start", "CPU.Verbose", "-filemode",
                   "-recordtempto", str(temp), "-instancename", INSTANCE]
        before = stamp()
        record("trace-started.json", {"instance": INSTANCE, "stamp": before,
               "max_seconds": LIMIT_SECONDS, "state": "start-intent"})
        self.guardian = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--guardian"],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        record("trace-start-result.json", {"before": before, "after": stamp(),
               "command": command, "returncode": result.returncode,
               "stdout": result.stdout, "stderr": result.stderr})
        assert result.returncode == 0, result.stdout + result.stderr
        record("trace-started.json", {"instance": INSTANCE, "stamp": stamp(),
               "max_seconds": LIMIT_SECONDS})

    def stop(self):
        stop("parent-finally")
        latest = OUT / "trace-stop-result.json"
        if latest.exists() and not json.loads(latest.read_text()).get("confirmed"):
            stop("parent-scoped-retry")


if __name__ == "__main__" and sys.argv[1:] == ["--guardian"]:
    started = json.loads((OUT / "trace-started.json").read_text())["stamp"]["perf_counter_ns"]
    while True:
        latest = OUT / "trace-stop-result.json"
        if latest.exists() and json.loads(latest.read_text()).get("confirmed"):
            break
        if time.perf_counter_ns() - started >= LIMIT_SECONDS * 1_000_000_000:
            stop("180-second-guardian")
            if latest.exists() and not json.loads(latest.read_text()).get("confirmed"):
                stop("guardian-scoped-retry")
            if latest.exists():
                break
        time.sleep(0.1)
