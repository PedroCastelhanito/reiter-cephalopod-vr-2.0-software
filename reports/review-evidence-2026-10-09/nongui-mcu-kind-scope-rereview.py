from pathlib import Path
source=Path('/tmp/cephvr-astra-mcu-kind-scope-probe.py').read_text()
source=source.replace("        result = await controller.execute(stale_on)\n        print('stale_partial_scope_on:', result.succeeded, 'physical_on_calls=', physical_calls)","""        with pytest.raises(ValueError, match='only valid for Configure'):
            await controller.execute(stale_on)
        assert physical_calls == []
        assert owner.claim_id == 'claim' and owner.acquisition_claimed
        assert owner.boundaries == {}
        print('Astra stale partial scoped ON rejected before physical serial')
        ordinary_off = wire.MicrocontrollerIoRequest.FromString(request.SerializeToString())
        ordinary_off.command_id = 'ordinary-unscoped-off'
        ordinary_off.kind = wire.MICROCONTROLLER_IO_KIND_OFF
        ordinary_off.ClearField('resolution_operation')
        ordinary_off.ClearField('requested_configuration_revision')
        result = await controller.execute(ordinary_off)
        assert result.succeeded and serial_effects == ['off']
        assert owner.claim_id == 'claim' and owner.acquisition_claimed
        print('Unscoped OFF remains accepted through real lifecycle/device')""")
exec(compile(source,'<sol-astra-mcu-rereview>','exec'))
