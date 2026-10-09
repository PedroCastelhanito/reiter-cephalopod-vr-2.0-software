import asyncio
from tests.acquisition.test_coordinator import _retained_operation_test_owner, _retained_operation_report
from cephvr.acquisition.v1 import messages_pb2 as acq

async def run():
    owner = await _retained_operation_test_owner(late_started=True)
    owner.child.kind = 'prepare_preview'
    preview = owner.record.preview
    preview.preparation = preview.start_operation
    preview.start_operation = None
    retained = _retained_operation_report(owner, late_started=True)
    retained.operation.operation.command = 'PreparePreview'
    retained.ClearField('lifecycle')
    retained.lifecycle.add(source=owner.context, operation=retained.operation.operation.context, state_revision=1, ready=acq.WorkerReadyEvidence(configuration_revision=1, required_checks_passed=True))
    accepted = await owner.evidence.reconcile_retained_operation(owner.record, owner.child, retained, deadline_ns=900, ingress_ns=500)
    print('late_prepare_query:', accepted, 'terminal_retained=', owner.child.report is not None, 'pending_resolution=', owner.resolution._pending is not None, 'preview_started=', preview.started)
    direct = await owner.evidence.report_lifecycle(retained.lifecycle[0], deadline_ns=900, ingress_ns=500)
    print('lifecycle rejection:', direct.failure.code, direct.failure.message)
    retained.ClearField('lifecycle')
    accepted = await owner.evidence.reconcile_retained_operation(owner.record, owner.child, retained, deadline_ns=900, ingress_ns=500)
    print('same_exact_terminal_without_late_ready:', accepted, 'terminal_retained=', owner.child.report is not None, 'pending_resolution=', owner.resolution._pending is not None)

asyncio.run(run())
