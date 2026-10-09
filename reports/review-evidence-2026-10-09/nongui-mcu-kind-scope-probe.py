import inspect
import textwrap
import tests.controller.test_microcontroller_owner as owner_tests

source = textwrap.dedent(inspect.getsource(owner_tests.test_owned_configuration_edit_scopes_candidate_microcontroller_write))
source = source.replace('test_owned_configuration_edit_scopes_candidate_microcontroller_write', 'probe', 1)
injection = '''
        physical_calls = []
        async def physical_on(roles, *, scheduled_boundary_ns, deadline_ns):
            physical_calls.append((roles, deadline_ns))
            return mcu.PulseCommandEvidence()
        owner.serial.on = physical_on
        stale_on = wire.MicrocontrollerIoRequest.FromString(request.SerializeToString())
        stale_on.command_id = 'wrong-kind-scoped-on'
        stale_on.kind = wire.MICROCONTROLLER_IO_KIND_ON
        stale_on.resolution_operation.command_id = 'stale-edit'
        stale_on.ClearField('requested_configuration_revision')
        result = await controller.execute(stale_on)
        print('stale_partial_scope_on:', result.succeeded, 'physical_on_calls=', physical_calls)
'''
source = source.replace('    async def _noop_warning(_warning) -> None:', injection + '\n    async def _noop_warning(_warning) -> None:')
namespace = dict(vars(owner_tests))
exec(compile(source, '<astra-mcu-kind-scope-probe>', 'exec'), namespace)
namespace['probe']()
