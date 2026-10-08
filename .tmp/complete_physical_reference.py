from pathlib import Path
import hashlib
import json

root = Path.cwd()
context_path = root / "reports/tracking-evidence-2026-10-08/physical-reference-context.json"
context = json.loads(context_path.read_text(encoding="utf-8"))
docs = ["architecture.md", "docs/architecture/gui.md", "docs/architecture/tracking.md",
        "docs/architecture/visual_stimulus.md", "contracts/gui-calibration.md",
        "contracts/tracking/records.md", "contracts/tracking/recording.md",
        "contracts/tracking/pipeline-catalogue.md", "contracts/tracking/locomotion-output.md",
        "contracts/tracking/water-flow-proxy.md", "contracts/tracking/fin-flow.md",
        "contracts/tracking/pose.md", "contracts/visual_stimulus/feedback.md",
        "reports/tracking.md", "reports/visual_stimulus.md", "reports/runtime.md",
        "reports/rig-verification.md"]
context["checks"].extend([
    dict(command="python .tmp/check_physical_reference_docs.py", outcome="682 local links/anchors and 10 amended register entries pass"),
    dict(command="git diff --check", outcome="Pass; normalize changed text to repository UTF-8/LF"),
])
with (root / "LOG.md").open("a", encoding="utf-8", newline="\n") as stream:
    stream.write("\n### 2026-10-08 [gui] [tracking] [visual_stimulus] Complete physical reference implementation and local validation\n\n"
                 "- Complete `physical-reference-calibration` implementation under the amended G01/V01/V15/V24/T08/T19/T20/T35/T38/T43 records. Final source review fixes output-mode provenance reuse, bounds generated-asset comparison/path resolution, and restricts consumer-unit checks to active Visual Stimulus under E07. Portable old inventories remain strict and unmeasured; raw pixel/radian evidence and original calibration assets remain. Update owning reports and the single rig checklist; preserve concurrent dummy work/defaults.\n"
                 "- Affected permitted-loopback/offscreen suite passes 658 with one skip and three deselections in 190.04 s. Two deselections are default/pacing checks affected by another chat's explicitly temporary calibration_front value; the first broad run retains those two failures plus a corrected stale unit-conflict fixture. Post-review configuration/recording checks pass 57, four GUI measurement/migration/export/legacy-binding cases pass, 48 Tracking contracts and 19/11 Tracking/Visual Stimulus generated-schema checks pass. Final Ruff lint/format pass 348 files, Win32 mypy passes 322 sources, boundaries inspect 625 modules with zero violations; 682 local links/anchors, ten amended register entries and whitespace pass.\n"
                 "- Retain raw JUnit, current method/source hashes and limitations in reports/tracking-evidence-2026-10-08/physical-reference-context.json. Visually inspect the 760×374 offscreen measurement card after loading Segoe UI for this QA environment; initial offscreen font boxes are a QA limitation, corrected without product changes. No new native projector/camera/managed runtime session, optical/DPI/scientific/full-load pass or legacy gain conversion is claimed. Rig acceptance remains open; video cadence padding remains separate. Remove only this completed implementation task from TODO.\n")
todo = root / "TODO.md"
text = todo.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)
matches = [line for line in lines if line.startswith("- [ ] `physical-reference-calibration`")]
assert len(matches) == 1
text = text.replace(matches[0] + "\n", "", 1)
todo.write_text(text, encoding="utf-8", newline="\n")
names = set(context["source_sha256"]) | set(docs) | {
    "LOG.md", "TODO.md", "src/cephvr/gui/projector_geometry.py", "src/cephvr/gui/calibration_arena.py",
    "contracts/tracking/test_contracts.py", "contracts/tracking/test_pipeline_contracts.py",
}
for name in names:
    path = root / name
    data = path.read_bytes()
    if b"\r\n" in data:
        path.write_bytes(data.replace(b"\r\n", b"\n"))
context["source_sha256"] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in context["source_sha256"]}
context_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8", newline="\n")
print("Implementation task completed; concurrent tasks preserved; UTF-8/LF and source hashes reconciled")
