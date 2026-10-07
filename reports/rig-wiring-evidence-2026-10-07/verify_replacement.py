"""Retain replacement evidence and current read-only endpoint provenance."""

import hashlib
import json
import re
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path
from urllib.parse import unquote

from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import default_runtime_root

OUT = Path(__file__).parent
ROOT = OUT.parents[1]
context_path = OUT / "replacement-context.json"
if not context_path.exists():
    context_path.write_text('{"status": "verification pending"}', encoding="utf-8")
documents = ["TODO.md", "LOG.md", "architecture.md", "docs/architecture/system-contracts.md",
             "contracts/windows-launch.md", "reports/runtime.md", "reports/rig-verification.md",
             str(OUT.relative_to(ROOT) / "README.md")]
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
for suffix, passed, skipped in (("after", 37, 0), ("integration", 219, 1), ("native-endpoint", 3, 0)):
    suite = ET.parse(OUT / f"replacement-{suffix}.xml").getroot().find("testsuite").attrib
    assert int(suite["failures"]) == int(suite["errors"]) == 0
    assert int(suite["skipped"]) == skipped and int(suite["tests"]) - skipped == passed
    totals[suffix] = suite
root = default_runtime_root()
record = _existing_endpoint(root)
assert record.controller_generation == "73987d0f-0d80-4f63-a646-3dba430048bb", "Observed owner changed; do not overwrite its historical assessment"
names = ["src/cephvr/launcher/main.py", "src/cephvr/launcher/replacement.py",
         "tests/launcher/test_lifecycle.py", "tests/platform/test_windows_native_on_rig.py",
         "scripts/start_runtime_gui.py", "contracts/windows-launch.md",
         "docs/architecture/system-contracts.md", "architecture.md"]
cleanup_path = OUT / "replacement-cleanup.json"
cleanup = json.loads(cleanup_path.read_text(encoding="utf-8-sig")) if cleanup_path.exists() else []
assert all(not Path(item["path"]).exists() for item in cleanup)
context = {
    "date": "2026-10-07", "timezone": "Asia/Tokyo",
    "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "dirty_tree": True, "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names},
    "read_only_current_endpoint": {"path": str(root / "launcher.json"), "record": asdict(record)},
    "interactive_observation": {
        "command": "C:/Users/ReiterU_PC/miniforge3/python.exe scripts/start_runtime_gui.py",
        "method": "Native interactive PTY, before and after change; answer N",
        "prompt": "CephVR2 is already running. Kill the existing runtime and start this one? Unsaved work may be lost. [Y/N]:",
        "answer": "N", "output": "Existing runtime left running.", "exit_code": 0,
    },
    "test_suites": totals,
    "commands": {
        "after": "pytest tests/launcher -q",
        "integration": 'pytest tests/launcher tests/supervisor tests/shared tests/client tests/controller/test_shutdown_handoff.py -q -m "not rig"',
        "native-endpoint": 'pytest tests/platform/test_windows_native_on_rig.py -q -k "replacement_endpoint or replacement_waits"',
    },
    "static": {"ruff": "pass", "format_files": 8, "windows_mypy_sources": 6, "boundary_modules": 604, "boundary_violations": 0},
    "before": "Five new native-authorized launcher regressions fail; initial sandbox attempt has four temp-directory fixture errors/one failure. Added cold-directory native variant fails before repair. Raw JUnit retained separately.",
    "limits": "Owner's original failure runtime path/timing unknown; startup race is reproduced and repaired, but original cause is not proven. Missing/unsafe endpoint still forbids replacement. No live Y, termination, restart or rig device operation occurred; current owner remains intact.",
    "document_links_checked": links,
    "cleanup": {"targets": len(cleanup), "files": sum(i["files"] for i in cleanup), "bytes": sum(i["bytes"] for i in cleanup)},
}
context_path.write_text(json.dumps(context, indent=2), encoding="utf-8")
print(f"Verified {len(documents)} documents/{links} links, JUnit results, exact unchanged endpoint and {len(cleanup)} absent cleanup targets.")
