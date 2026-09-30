"""Controller process entry point for the supervisor's inherited-pipe bootstrap."""

from __future__ import annotations

import argparse
import asyncio
import sys

from cephvr.controller.startup.application import run_controller


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CephVR controller supervised process")
    parser.add_argument("--bootstrap-handle", type=int, required=True)
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        parser.error("supervised controller bootstrap requires Windows")
    from cephvr.platform.windows.bootstrap import read_bootstrap
    from cephvr.platform.windows.guard import SingleInstanceGuard

    with SingleInstanceGuard("controller"):
        bootstrap = read_bootstrap(args.bootstrap_handle)
        asyncio.run(run_controller(bootstrap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
