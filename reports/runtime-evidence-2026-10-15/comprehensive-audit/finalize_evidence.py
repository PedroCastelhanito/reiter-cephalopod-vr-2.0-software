"""Record final source/provenance and check edited Markdown link targets."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import unquote

root = Path.cwd()
out = Path(__file__).parent
changed = subprocess.check_output(["git", "diff", "--name-only", "0361484d1018c2514ba64aba22432a0079c6ce5c"], text=True).splitlines()
sources = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in changed if name.startswith(("src/", "tests/"))}
missing = []
links = 0
for name in [item for item in changed if item.endswith(".md")] + [str((out/"README.md").relative_to(root))]:
    path = root/name
    prose = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", prose):
        target = match.group(1).strip("<>").split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        links += 1
        if not (path.parent/unquote(target)).exists():
            missing.append({"file": name, "target": target})
assert not missing, missing
record = {
    "observed_unix_time": time.time(),
    "source_revision_at_start": "0361484d1018c2514ba64aba22432a0079c6ce5c",
    "head_before_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "modified_source_sha256": sources,
    "checks": {
        "backend": "1920 passed,5 skipped (symlink privilege),1 rig deselected;20.92s",
        "explicit_rig_flow": "1 passed;0.37s; synthetic same-image CUDA/NVOF only",
        "gui_offscreen": "519 passed across512+7; later changed row fixture separately passes",
        "gui_native": "510 passed/2 failed/7 deselected; later reviewed row fixture passes native and offscreen; one MouseMove case unresolved and7 selection fixtures blocked",
        "tracking_contracts": "48 passed",
        "visual_contracts": "42 passed",
        "static": "Ruff/format915/Win32 mypy795/boundaries699zero/whitespace pass",
        "videos": "27 full decode/count passes:18 managed with declared counts matched;9 direct submitted counts matched",
        "restoration": "all3 original PFS byteexact,all original feature readbacks matched,camerasclosed;10 savedJSON/TOML byteexact",
        "final_shutdown": "Command succeeded and exact process absence confirmed, but cleanup returned an unregistered resource emergency retained; shutdown resource-report acceptance unresolved",
        "markdown_link_targets": {"checked": links, "missing": missing, "scope": "edited documents and evidence README; no heading anchors changed"},
    },
    "limits": ["No MCU firmware flash; external-trigger acceptance blocked by current incompatible CAPS dialect", "Tracking processing/feedback and physical optical calibration unverified", "Saved full arena resource budget rejection retained; explicit reduced512texture fixture used", "Abort metadata settlement40.12s and post-session calibration reopening fence remain", "Final shutdown cleanup resource registration emergency remains despite command success and confirmed process absence", "Native4096 direct case one BlockID gap; black Tracking sample and dim scene limit quality claims", "Original direct CPU interval overlaps tests; final managed active60s interval isolated", "Harnesses evolved during audit; final helper hashes are not exact historical execution revisions; per-run commands/settings/results retained"],
}
(out/"final-validation-context.json").write_text(json.dumps(record, indent=2)+"\n")
index = {}
for path in sorted(out.rglob("*")):
    if path.is_file() and path.name != "evidence-index.json":
        content = path.read_bytes()
        index[str(path.relative_to(out))] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
(out/"evidence-index.json").write_text(json.dumps(index, indent=2)+"\n")
print(json.dumps({"source_files": len(sources), "evidence_files": len(index), "evidence_bytes": sum(row["bytes"] for row in index.values()), "markdown_targets": links}, indent=2))
