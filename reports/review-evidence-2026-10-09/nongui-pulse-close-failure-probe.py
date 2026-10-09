from pathlib import Path
script=Path('/tmp/cephvr-sol-pulse-stop-recovery-probe.py').read_text()
old="namespace=dict(vars(owner));exec(compile(source,'<sol-pulse-recovery>','exec'),namespace);asyncio.run(namespace['probe']())"
new="""
source=source.replace('    result = await ManualPreview._stop(flow, request, 1000)', '    flow.serial.close.side_effect = RuntimeError("native close remains uncertain")\\n    flow.results.report_failure = AsyncMock()\\n    result = await ManualPreview._stop(flow, request, 1000)')
source=source.replace('    result = await ManualPreview._stop(flow, request, 1000)', '    flow.device_status.update_camera_state=lambda *args, **kwargs:None\\n    result = await ManualPreview._stop(flow, request, 1000)')
start=source.index('    assert result.result == control.COMMAND_RESULT_ACCEPTED')
end=source.index('    print("actual Stop success:')
source=source[:start]+source[end:]
source=source.replace('    try:\\n        await real_resolution.begin', '    await real_resolution.retire_failed_if_quiescent()\\n    print("fresh caller quiet reconciliation retired despite failed close:",real_resolution._pending is None)\\n    try:\\n        await real_resolution.begin')
namespace=dict(vars(owner));exec(compile(source,'<sol-pulse-close-failure>','exec'),namespace);asyncio.run(namespace['probe']())
"""
assert old in script
exec(compile(script.replace(old,new),'<sol-pulse-close-failure-builder>','exec'))
