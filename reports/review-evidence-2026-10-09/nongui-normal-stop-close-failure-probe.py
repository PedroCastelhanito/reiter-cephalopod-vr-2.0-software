import asyncio,inspect,textwrap
import pytest
import tests.acquisition.test_manual_preview as owner
source=textwrap.dedent(inspect.getsource(owner.test_preview_disconnect_releases_only_last_external_camera_claim))
source=source.replace('test_preview_disconnect_releases_only_last_external_camera_claim','probe',1)
source=source[:source.index('    assert result.result == control.COMMAND_RESULT_ACCEPTED')]
source=source.replace('    result = await ManualPreview._stop(flow, request, 1000)', '''    flow.device_status.update_camera_state = MagicMock()
    flow.results.report_failure = AsyncMock()
    serial.close.side_effect = RuntimeError("same-claim native CLOSE unconfirmed")
    result = await ManualPreview._stop(flow, request, 1000)
    print("normal worker Stop completed:",events == ["camera stopped"],"preview stopped:",not preview.started,"Stop caller failed:",result.result == control.COMMAND_RESULT_REJECTED)
    print("failed device view:",flow.device_status.update_camera_state.call_args.kwargs)
''')
namespace=dict(vars(owner));exec(compile(source,'<sol-normal-stop-close>','exec'),namespace)
patch=pytest.MonkeyPatch()
try:asyncio.run(namespace['probe'](patch,False))
finally:patch.undo()
