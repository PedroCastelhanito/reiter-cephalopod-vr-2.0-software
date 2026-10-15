"""Opt-in startup/stack evidence for this bounded audit generation only."""

import faulthandler
import os
from pathlib import Path
import sys

destination = os.environ.get("CEPHVR_AUDIT_STACKS")
if destination and "cephvr" in sys.executable.lower():
    root = Path(destination)
    root.mkdir(exist_ok=True)
    stream = (root / f"process-{os.getpid()}.txt").open("a", encoding="utf-8", buffering=1)
    stream.write(f"executable={sys.executable}\nargv={sys.argv!r}\n")
    sys.stderr = stream
    faulthandler.enable(file=stream)
    faulthandler.dump_traceback_later(30, repeat=True, file=stream)
    import asyncio

    original_run = asyncio.run

    def traced_run(coro, **kwargs):
        async def traced():
            loop = asyncio.get_running_loop()

            def task_dump():
                stream.write("\nASYNC TASK CHAINS\n")
                for task in asyncio.all_tasks(loop):
                    stream.write(f"TASK {task.get_name()}\n")
                    current = task.get_coro()
                    while current is not None:
                        frame = getattr(current, "cr_frame", None) or getattr(current, "gi_frame", None)
                        if frame is not None:
                            stream.write(f"  {frame.f_code.co_filename}:{frame.f_lineno} {frame.f_code.co_name}\n")
                        current = getattr(current, "cr_await", None) or getattr(current, "gi_yieldfrom", None)
                loop.call_later(15, task_dump)

            loop.call_later(15, task_dump)
            return await coro

        return original_run(traced(), **kwargs)

    asyncio.run = traced_run
