"""Windows supervisor command entry point."""

from __future__ import annotations

import argparse
import asyncio
import os

from cephvr.platform.windows.bootstrap import read_bootstrap
from cephvr.platform.windows.guard import SingleInstanceGuard
from cephvr.supervisor.startup import run_supervisor


def main() -> None:
    parser = argparse.ArgumentParser(description="CephVR supervisor")
    parser.add_argument("--bootstrap-handle", type=int, required=True)
    parser.add_argument("--launcher-control-handle", type=int, required=True)
    parser.add_argument("--launcher-controller-control-handle", type=int, required=True)
    parser.add_argument("--launcher-ack-handle", type=int, required=True)
    args = parser.parse_args()
    descriptor = read_bootstrap(args.bootstrap_handle)
    # The retained inherited handle is the local generation-bound launcher channel.
    import msvcrt

    control_fd = msvcrt.open_osfhandle(args.launcher_control_handle, os.O_WRONLY)
    ack_fd = msvcrt.open_osfhandle(args.launcher_ack_handle, os.O_RDONLY)
    with SingleInstanceGuard("supervisor"):
        asyncio.run(
            run_supervisor(
                descriptor,
                control_fd,
                ack_fd,
                args.launcher_controller_control_handle,
            )
        )


if __name__ == "__main__":
    main()
