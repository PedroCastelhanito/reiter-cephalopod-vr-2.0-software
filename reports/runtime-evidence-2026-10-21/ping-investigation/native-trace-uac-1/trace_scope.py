"""Normal-token test requests fixed operations from the reviewed WPR broker."""
import json
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent


def wait_for(name, seconds, *, check_error=True):
    until = time.perf_counter_ns() + int(seconds * 1e9)
    while not (OUT / name).exists():
        if check_error and (OUT / "broker-error.json").exists():
            raise RuntimeError((OUT / "broker-error.json").read_text())
        if time.perf_counter_ns() >= until:
            raise TimeoutError(f"WPR broker did not publish {name}")
        time.sleep(0.05)
    return json.loads((OUT / name).read_text())


class TraceSession:
    def start(self):
        ready = wait_for("broker-ready.json", 10)
        assert ready["admin"] and not (OUT / "start.request").exists()
        (OUT / "start.request").write_text(str(time.perf_counter_ns()))
        wait_for("broker-started.json", 25)

    def stop(self):
        (OUT / "stop.request").write_text(str(time.perf_counter_ns()))
        if (OUT / "start.request").exists():
            outcome = wait_for("trace-stop-result.json", 85, check_error=False)
            assert outcome["confirmed"], outcome
