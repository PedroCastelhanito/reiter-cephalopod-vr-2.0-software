from pathlib import Path
from urllib.parse import unquote
import re

names = ["contracts/gui-configuration-files.md", "TODO.md", "architecture.md", "docs/architecture/gui.md", "docs/architecture/tracking.md",
         "docs/architecture/visual_stimulus.md", "contracts/gui-calibration.md",
         "contracts/tracking/records.md", "contracts/tracking/recording.md",
         "contracts/tracking/pipeline-catalogue.md", "contracts/tracking/locomotion-output.md",
         "contracts/tracking/water-flow-proxy.md", "contracts/tracking/fin-flow.md",
         "contracts/tracking/pose.md", "contracts/visual_stimulus/feedback.md",
         "reports/tracking.md", "reports/visual_stimulus.md", "reports/runtime.md",
         "reports/rig-verification.md"]
checked = 0
for name in names:
    source = Path(name)
    text = source.read_text(encoding="utf-8")
    for link in re.findall(r"\]\(([^\s)]+)\)", text):
        if "://" in link or link.startswith("mailto:"):
            continue
        destination, _, anchor = unquote(link).partition("#")
        target = source.parent / destination if destination else source
        if not target.exists():
            raise RuntimeError(f"Missing target in {source}: {link}")
        if anchor and target.suffix == ".md":
            target_text = target.read_text(encoding="utf-8")
            anchors = set(re.findall(r'<a id="([^"]+)"', target_text))
            for heading in re.findall(r"^#{1,6}\s+(.+)$", target_text, re.M):
                anchors.add(re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-"))
            if anchor not in anchors:
                raise RuntimeError(f"Missing anchor in {source}: {link}")
        checked += 1
register = Path("architecture.md").read_text(encoding="utf-8")
for name, ids in (("tracking", ("T08", "T19", "T20", "T35", "T38", "T43")),
                  ("gui", ("G01",)), ("visual_stimulus", ("V01", "V15", "V24"))):
    text = Path(f"docs/architecture/{name}.md").read_text(encoding="utf-8")
    for decision in ids:
        revision = re.search(rf"### {decision} — .*?\*\*Revision:\*\* (\d+)", text, re.S).group(1)
        assert re.search(rf"\[{decision}\].*?\| Accepted \| {revision} \|", register), decision
print(f"{checked} local links/anchors and 10 amended register entries pass")
