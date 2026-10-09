import asyncio,inspect,textwrap,tempfile
from pathlib import Path
import tests.controller.test_camera_configuration as owner
source=textwrap.dedent(inspect.getsource(owner.test_controller_recovers_expired_owned_edit_status_before_camera_stop))
source=source.replace('test_controller_recovers_expired_owned_edit_status_before_camera_stop','probe',1)
source=source.replace('        started=True,','        started=False,')
source=source.replace('        preview_prepared=True,\n        preview_running=True,\n        preview_run_id=run_id,\n        cleanup_pending=True,','        preview_prepared=False,\n        preview_running=False,\n        preview_run_id=run_id,\n        cleanup_pending=True,')
source=source.replace('    class _DeviceStatus:\n        def reserve', '    class _DeviceStatus:\n        def update_camera_state(self,*args,**kwargs):\n            pass\n\n        def reserve')
source=source.replace('    manual.resources = {}','''    async def retire_sessionless_worker(role, *, deadline_ns):
        assert role == acquisition_camera_pb.CAMERA_ROLE_TRACKING
        assert worker.preview is preview and preview.run_id == run_id
        manual.workers.workers.pop(role)
    manual.workers.retire_sessionless_worker = retire_sessionless_worker
    manual.resources = {}''')
source=source.replace('    for task in tuple(runtime._tasks):','    print("expired nonrunning cleanup identity recovered and exact Stop accepted:",request_matches_reported_run, admission.result,"query count:",len(controller_backend.retained_queries),"worker removed:",not manual.workers.workers,"accepted config revision:",runtime.configuration_state.revision)\n    for task in tuple(runtime._tasks):')
ns=dict(vars(owner));exec(compile(source,'<sol-pending-run-real-query>','exec'),ns)
async def run():
 for match in (False,True):
  with tempfile.TemporaryDirectory(prefix='cephvr-sol-pending-run-') as directory:
   await ns['probe'](Path(directory),None,match)
asyncio.run(run())
