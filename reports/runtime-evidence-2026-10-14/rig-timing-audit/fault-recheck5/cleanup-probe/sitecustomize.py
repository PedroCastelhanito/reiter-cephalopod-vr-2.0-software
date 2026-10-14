"""Bounded Controller lifecycle trace for one authorized diagnostic run."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

if 'cephvr.controller.main' in ' '.join(sys.argv[1:]) and os.environ.get('CEPHVR_CLEANUP_TRACE'):
    manifest = json.loads((Path(sys.executable).parent / 'cephvr-python.runtime.json').read_text())
    handles = [os.add_dll_directory(x) for x in manifest['dll_directories']]
    try:
        from google.protobuf.json_format import MessageToDict

        from cephvr.controller.control.operations import ControlOperations
        from cephvr.controller.lifecycle.cleanup import CleanupWorkflow
        from cephvr.controller.lifecycle_reports import LifecycleReports

        _path = os.environ.get("CEPHVR_CLEANUP_TRACE")
        _lock = threading.Lock()
        _count = 0
        _maximum = 256

        def _dict(message: object) -> object:
            try:
                return MessageToDict(message, preserving_proto_field_name=True)
            except (TypeError, ValueError):
                return str(message)

        def _write(event: str, **fields: object) -> None:
            global _count
            if not _path:
                return
            try:
                with _lock:
                    if _count >= _maximum:
                        return
                    _count += 1
                    with Path(_path).open("a", encoding="utf-8") as stream:
                        stream.write(
                            json.dumps(
                                {
                                    "monotonic_ns": time.perf_counter_ns(),
                                    "event": event,
                                    **fields,
                                },
                                separators=(",", ":"),
                            )
                            + "\n"
                        )
            except OSError:
                return

        _receive = LifecycleReports.receive

        async def _receive_trace(self, report, ingress_ns):
            kind = report.WhichOneof("report")
            _write("lifecycle_report_received", report=_dict(report), ingress_ns=ingress_ns)
            try:
                receipt = await _receive(self, report, ingress_ns)
            except BaseException as exc:
                _write("lifecycle_report_exception", kind=kind, error=repr(exc))
                raise
            _write("lifecycle_report_receipt", kind=kind, receipt=_dict(receipt))
            return receipt

        LifecycleReports.receive = _receive_trace

        _dispatch = CleanupWorkflow.dispatch_backend_cleanup

        async def _dispatch_trace(self, attempt, deadline, method):
            _write(
                "backend_cleanup_begin",
                method=method,
                deadline_ns=deadline,
                session=_dict(attempt.context),
                backends=sorted(attempt.required),
            )
            saved = {}
            for name, backend in attempt.required.items():
                original = getattr(backend, method)
                saved[name] = original

                async def invoke(request, *, deadline_ns, _name=name, _original=original):
                    _write(
                        "backend_cleanup_call",
                        backend=_name,
                        method=method,
                        request=_dict(request),
                        deadline_ns=deadline_ns,
                    )
                    try:
                        result = await _original(request, deadline_ns=deadline_ns)
                    except BaseException as exc:
                        _write(
                            "backend_cleanup_exception",
                            backend=_name,
                            method=method,
                            error=repr(exc),
                        )
                        raise
                    _write(
                        "backend_cleanup_result",
                        backend=_name,
                        method=method,
                        result=_dict(result),
                    )
                    return result

                setattr(backend, method, invoke)
            try:
                result = await _dispatch(self, attempt, deadline, method)
                _write("backend_cleanup_complete", method=method, accepted=result)
                return result
            except BaseException as exc:
                _write("backend_cleanup_dispatch_exception", method=method, error=repr(exc))
                raise
            finally:
                for name, backend in attempt.required.items():
                    setattr(backend, method, saved[name])

        CleanupWorkflow.dispatch_backend_cleanup = _dispatch_trace

        _cancel_setup = CleanupWorkflow.cancel_setup

        async def _cancel_setup_trace(self, command):
            _write("cancel_setup_command", command=_dict(command))
            result = await _cancel_setup(self, command)
            _write("cancel_setup_admission", result=_dict(result))
            return result

        CleanupWorkflow.cancel_setup = _cancel_setup_trace

        _complete = ControlOperations.complete_operation

        def _complete_trace(
            self,
            command_id,
            *,
            success,
            progress,
            error="",
            failure_code="OPERATION_FAILED",
        ):
            result = _complete(
                self,
                command_id,
                success=success,
                progress=progress,
                error=error,
                failure_code=failure_code,
            )
            _write(
                "controller_operation_complete",
                command_id=command_id,
                success=success,
                progress=progress,
                error=error,
                failure_code=failure_code,
                operation=_dict(self.control.operations.get(command_id)),
            )
            return result

        ControlOperations.complete_operation = _complete_trace
    except (ImportError, AttributeError) as exc:
        sys.stderr.write(f"CephVR cleanup trace unavailable: {exc}\n")
