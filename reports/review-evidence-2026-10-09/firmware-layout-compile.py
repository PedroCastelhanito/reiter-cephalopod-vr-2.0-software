"""Compile the repaired pinned sketch layouts without opening a serial port."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

from cephvr.controller.microcontroller.firmware import read_uno_image
from cephvr.controller.microcontroller.firmware_source import read_uno_sketch
from cephvr.controller.microcontroller.firmware_upload import arduino_cli

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
scratch = ROOT / ".tmp"
scratch.mkdir(exist_ok=True)
results = {}
for name in ("cephvr1_mcu", "cephvr2_mcu"):
    selected = read_uno_sketch(str(ROOT / "firmware/uno" / name / f"{name}.ino"))
    assert read_uno_sketch(str(selected.path), selected.digest) == selected
    expected = [f"{name}.ino"] + (["projector_clock.h"] if name == "cephvr1_mcu" else [])
    assert sorted(p.as_posix() for p, _ in selected.files) == sorted(expected)
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix=f"firmware-layout-{name}-", dir=scratch) as directory:
        trial = Path(directory)
        project = trial / name
        project.mkdir()
        for relative, payload in selected.files:
            destination = project / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        build, output = trial / "build", trial / "output"
        command = [str(arduino_cli()), "compile", "--fqbn", "arduino:avr:uno", "--clean",
                   "--build-path", str(build), "--output-dir", str(output), str(project)]
        start = time.monotonic()
        with (OUT / f"firmware-layout-{name}-compile.txt").open("w", encoding="utf-8") as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        record = {"command": command, "started_utc": started, "elapsed_seconds": round(time.monotonic()-start, 3),
                  "returncode": result.returncode, "source": str(selected.path), "snapshot_digest": selected.digest,
                  "source_sha256": {p.as_posix(): hashlib.sha256(raw).hexdigest() for p, raw in selected.files}}
        if result.returncode == 0:
            image = read_uno_image(str(output / f"{name}.ino.hex"))
            (OUT / f"firmware-layout-{name}.hex").write_bytes(image.payload)
            record["validated_hex_digest"] = image.digest
        results[name] = record
        print(name, record["returncode"], record["elapsed_seconds"], flush=True)
        print((OUT / f"firmware-layout-{name}-compile.txt").read_text(encoding="utf-8")[-1200:], flush=True)

context = {"recorded_utc": datetime.now(timezone.utc).isoformat(), "results": results,
           "method": "Existing production source snapshot and HEX validator; Arduino CLI compiles pinned bytes in workspace scratch. TemporaryDirectory removes only its task-created workspace-contained build tree. No upload, serial access or board command.",
           "limitations": "CephVR1 is the retained legacy serial protocol, lacking CAPS. Successful compilation is not protocol-3 host compatibility or electrical/experiment acceptance."}
(OUT / "firmware-layout-compile.json").write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
raise SystemExit(any(record["returncode"] for record in results.values()))
