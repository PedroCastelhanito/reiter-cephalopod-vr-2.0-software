"""Run only the old capture-stop method in an isolated pytest process."""
import ast
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import pytest
from cephvr.acquisition.worker import capture_runtime
source = subprocess.check_output(["git", "show", "HEAD:src/cephvr/acquisition/worker/capture_runtime.py"], text=True)
cls = next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef) and node.name == "WorkerCaptureResources")
method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "stop")
namespace = {}
exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), "<committed capture stop>", "exec"), capture_runtime.__dict__, namespace)
original = namespace["stop"]
def old_stop(self, *args, **kwargs):
    kwargs.pop("resumable", None)
    return original(self, *args, **kwargs)
capture_runtime.WorkerCaptureResources.stop = old_stop
# Restore the original mutable wait-limit field only in this isolated old-method run.
capture_runtime.WorkerCaptureResources._drain_until_ns = None
raise SystemExit(pytest.main(["tests/acquisition/test_worker_foundations.py", "-q", "-k", "terminal_stage", "--basetemp", str(Path.home() / "AppData/Local/Temp/cephvr-original-drain-proof"), "--tb=short"]))
