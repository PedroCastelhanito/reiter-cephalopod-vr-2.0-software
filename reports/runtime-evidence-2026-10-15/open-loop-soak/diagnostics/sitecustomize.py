"""Opt-in file routing of existing renderer metrics; no workload hooks."""

import logging
import os
from pathlib import Path
import sys

if any("cephvr.visual_stimulus.worker.main" in value for value in sys.argv):
    output = os.environ.get("CEPHVR_OPEN_LOOP_DIAGNOSTICS")
    if output:
        root = Path(output)
        sys.stderr = (root / f"renderer-stderr-{os.getpid()}.txt").open("a", encoding="utf-8", buffering=1)
        handler = logging.FileHandler(root / f"renderer-metrics-{os.getpid()}.jsonl", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger = logging.getLogger("cephvr.visual_stimulus.recording.session")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False
