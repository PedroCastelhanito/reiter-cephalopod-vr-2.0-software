import asyncio,inspect,textwrap
from pathlib import Path
import tests.controller.test_microcontroller_owner as owner
from cephvr.acquisition.microcontroller_client import ControllerMicrocontrollerClient
from cephvr.shared.auth import Principal
source=textwrap.dedent(inspect.getsource(owner.test_owned_configuration_edit_scopes_candidate_microcontroller_write))
source=source.replace('test_owned_configuration_edit_scopes_candidate_microcontroller_write','probe',1)
injection='''
        forwarded=[]
        class Stub:
            async def ExecuteMicrocontrollerIo(self, request, **kwargs):
                forwarded.append(request)
                return await controller.execute(request)
        client=ControllerMicrocontrollerClient(Stub(),Principal("acquisition",acquisition_generation,"token"),"controller-gen",lambda:configuration.current.backends[0].acquisition.pulses,clock=lambda:now)
        client.claim_id="claim"
        async def configure(pulses, *, op="edit-op", revision=7, roles=(camera.CAMERA_ROLE_BEHAVIORAL,), deadline=200):
            return await client.configure(pulses,active_roles=roles,deadline_ns=deadline,resolution_operation=control.OperationContext(command_id=op) if op is not None else None,requested_configuration_revision=revision)
        await configure(candidate_pulses)
        print("real client scoped candidate forwarded, real controller/device accepted")
        for label,kwargs in [("old-scope",{"op":"old-op"}),("revision",{"revision":6}),("over-bound",{"deadline":201}),("partial-pair",{"revision":None}),("duplicate-role",{"roles":(camera.CAMERA_ROLE_BEHAVIORAL,camera.CAMERA_ROLE_BEHAVIORAL)}),("unsupported-role",{"roles":(0,)})]:
            before=len(calls)
            with pytest.raises((ValueError,RuntimeError)):
                await configure(candidate_pulses,**kwargs)
            assert len(calls)==before
            print(label,"rejected before physical serial")
        accepted=configuration.current.backends[0].acquisition.pulses
        with pytest.raises(ValueError):await configure(accepted,op="old-op")
        await configure(accepted,op=None,revision=None)
        print("unscoped accepted configuration allowed; stale scope with accepted bytes rejected")
        client.claim_id="wrong-claim"
        before=len(calls)
        with pytest.raises(RuntimeError):await configure(candidate_pulses)
        assert len(calls)==before
        client.claim_id="claim"
        print("wrong exact claim rejected")
        candidate_pulses.port="COM9"
        edit.proposed.backends[0].acquisition.pulses.CopyFrom(candidate_pulses)
        before=len(calls)
        with pytest.raises(ValueError,match="different configured port"):
            await configure(candidate_pulses)
        assert len(calls)==before
        print("bound candidate cannot switch owned port implicitly")
        assert device.camera_operation is None
'''
needle='    async def _noop_warning(_warning) -> None:'
source=source.replace(needle,injection+'\n'+needle)
source=source.replace('acq-gen','123e4567-e89b-42d3-a456-426614174000')
ns=dict(vars(owner));ns.update(globals());exec(compile(source,'<sol-mcu-matrix>','exec'),ns);ns['probe']()
