"""Reuse reviewed instrumentation with fresh paths and an explicit abort gate."""

from pathlib import Path
import shutil

OUT = Path(__file__).resolve().parent
for name in ("run.py", "monitor.py", "assess.py", "collect_run.py", "collect_parallel.py", "recover_startup.py", "live_state.py", "monitor_analysis.py", "offline_compile.py"):
    target = OUT / name
    if target.exists():
        raise RuntimeError(f"Preserve existing harness: {target}")
    shutil.copy2(OUT.parent / name, target)
path = OUT / "run.py"
source = path.read_text()
source = source.replace('parser.add_argument("--label", required=True)', 'parser.add_argument("--label", required=True)\nparser.add_argument("--abort-after", type=float)')
source = source.replace('case = "textures60" if args.mode == "configure" else args.mode', 'case = "combined120" if args.mode == "configure" else args.mode')
source = source.replace('                while client.snapshot.session.phase != pb.SESSION_PHASE_ENDED:', '''                abort_sent = False
                while client.snapshot.session.phase != pb.SESSION_PHASE_ENDED:
                    trial_start = client.snapshot.trial.start_monotonic_ns
                    if args.abort_after is not None and not abort_sent and trial_start and time.perf_counter_ns() >= trial_start + int(args.abort_after * 1e9):
                        abort_sent = True
                        keep("planned_abort_request", dict(observed_ns=time.perf_counter_ns(), trial_start_ns=trial_start, after_seconds=args.abort_after))
                        try:
                            await execute("AbortNow", timeout=90)
                        finally:
                            keep("abort_snapshot", view(client.snapshot))
                            (destination / "abort-snapshot.pb").write_bytes(client.snapshot.SerializeToString())''')
path.write_text(source)
path = OUT / "offline_compile.py"
path.write_text(path.read_text().replace('(\"textures60\", \"arena60\", \"combined60\", \"combined120\", \"combined900\")', '(\"combined120\", \"combined900\")'))
path = OUT / "collect_parallel.py"
path.write_text(path.read_text().replace('ROOT = Path(__file__).resolve().parents[3]', 'ROOT = Path.cwd()'))
