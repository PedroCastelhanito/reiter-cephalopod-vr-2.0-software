import asyncio,inspect,textwrap
from pathlib import Path
import tests.acquisition.test_manual_devices as owner
from cephvr.acquisition.microcontroller_client import ControllerMicrocontrollerClient
from cephvr.controller.microcontroller.device import MicrocontrollerDevice
from cephvr.controller.microcontroller.lifecycle import MicrocontrollerLifecycle
from cephvr.controller.state import ConfigurationEdit,ConfigurationEditTerminal,ConfigurationState,DeviceState,LifecycleState
from cephvr.shared.auth import Principal
source=textwrap.dedent(inspect.getsource(owner.test_pulse_only_edit_uses_exact_resolution_and_terminal_status))
source=source.replace('def test_pulse_only_edit_uses_exact_resolution_and_terminal_status()', 'def probe()',1)
needle='    manual = ManualDevices('
injection='''    current = control.ExperimentConfiguration()
    current.backends.add(backend_name="acquisition").acquisition.CopyFrom(settings)
    candidate = control.ExperimentConfiguration.FromString(current.SerializeToString())
    candidate.backends[0].acquisition.pulses.CopyFrom(edited)
    controller_config = ConfigurationState(current=current,policies=control.ControlPolicies(),revision=7)
    edit = ConfigurationEdit(command=wire.OperatorCommand(),command_id="operator-edit",operation_id=request.command.command_id,revision=7,deadline_ns=host_time_ns()+6_000_000_000,expected_cameras=frozenset(),expect_pulses=True,proposed=candidate)
    device = DeviceState(configuration_edit=edit)
    device.configuration_edit_terminals[edit.operation_id]=ConfigurationEditTerminal(operation_id=edit.operation_id,source=backend,deadline_ns=edit.deadline_ns)
    actual_device = MicrocontrollerDevice(_Serial(),control.AcquisitionSettings.FromString(settings.SerializeToString()),policies,lambda:10)
    async def noop(*args): pass
    gate = MicrocontrollerLifecycle(actual_device,generation=controller_identity.generation,lifecycle=LifecycleState(),configuration=controller_config,device=device,limits=SimpleNamespace(current=SimpleNamespace(setup_ns=100)),clock=lambda:10,publish=lambda:None,warning=noop,interrupt=noop,spawn=asyncio.create_task)
    received=[]
    class Stub:
        async def ExecuteMicrocontrollerIo(self,io_request,**kwargs):
            received.append(wire.MicrocontrollerIoRequest.FromString(io_request.SerializeToString()))
            return await gate.execute(io_request)
    client = ControllerMicrocontrollerClient(Stub(),Principal("acquisition",backend.backend_generation,"token"),controller_identity.generation,lambda:settings.pulses,clock=lambda:10)
'''
source=source.replace(needle,injection+needle)
source=source.replace('        serial=_Serial(),','        serial=client,')
# The controller device consumes the scope before calling its unscoped physical owner.
source=source.replace('            assert requested == edited','            assert requested == edited\n            assert device.camera_operation is not None\n            assert controller_config.revision == 7\n            assert controller_config.current.backends[0].acquisition.pulses == settings.pulses')
source += '''\n    configure = next(x for x in received if x.kind == wire.MICROCONTROLLER_IO_KIND_CONFIGURE)
    assert configure.resolution_operation.command_id == request.command.command_id
    assert configure.requested_configuration_revision == request.configuration_revision
    assert configure.requester.generation == backend.backend_generation
    assert actual_device.claim_id == client.claim_id
    assert device.camera_operation is None
    assert controller_config.current.backends[0].acquisition.pulses == settings.pulses
    print("ManualDevices.apply -> typed client -> real lifecycle/device: candidate25 configured, exact scope7/operation/claim; accepted20 retained")
'''
source=source.replace('    assert admission.result == control.COMMAND_RESULT_ACCEPTED','    assert admission.result == control.COMMAND_RESULT_ACCEPTED, admission.failure.message')
Path('/tmp/cephvr-sol-mcu-client-integration-derived.py').write_text(source)
ns=dict(vars(owner));ns.update(globals());exec(compile(source,'<sol-mcu-integration>','exec'),ns);ns['probe']()
