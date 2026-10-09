import asyncio
import inspect
import tempfile
import textwrap
from pathlib import Path
import tests.controller.test_camera_configuration as owner
source=textwrap.dedent(inspect.getsource(owner.test_empty_edit_uses_real_acquisition_status_and_completion_path))
source=source.replace('async def test_empty_edit_uses_real_acquisition_status_and_completion_path(', 'async def repro(')
source=source.replace('    runtime = _runtime_with_validators(tmp_path)', '    runtime = _runtime_with_validators(tmp_path)\n    runtime.configuration_commands.owned_edits.limits.current = __import__("dataclasses").replace(runtime.configuration_commands.owned_edits.limits.current, setup_ns=100_000_000, recovery_ns=1_000_000)',1)
source=source.split('    backend.confirmation_gate.set()')[0]
source+='''    admission = await asyncio.wait_for(update, 2)
    print('controller update accepted:', admission.result == pb.COMMAND_RESULT_ACCEPTED)
    print('controller/backend revision:', runtime.configuration_state.revision, configuration.revision)
    bridge.status_gate.set()
    await backend.transport.close(host_time_ns() + 2_000_000_000)
    print('first terminal status receipt:', bridge.status_receipt)
    print('first failed parent receipt:', bridge.lifecycle_receipt)
    pending = resolution._pending
    print('terminal resolution retained:', pending is not None and pending.confirmed.is_set(), 'failure:', pending.failure if pending else None)
    retry = svc.AcquisitionCameraSettingsCommand.FromString(backend.request.SerializeToString())
    retry.command.command_id = _id()
    retry.command.parent_operation.command_id = _id()
    retry.configuration_revision = runtime.configuration_state.revision
    retry.accepted_base_revision = runtime.configuration_state.revision
    retry.accepted_base_settings.CopyFrom(runtime.configuration_state.current.backends[0].acquisition)
    new_deadline = host_time_ns() + 2_000_000_000
    commands.admit(retry.command.command_id, b'retry-current-base', host_time_ns(), work_key=retry.command.command_id, deadline_ns=new_deadline)
    retry_admission = await manual.apply(retry, deadline_ns=new_deadline)
    print('fresh current-base edit:', retry_admission)
'''
namespace=dict(vars(owner))
exec(compile(source,'/tmp/cephvr-owned-expired-repro-derived.py','exec'),namespace)
with tempfile.TemporaryDirectory(prefix='cephvr-expired-') as temporary:
    asyncio.run(namespace['repro'](Path(temporary)))
