"""Trace original production waits without changing fixture gates or assertions."""

import asyncio
import json
import sys

import pytest

from cephvr.acquisition.coordinator.configuration_resolution import ConfigurationResolution
from cephvr.acquisition.coordinator.manual_operation_results import ManualOperationResults
from cephvr.shared.clock import host_time_ns


def trace(event, **values):
    print(json.dumps({"event": event, **values}), flush=True)


original_wait = ConfigurationResolution.wait_confirmed
original_status = ManualOperationResults.report_failure
original_failure = ManualOperationResults.report_operation_failure


async def traced_wait(self, operation, *, deadline_ns):
    trace("wait_enter", remaining_ns=deadline_ns - self.clock())
    try:
        return await original_wait(self, operation, deadline_ns=deadline_ns)
    except BaseException as error:
        trace(
            "wait_exception",
            error=repr(error),
            error_type=type(error).__name__,
            remaining_ns=deadline_ns - self.clock(),
            loop_time_ns=round(asyncio.get_running_loop().time() * 1e9),
            host_time_ns=host_time_ns(),
        )
        raise


async def traced_status(self, command, **kwargs):
    trace(
        "status_failure_enter",
        remaining_ns=kwargs["deadline_ns"] - self.device_status.clock(),
        failure=kwargs["failure"],
    )
    result = await original_status(self, command, **kwargs)
    trace(
        "status_failure_return",
        remaining_ns=kwargs["deadline_ns"] - self.device_status.clock(),
    )
    return result


async def traced_failure(self, command, **kwargs):
    trace(
        "lifecycle_failure_enter",
        remaining_ns=kwargs["deadline_ns"] - self.device_status.clock(),
        failure=kwargs["failure"],
    )
    result = await original_failure(self, command, **kwargs)
    trace("lifecycle_failure_return", accepted=result)
    return result


ConfigurationResolution.wait_confirmed = traced_wait
ManualOperationResults.report_failure = traced_status
ManualOperationResults.report_operation_failure = traced_failure

raise SystemExit(
    pytest.main(
        [
            "tests/controller/test_camera_configuration.py::test_empty_edit_uses_real_acquisition_status_and_completion_path[True]",
            "-q",
            "-s",
            "--basetemp=" + sys.argv[1],
            "-o",
            "faulthandler_timeout=10",
        ]
    )
)
