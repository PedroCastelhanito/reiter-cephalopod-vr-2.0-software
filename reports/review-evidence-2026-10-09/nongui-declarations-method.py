from pathlib import Path
import datetime,hashlib,json,re,tomllib
paths=[p for root in ('config','contracts') for p in Path(root).rglob('*.toml')]
for p in paths: tomllib.loads(p.read_text())
revisions={'A07':59,'A08':50,'A10':57,'A11':41,'E13':20,'V12':11,'V28':5}
register=Path('architecture.md').read_text()
for decision,revision in revisions.items():
 source=Path('docs/architecture/acquisition.md' if decision.startswith('A') else 'docs/architecture/visual_stimulus.md')
 section=source.read_text().split(f'<a id="{decision.lower()}"></a>',1)[1]
 actual=int(re.search(r'\*\*Revision:\*\* (\d+)',section).group(1))
 assert actual==revision,(decision,actual,revision)
 row=next(s for s in register.splitlines() if s.startswith(f'| <a id="{decision.lower()}"></a>'))
 assert row.rstrip().endswith(f'| {revision} |'),row
files=[Path('architecture.md'),Path('docs/architecture/acquisition.md'),Path('docs/architecture/visual_stimulus.md'),*paths]
r={'date_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'Parse all config/contract TOMLs with Python3.11 tomllib; compare each revised owning decision revision to its root register row.','toml_files':len(paths),'matched_decision_revisions':revisions,'sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
Path('reports/review-evidence-2026-10-09/nongui-declarations-check.json').write_text(json.dumps(r,indent=2)+'\n')
print(len(paths),'TOMLs parsed;',len(revisions),'decision revisions match register')
