"""Check generated bindings, declarations and changed-document references."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
from generate_contracts import generate

issues = []
generated = {}
scratch = ROOT / '.tmp'
scratch.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='cephvr-bindings-', dir=scratch) as temp:
    assert generate(Path(temp)) == 0
    for path in Path(temp).rglob('*_pb2*'):
        if path.suffix not in ('.py', '.pyi'):
            continue
        relative = path.relative_to(temp)
        current = ROOT / 'src' / relative
        if current.read_bytes() != path.read_bytes():
            issues.append(f'Generated drift: {relative}')
        generated[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()

tomls = sorted([*ROOT.glob('config/**/*.toml'), *ROOT.glob('contracts/**/*.toml')])
for path in tomls:
    tomllib.loads(path.read_text(encoding='utf-8'))
for config in ROOT.glob('config/backends/*_config.toml'):
    policy = ROOT / 'contracts/policy' / config.name.replace('_config', '_policy')
    if policy.exists():
        a = tomllib.loads(config.read_text(encoding='utf-8'))['policy_version']
        b = tomllib.loads(policy.read_text(encoding='utf-8'))['policy_version']
        if a != b:
            issues.append(f'Policy version mismatch: {config.name}')

register = (ROOT / 'architecture.md').read_text(encoding='utf-8')
revisions = 0
for match in re.finditer(r'\[([^\]]+)\]\(((?:docs/architecture/[^)#]+)?)#([^)]*)\).*?\|\s*(\d+)\s*\|', register):
    ident, file, anchor, revision = match.groups()
    body = (ROOT / (file or 'architecture.md')).read_text(encoding='utf-8')
    section = body.split(f'<a id="{anchor}"></a>', 1)[1].split('<a id=', 1)[0]
    actual = re.search(r'\*\*Revision:\*\* (\d+)', section)
    if actual is None or actual.group(1) != revision:
        issues.append(f'Decision revision mismatch: {ident}')
    revisions += 1

changed = subprocess.check_output(['git', 'diff', '--name-only', '0aebf47', 'HEAD', '--', '*.md', ':!.tmp'], cwd=ROOT, text=True).splitlines()
changed = sorted(set(changed) | set(subprocess.check_output(['git', 'diff', '--name-only', 'HEAD', '--', '*.md', ':!.tmp'], cwd=ROOT, text=True).splitlines()))
checked = 0
anchors_cache = {}
def anchors(path):
    if path not in anchors_cache:
        data = path.read_text(encoding='utf-8')
        values = set(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)', data))
        duplicates = {}
        for title in re.findall(r'^#{1,6}\s+(.+)$', data, re.M):
            title = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', title).strip().lower()
            slug = re.sub(r'[^\w\- ]', '', title).replace(' ', '-')
            n = duplicates.get(slug, 0)
            duplicates[slug] = n + 1
            values.add(slug if n == 0 else f'{slug}-{n}')
        anchors_cache[path] = values
    return anchors_cache[path]

for file in changed:
    source = ROOT / file
    text = source.read_text(encoding='utf-8')
    for target in re.findall(r'\[[^\]\n]*\]\(([^)\n]+)\)', text):
        target = target.strip().strip('<>')
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target):
            continue
        target = unquote(target)
        filename, _, anchor = target.partition('#')
        dest = (source.parent / filename).resolve() if filename else source
        checked += 1
        if not dest.exists():
            issues.append(f'{file}: missing {target}')
        elif anchor and dest.suffix == '.md' and anchor not in anchors(dest):
            issues.append(f'{file}: missing anchor {target}')

result = {'base_revision': '0aebf47', 'generated_files': len(generated), 'generated_sha256': generated, 'tomls_parsed': len(tomls), 'register_revisions_checked': revisions, 'changed_markdown_files': len(changed), 'local_links_checked': checked, 'issues': issues}
(OUT / 'runtime-root-declarations.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k != 'generated_sha256'}, indent=2))
raise SystemExit(bool(issues))


