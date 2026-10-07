"""Verify current installation evidence and edited document links without hardware."""

import hashlib
import json
import re
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

OUT = Path(__file__).parent
ROOT = OUT.parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


files = [ROOT / name for name in ("TODO.md", "LOG.md", "reports/acquisition.md",
         "reports/runtime.md", "reports/tracking.md", "reports/rig-verification.md",
         "firmware/uno/README.md")] + [OUT / "README.md", OUT / "mcu-installation-and-preview.md"]
checked = 0
for source in files:
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
        checked += 1
image = OUT / "mcu-counted-firmware/cephvr2_mcu.ino.hex"
assert digest(image) == "0e4d05e6466328f26b33866793d895d65943ea4dfbd35165a2a090f2023bf630"
assert digest(OUT / "mcu-before-protocol3-flash.hex") == "dcc0f4d1c7f50c45115bf45c591d6df8d4bc6d77f52ba9e0785736678716e19a"
board = json.loads((OUT / "mcu-update-board.json").read_text())["checks"]
assert board["startup"]["capabilities"]["protocol_version"] == 3
assert board["startup"]["capabilities"]["firmware"] == "cephvr2_uno_2"
assert board["serial_closed"]
assert board["cleanup_off"]["applied"]
managed = json.loads((OUT / "mcu-update-managed.json").read_text())["checks"]
for name in ("start", "show", "hide", "reopen", "show_after_x", "stop"):
    assert managed[f"camera_1_{name}"]["succeeded"]
for name in ("hidden_capture_continues", "native_closed_capture_continues"):
    view = managed[f"camera_1_{name}"]["acquisition_devices"]["behavioral"]
    assert view["preview_running"] and not view["preview_visible"]
final = managed["camera_1_final"]["acquisition_devices"]["behavioral"]
assert not final["preview_running"] and not final["cleanup_pending"]
assert managed["camera_1_final_window"]["handle"] is None
diagnostics = json.loads((OUT / "mcu-handoff-diagnostics.json").read_text())["checks"]
assert "error" not in diagnostics
for name in ("behavioral", "tracking"):
    stopped = diagnostics[f"{name}_stopped"]["diagnostic"]
    assert not stopped["active"] and stopped["rising_edges"] > 1
timeout = diagnostics["trial_timeout_readback"]["diagnostic"]
assert not timeout["active"] and timeout["rising_edges"] == 1
totals = {name: ET.parse(OUT / name).getroot().find("testsuite").attrib for name in
          ("mcu-preview-adoption.xml", "mcu-preview-integration.xml")}
assert int(totals["mcu-preview-integration.xml"]["failures"]) == 0
cleaned = json.loads((OUT / "mcu-install-cleanup.json").read_text(encoding="utf-8-sig"))
cleaned += json.loads((OUT / "mcu-install-cleanup-final.json").read_text(encoding="utf-8-sig"))
assert all(not Path(item["path"]).exists() for item in cleaned)
source_names = ["firmware/uno/cephvr2_mcu/cephvr2_mcu.ino",
                "src/cephvr/acquisition/worker/camera_configuration.py",
                "src/cephvr/acquisition/worker/execution.py",
                "tests/acquisition/test_camera_adapter_contracts.py",
                "contracts/policy/acquisition_policy.toml", "config/backends/acquisition_config.toml"]
context = {"date": "2026-10-07", "timezone": "Asia/Tokyo",
           "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
           "dirty_tree": True, "uploaded": True, "upload_verified_exit_code": 0,
           "firmware_image_sha256": digest(image), "flash_backup_sha256": digest(OUT / "mcu-before-protocol3-flash.hex"),
           "source_sha256": {name: digest(ROOT / name) for name in source_names},
           "test_suites": totals, "document_links_checked": checked,
           "cleanup": {"targets": len(cleaned), "files": sum(i["files"] for i in cleaned), "bytes": sum(i["bytes"] for i in cleaned)},
           "limits": "Behavior native command window checks pass; Tracking health failure and physical receiver/voltage/waveform acceptance remain open."}
(OUT / "mcu-installed-context.json").write_text(json.dumps(context, indent=2), encoding="utf-8")
print(f"{len(files)} Markdown files/{checked} local links pass; exact image/backup, board/Behavior/managed diagnostic evidence and cleanup inventory verified.")
