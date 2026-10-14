import json
import re
from pathlib import Path

root = Path(__file__).parent
p = Path('TODO.md')
b = p.read_bytes()
p.write_bytes(re.sub(rb'(\r?\n)(?:\r?\n){2,}', rb'\1\1', b))

p = root / 'final-provenance.json'
d = json.loads(p.read_text())
d['source_hash_scope'] = 'Changed tracked files at final snapshot; pre-existing/untracked source and rig assets are not a complete immutable revision. Earlier native generations used earlier subsets of fixes.'
d['json_schema_scope'] = '30 schema files parse as JSON objects; no formal meta-schema validator installed. Runtime/contract behavior is covered by owning suites, not inferred from this parse.'
d['contract_generation_check'] = json.loads((root / 'closing-contracts.json').read_text())
d['delegated_visual_final']['command'] = 'python -m pytest tests/visual_stimulus -q'
p.write_text(json.dumps(d, indent=2) + '\n')

with Path('LOG.md').open('ab') as out:
    out.write(b'\n\n## 2026-10-14 - Final configuration and evidence checks\n\n- `rig-timing-buffer-audit` [repo] [controller] [supervisor] [acquisition] [visual_stimulus] [shared] [gui]: parse16 operator/policy TOMLs, parse30 schema JSON objects (formal meta-schema validator unavailable), validate10 new report links, confirm visual config byte-exact original and buffer17 in owning TOML. Generate19 proto sources into isolated owned temporary directory;57 pb2 outputs compare with zero source drift. Generated source untouched. Final-provenance records changed tracked-file hashes and their dirty/untracked/earlier-generation limits.\n- Full Visual selection initially310pass/one old automatic-retirement fixture expectation failed; update only that owning fixture to call explicit catalogue retirement, delegated full311pass. Failed log/XML preserved under closing-visual-before-fixture-retirement; final delegated outcome/provenance recorded. Other final backend1229pass/5skip and GUI494pass remain current. Source/resource retirement reviewed under ARCH-002: existing preparation/catalogue owners, no new dependency/process, same-key reopening invalidates receipts; lifecycle609 lines remains cohesive orchestration delegating resource/recording/display/trial owners.\n')
