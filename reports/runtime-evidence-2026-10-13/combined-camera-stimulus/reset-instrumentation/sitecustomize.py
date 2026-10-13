"""Diagnostic-only rejected controller warning payload capture."""
import json
import os
from pathlib import Path
import sys

if 'cephvr.controller.main' in sys.argv:
    manifest=json.loads((Path(sys.executable).parent/'cephvr-python.runtime.json').read_text())
    handles=[os.add_dll_directory(path) for path in manifest['dll_directories']]
    from cephvr.controller.projections import ProjectionStore
    from google.protobuf.json_format import MessageToDict
    original=ProjectionStore.accept_warnings
    def accept(self, report):
        try:
            return original(self,report)
        except Exception:
            data=dict(report=MessageToDict(report,preserving_proto_field_name=True),current_work=MessageToDict(self.work,preserving_proto_field_name=True),revision=self.configuration_revision,
                previous_trial=MessageToDict(self.previous_trial,preserving_proto_field_name=True) if self.previous_trial else None)
            with Path(os.environ['CEPHVR_RESET_OUTPUT']).open('a') as stream:
                stream.write(json.dumps(data)+'\n')
            raise
    ProjectionStore.accept_warnings=accept

if 'cephvr.acquisition.main' in sys.argv and os.environ.get('CEPHVR_HEARTBEAT_OUTPUT'):
    manifest=json.loads((Path(sys.executable).parent/'cephvr-python.runtime.json').read_text())
    handles=[os.add_dll_directory(path) for path in manifest['dll_directories']]
    from cephvr.acquisition.coordinator.evidence_telemetry import WorkerTelemetryReports
    from google.protobuf.json_format import MessageToDict
    original_heartbeat=WorkerTelemetryReports.report_heartbeat
    async def heartbeat(self, report, **kwargs):
        receipt=await original_heartbeat(self,report,**kwargs)
        if receipt.failure.code:
            session=self.current_session()
            record=next((r for r in self.workers.values() if r.launch.worker==report.source),None)
            data=dict(report=MessageToDict(report,preserving_proto_field_name=True),failure=receipt.failure.message,kwargs=kwargs,
                expected_work=MessageToDict(session.trial.work if session and session.trial else session.work,preserving_proto_field_name=True) if session else None,
                previous=MessageToDict(record.heartbeat,preserving_proto_field_name=True) if record and record.heartbeat else None,
                preparation=MessageToDict(record.trial.preparation,preserving_proto_field_name=True) if record and record.trial and record.trial.preparation else None,
                child_operations=[dict(kind=c.kind,deadline_ns=c.deadline_ns,work=MessageToDict(c.work,preserving_proto_field_name=True),parent=MessageToDict(c.parent_operation,preserving_proto_field_name=True)) for c in record.child_operations.values()] if record else [])
            with Path(os.environ['CEPHVR_HEARTBEAT_OUTPUT']).open('a') as stream: stream.write(json.dumps(data)+'\n')
        return receipt
    WorkerTelemetryReports.report_heartbeat=heartbeat
