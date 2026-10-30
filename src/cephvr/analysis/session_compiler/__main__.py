"""CLI: ``python -m cephvr.analysis.session_compiler <folder> [options]``."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import CompileReport, Settings, compile_sessions, discover_sessions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="A session folder or a parent of many")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--output-root", type=Path, help="Write <session>.h5 here instead"
    )
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument(
        "--settings",
        type=Path,
        help="Pre-processing settings JSON saved by the inspection notebook",
    )
    parser.add_argument(
        "--no-probe-sync", action="store_true", help="Skip imec SY reads"
    )
    parser.add_argument(
        "--camera-latency-ms",
        nargs=2,
        type=float,
        metavar=("MIN", "MAX"),
        help="Measured exposure-start to host-receipt latency window (A09 offset choice)",
    )
    args = parser.parse_args(argv)
    sessions = discover_sessions(args.root)
    if not sessions:
        parser.error(f"no sessions under {args.root}")
    overrides: dict[str, object] = {
        "overwrite": args.overwrite,
        "output_root": args.output_root,
    }
    if args.camera_latency_ms:
        low, high = args.camera_latency_ms
        overrides["camera_latency_s"] = (low / 1e3, high / 1e3)
    if args.no_probe_sync:
        overrides["probe_sync"] = False
    settings = (
        Settings.load(args.settings, **overrides)
        if args.settings
        else Settings(**overrides)  # type: ignore[arg-type]
    )

    def show(report: CompileReport) -> None:
        print(
            f"{report.name}: {report.status} ({report.duration_s:.1f} s) {report.error}"
        )
        for warning in report.warnings:
            print(f"    {warning}")

    reports = compile_sessions(
        sessions, settings, max_workers=args.workers, on_report=show
    )
    return 0 if all(r.ok for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
