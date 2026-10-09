"""Record final non-GUI cohort provenance and exact local validation evidence."""
from pathlib import Path
import datetime, hashlib, json, subprocess
repo = Path.cwd()
evidence = repo / 'reports/review-evidence-2026-10-09'
source = json.loads((evidence / 'nongui-source-hashes.json').read_text())
results = {}
for path in sorted(evidence.glob('nongui-*.result.json')):
    results[path.name] = json.loads(path.read_text())
governance = ['AGENTS.md', 'TODO.md', 'LOG.md', 'architecture.md', 'docs/architecture/acquisition.md', 'docs/architecture/visual_stimulus.md', 'docs/architecture/system-contracts.md', 'reports/runtime.md', 'reports/acquisition.md', 'reports/visual_stimulus.md', 'reports/rig-verification.md']
record = {
    'recorded_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'source_state': 'Pre-existing dirty worktree preserved. nongui-source.patch records only this non-GUI cohort against its hashed start, including prior dirty-file reconstruction; it is not a full patch from HEAD. The exact dirty start content of test_worker_foundations.py could not be recovered: its declared start/final hashes are retained, and nongui-worker-foundations-head.patch separately records HEAD-to-final, which may include earlier edits. Earlier implementation-context.json and implementation.patch describe the preceding repair cohort.',
    'scope': 'Authorized local non-GUI TODO implementation, including lifted shared-launch/execution/deadline deferrals, owned-camera edits and accepted first-usable-slot/leading-backfill video mapping. No GUI source/test modifications in this cohort.',
    'models': {'implementation': 'gpt-6-luna', 'interpretation': 'gpt-6.1-sol', 'review': 'gpt-6-astra'},
    'source_manifest': 'nongui-source-hashes.json',
    'source_patch': 'nongui-source.patch',
    'baseline_exceptions': source['baseline_unavailable'],
    'final_validation_inputs': 'nongui-final-input-hashes.json',
    'gui_source_test_files_unchanged': source['gui_files_unchanged'],
    'commands': results,
    'generation_and_declarations': ['nongui-protobuf-check.json', 'nongui-declarations-check.json'],
    'review_evidence': [p.name for p in sorted(evidence.glob('nongui-*.txt')) if any(s in p.name for s in ('luna', 'sol', 'astra'))],
    'governance_sha256': {p: hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in governance},
    'cleanup': 'cleanup.json',
    'limitations': ['Portable/offscreen tests and Windows-target static analysis do not establish Windows-native, SDK, serial, electrical, optical, encoder compatibility, throughput or full-workload acceptance.', 'Native/rig/remote/scientific and firmware deferrals remain in TODO.md and reports/rig-verification.md. No hardware, running managed runtime, remote SpikeGLX or native GUI interaction was performed for this cohort.', 'Scoped test selections overlap; do not sum their counts. Earlier failures and corrections remain in LOG.md and raw review evidence.', 'No commit or push was requested or performed.'],
}
(evidence / 'nongui-context.json').write_text(json.dumps(record, indent=2)+'\n')
print('Saved final context:', len(results), 'command results;', source['gui_files_unchanged'], 'GUI files unchanged')
