"""Check edited repository links, executed counts and frozen source inputs."""

import hashlib
import json
import re
import tomllib
import unicodedata
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent


def slug(value):
    value = re.sub(r"<[^>]+>", "", value).replace("`", "").lower()
    value = "".join(c for c in value if c in "-_ " or unicodedata.category(c)[0] in "LN")
    return value.replace(" ", "-")


files = [ROOT / "TODO.md", ROOT / "LOG.md"] + [
    ROOT / "reports" / name for name in (
        "runtime.md", "acquisition.md", "tracking.md", "visual_stimulus.md", "rig-verification.md"
    )
] + [OUT / "README.md"]
checked = 0
for source in files:
    text = source.read_text(encoding="utf-8")
    for match in re.finditer(r"\]\(([^)]+)\)", text):
        target = match.group(1).strip().strip("<>")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        path, _, anchor = unquote(target).partition("#")
        destination = (source.parent / path).resolve() if path else source
        assert destination.exists(), (source, target)
        if anchor and destination.suffix == ".md":
            contents = destination.read_text(encoding="utf-8")
            anchors = set(re.findall(r'id=["\']([^"\']+)', contents))
            anchors.update(slug(h) for h in re.findall(r"^#{1,6}\s+(.+)$", contents, re.M))
            assert anchor in anchors, (source, target)
        checked += 1
manifest = json.loads((OUT / "source-sha256.json").read_text())
changed = [name for name, expected in manifest.items() if
           hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected]
assert not changed, changed
with (ROOT / "pyproject.toml").open("rb") as stream:
    tomllib.load(stream)
receiver = json.loads((OUT / "tracking-receiver.json").read_text())
assert len(receiver["frames"]) == 81
assert all(frame["valid"] for frame in receiver["frames"])
assert receiver["on"]["applied"] and receiver["off"]["applied"]
print(f"{len(files)} Markdown files / {checked} local links and anchors pass; "
      f"{len(manifest)} source/input hashes unchanged; TOML parses; 81 valid receiver frames.")
