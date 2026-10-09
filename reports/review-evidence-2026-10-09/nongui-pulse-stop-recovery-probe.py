import asyncio, inspect, textwrap
from pathlib import Path
import tests.acquisition.test_manual_preview as owner
source=textwrap.dedent(inspect.getsource(owner.test_uncertain_preview_stop_switches_external_output_off_before_cleanup))
source=source.replace('test_uncertain_preview_stop_switches_external_output_off_before_cleanup','probe',1)
injection='''
    from cephvr.acquisition.coordinator.configuration_resolution import ConfigurationResolution
    from cephvr.acquisition.coordinator.manual_device_recovery import ManualDeviceRecovery
    from cephvr.acquisition.state import ConfigurationRecord, CoordinatorIdentity
    from cephvr.acquisition.v1 import runtime_pb2
    identity = CoordinatorIdentity(
        backend=control.BackendContext(backend_name="acquisition",backend_generation="acq"),
        process=control.ProcessIdentity(role="acquisition",generation="acq"),
        controller=control.ProcessIdentity(role="controller",generation="ctl"),
        supervisor=control.ProcessIdentity(role="supervisor",generation="sup"),
        tracking=control.ProcessIdentity(role="tracking",generation="trk"),
    )
    configuration=ConfigurationRecord(settings,runtime_pb2.AcquisitionFilePolicies(),revision=1)
    real_resolution=ConfigurationResolution(identity=identity,configuration=configuration,controller=SimpleNamespace(),lock=asyncio.Lock(),clock=lambda:5)
    worker.context=acq.WorkerContext(camera=camera.CAMERA_ROLE_BEHAVIORAL)
    worker.child_operations={}
    recovery=ManualDeviceRecovery(workers=flow.workers,resolution=real_resolution,pulse=flow.pulse,clock=lambda:5)
    def command(name):
        return wire.BackendCommand(command_id=name,issuer=identity.controller,target=identity.backend,parent_operation=control.OperationContext(command_id=name))
    failed=await real_resolution.begin(command("cancelled-pulse-edit"),expected_cameras=set(),request_revision=1,deadline_ns=100,expected_pulses=True,requested_pulses=settings.pulses,device_work_quiescent=lambda:recovery.device_work_quiescent(parent_command_id="cancelled-pulse-edit",required_preview_runs={camera.CAMERA_ROLE_BEHAVIORAL:preview.run_id},required_pulse_roles={camera.CAMERA_ROLE_BEHAVIORAL,camera.CAMERA_ROLE_TRACKING}))
    await real_resolution.cancel(failed)
    flow.resolution=real_resolution
'''
source=source.replace('    result = await ManualPreview._stop(flow, request, 1000)',injection+'\n    result = await ManualPreview._stop(flow, request, 1000)')
source+='''
    print("actual Stop success:",result.result==control.COMMAND_RESULT_ACCEPTED,"worker removed:",not flow.workers.workers,"pulse observation cleared:",flow.pulse.observation is None,"canceled resolution pending:",real_resolution._pending is not None)
    try:
        await real_resolution.begin(command("fresh-apply"),expected_cameras=set(),request_revision=1,deadline_ns=1000,allow_empty=True,accepted_base_revision=1,accepted_base_settings=settings,preexisting_work_quiescent=recovery.prior_device_work_quiescent)
    except RuntimeError as exc:
        print("fresh Apply resolution admission blocked:",str(exc))
    else:print("fresh Apply resolution admission succeeded")
'''
namespace=dict(vars(owner));exec(compile(source,'<sol-pulse-recovery>','exec'),namespace);asyncio.run(namespace['probe']())
