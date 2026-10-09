import asyncio,inspect,textwrap,tempfile
from pathlib import Path
import tests.controller.test_camera_configuration as owner
source=textwrap.dedent(inspect.getsource(owner.test_controller_can_stop_exact_late_preview_run_after_lost_edit))
source=source.replace('test_controller_can_stop_exact_late_preview_run_after_lost_edit','probe',1)
source=source.replace('    runtime.projections.devices.tracking.preview_run_id = run_id','    runtime.projections.devices.tracking.preview_run_id = run_id\n    runtime.projections.devices.tracking.preview_running = False\n    runtime.projections.devices.tracking.cleanup_pending = True')
source=source.replace('        started=True,','        started=False,')
source=source.replace('    assert admission.result == pb.COMMAND_RESULT_ACCEPTED, admission.failure.message\n    assert worker.preview is None\n    assert resolution._pending is None','    print("exact cleanup-pending nonrunning run Stop:",admission.result,"reason:",admission.failure.message,"backend run still owned:",worker.preview is not None)')
namespace=dict(vars(owner));exec(compile(source,'<sol-controller-stop-gate>','exec'),namespace)
with tempfile.TemporaryDirectory(prefix='cephvr-sol-stop-gate-') as directory:asyncio.run(namespace['probe'](Path(directory)))
