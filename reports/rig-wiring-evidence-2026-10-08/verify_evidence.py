"""Final evidence consistency, edited-document links, exact source patch and hashes."""

import hashlib
import json
import re
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

OUT = Path(__file__).parent
ROOT = OUT.parents[1]
documents = ["TODO.md", "LOG.md", "reports/runtime.md", "reports/acquisition.md", "reports/tracking.md", "reports/visual_stimulus.md", "reports/rig-verification.md", str(OUT.relative_to(ROOT) / "README.md")]
suite_path = OUT / "final-tree-tests.xml"
suite = ET.parse(suite_path).getroot().find("testsuite")
assert suite is not None
assert int(suite.attrib["failures"]) == 8 and int(suite.attrib["errors"]) == 0
failed = [case.attrib for case in suite.findall("testcase") if case.find("failure") is not None]
assert all(case["classname"] == "tests.gui.test_dashboard" for case in failed)
passed = int(suite.attrib["tests"]) - int(suite.attrib["failures"]) - int(suite.attrib["skipped"])
changes = subprocess.check_output(["git", "diff", "--name-only", "--", "src", "tests"], cwd=ROOT, text=True).splitlines()
(OUT / "final-repairs.patch").write_bytes(subprocess.check_output(["git", "diff", "--", "src", "tests"], cwd=ROOT))
context = {
    "date": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
    "baseline_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "review_range": "e4c653c..7ba43b1", "dirty_source_tree": True,
    "policy_versions": {"acquisition": 18, "microcontroller": 1},
    "baseline_source_manifest": "source-sha256.json", "source_patch": "final-repairs.patch",
    "changed_source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in changes},
    "final_suite": {"passed": passed, "failed": int(suite.attrib["failures"]), "skipped": int(suite.attrib["skipped"]), "deselected_rig": 1, "time_s": suite.attrib["time"], "failures": failed},
    "methods": {
        "suite": '.venv/Scripts/python.exe -m pytest tests -q -m "not rig"; QT_QPA_PLATFORM=offscreen',
        "baseline": 'tools/test_on_rig.ps1 -OutputDirectory reports/rig-wiring-evidence-2026-10-08/automated',
        "managed_board": "managed_mcu.py; authenticated controller RPC; acquisition temporarily disabled, restored",
        "cameras": "managed_cameras.py; actual GUI managed-device dispatch, native coordinates/Qt screenshot; approved BehaviorSquid",
        "negative_compile": "managed_failure.py; native #error fixture, same-connection comparison, active-D9 release",
        "watchdog": "board_watchdog.py; isolated board after exact application exit, 3.4 s host silence",
        "cleanup": "cleanup.ps1; literal verified workspace paths; final-native-cleanup.json",
    },
    "scope": "bounded software/native/device checks; three product repairs and uncertain-start cleanup fence; no scientific session or remote mutation; physical timing, Tracking health, GUI clipping, remote/projector/full-load limitations retained",
}
(OUT / "context.json").write_text(json.dumps(context, indent=2), encoding="utf-8")
links = 0
for name in documents:
    source = ROOT / name
    for match in re.finditer(r"\]\(([^)]+)\)", source.read_text(encoding="utf-8")):
        target = match.group(1).strip().strip("<>")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        path, _, anchor = unquote(target).partition("#")
        destination = (source.parent / path).resolve() if path else source
        assert destination.exists(), (name, target)
        if anchor and destination.suffix == ".md":
            contents = destination.read_text(encoding="utf-8")
            anchors = set(re.findall(r'id=["\']([^"\']+)', contents))
            for heading in re.findall(r"^#{1,6}\s+(.+)$", contents, re.M):
                slug = re.sub(r"<[^>]+>", "", heading).replace("`", "").lower()
                slug = "".join(c for c in slug if c in "-_ " or unicodedata.category(c)[0] in "LN")
                anchors.add(slug.replace(" ", "-"))
            assert anchor in anchors, (name, target)
        links += 1
print(f"Final suite {passed} pass/8 fail/{suite.attrib['skipped']} skip; preserved source patch/{len(changes)} hashes; {len(documents)} documents/{links} links checked.")
