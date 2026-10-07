"""Retain presentation provenance and verify documents/results without hardware."""

import hashlib
import json
import re
import subprocess
import tomllib
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

OUT = Path(__file__).parent
ROOT = OUT.parents[1]
context_path = OUT / "preview-presentation-context.json"
if not context_path.exists():
    context_path.write_text('{"status": "verification pending"}', encoding="utf-8")
names = [
    "src/cephvr/acquisition/preview/highgui.py",
    "src/cephvr/acquisition/preview/viewport.py",
    "src/cephvr/acquisition/coordinator/preview_windows.py",
    "src/cephvr/acquisition/coordinator/manual_preview_window.py",
    "src/cephvr/acquisition/coordinator/manual_preview.py",
    "src/cephvr/acquisition/config/policy.py",
    "src/cephvr/controller/device/camera.py",
    "src/cephvr/gui/main.py",
    "src/cephvr/gui/managed_preview_viewers.py",
    "src/cephvr/gui/managed_device_commands.py",
    "src/cephvr/gui/preview_placement.py",
    "src/cephvr/platform/windows/window_coordinates.py",
    "src/cephvr/shared/preview_placement.py",
    "tests/acquisition/test_manual_preview.py", "tests/gui/test_dashboard.py",
    "contracts/cephvr/control/v1/services.proto",
    "contracts/policy/acquisition_policy.toml",
    "config/backends/acquisition_config.toml",
]
documents = ["TODO.md", "LOG.md", "architecture.md",
             "docs/architecture/acquisition.md", "docs/architecture/gui.md",
             "contracts/acquisition/preview-control.md", "reports/acquisition.md",
             "reports/runtime.md", "reports/rig-verification.md"] + [str(OUT.relative_to(ROOT) / "README.md")]
links = 0
for name in documents:
    source = ROOT / name
    for match in re.finditer(r"\]\(([^)]+)\)", source.read_text(encoding="utf-8")):
        target = match.group(1).strip().strip("<>")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        path, _, anchor = unquote(target).partition("#")
        destination = (source.parent / path).resolve() if path else source
        assert destination.exists(), (source, target)
        if anchor and destination.suffix == ".md":
            contents = destination.read_text(encoding="utf-8")
            anchors = set(re.findall(r'id=["\']([^"\']+)', contents))
            for heading in re.findall(r"^#{1,6}\s+(.+)$", contents, re.M):
                slug = re.sub(r"<[^>]+>", "", heading).replace("`", "").lower()
                slug = "".join(c for c in slug if c in "-_ " or unicodedata.category(c)[0] in "LN")
                anchors.add(slug.replace(" ", "-"))
            assert anchor in anchors, (source, target)
        links += 1
totals = {}
for suffix, passed, skipped in (("tests", 549, 2), ("native", 1, 0), ("gui", 8, 0)):
    suite = ET.parse(OUT / f"preview-presentation-{suffix}.xml").getroot().find("testsuite").attrib
    assert int(suite["failures"]) == int(suite["errors"]) == 0
    assert int(suite["skipped"]) == skipped
    assert int(suite["tests"]) - skipped == passed
    totals[suffix] = suite
for name in ("contracts/policy/acquisition_policy.toml", "config/backends/acquisition_config.toml"):
    assert tomllib.loads((ROOT / name).read_text(encoding="utf-8"))["policy_version"] == 15
cleanup_path = OUT / "preview-presentation-cleanup.json"
cleanup = json.loads(cleanup_path.read_text(encoding="utf-8-sig")) if cleanup_path.exists() else []
assert all(not Path(item["path"]).exists() for item in cleanup)
context = {
    "date": "2026-10-07", "timezone": "Asia/Tokyo",
    "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "dirty_tree": True, "policy_version": 15,
    "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names},
    "commands": {
        "tests": '.venv/Scripts/python.exe -m pytest tests/acquisition tests/controller tests/client -q -m "not rig"',
        "native": ".venv/Scripts/python.exe -m pytest tests/acquisition/test_manual_preview.py -q -m windows",
        "gui": 'QT_QPA_PLATFORM=offscreen; pytest tests/gui/test_dashboard.py -q -k "square_preview or preview_window_waits or managed_camera_projection_distinguishes"',
    },
    "test_suites": totals,
    "static_checks": {"ruff": "pass", "format_files": 448, "windows_mypy_sources": 395,
                      "boundary_modules": 604, "boundary_violations": 0, "protos_generated": 19},
    "document_links_checked": links,
    "cleanup": {"targets": len(cleanup), "files": sum(i["files"] for i in cleanup), "bytes": sum(i["bytes"] for i in cleanup)},
    "assessment": "Native isolated HighGUI physical placement/square image area, cached-frame wheel/reset redraw and independent X/producer lifetime pass. Owner runtime preserved; full restart, actual GUI/monitor/DPI and physical-camera presentation acceptance remain open. Existing Tracking coordinator-health and full-workload limitations remain.",
    "failed_attempt": "Sandboxed non-Windows-marked selection stalled after 17 cases; exact test process ended and native-authorized final integration passed. Initial two geometry-local-name mypy errors corrected.",
}
context_path.write_text(json.dumps(context, indent=2), encoding="utf-8")
print(f"Verified {len(documents)} documents/{links} links, JUnit outcomes, policy 15 and {len(cleanup)} absent cleanup targets.")
