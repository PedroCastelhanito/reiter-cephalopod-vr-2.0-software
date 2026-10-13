"""Diagnostic-only first activity/operation timings; no lifecycle behavior changes."""
import functools
import json
import os
from pathlib import Path
import sys
import time

if 'cephvr.acquisition.worker.main' in sys.argv:
    manifest=json.loads((Path(sys.executable).parent/'cephvr-python.runtime.json').read_text())
    handles=[os.add_dll_directory(p) for p in manifest['dll_directories']]
    from cephvr.acquisition.worker.execution import WorkerOperationExecutor
    from cephvr.acquisition.worker.capture_runtime import WorkerCaptureResources
    from cephvr.acquisition.worker.trial_lifecycle import WorkerTrialLifecycle
    destination=Path(os.environ['CEPHVR_START_OUTPUT'])/f'start-{os.getpid()}.jsonl'
    def event(kind, **values):
        with destination.open('a') as stream:stream.write(json.dumps(dict(kind=kind,host_ns=time.perf_counter_ns(),**values))+'\n')
    def wrap(cls, name, first_only=False):
        original=getattr(cls,name)
        observed=set()
        @functools.wraps(original)
        def call(self,*args,**kwargs):
            if first_only and id(self) in observed:return original(self,*args,**kwargs)
            observed.add(id(self))
            detail=str(args[0])[:300] if args else ''
            event(name+'_begin', detail=detail)
            try:return original(self,*args,**kwargs)
            except BaseException as error:
                event(name+'_failure',error=str(error));raise
            finally:event(name+'_end')
        setattr(cls,name,call)
    wrap(WorkerOperationExecutor,'execute')
    wrap(WorkerCaptureResources,'start')
    wrap(WorkerTrialLifecycle,'camera_first_frame',True)
    wrap(WorkerTrialLifecycle,'recording_first_frame',True)
    event('instrumentation',argv=sys.argv)

if 'cephvr.acquisition.main' in sys.argv:
    manifest=json.loads((Path(sys.executable).parent/'cephvr-python.runtime.json').read_text())
    handles=[os.add_dll_directory(p) for p in manifest['dll_directories']]
    from cephvr.acquisition.coordinator.trial_delivery import TrialReportDelivery
    from google.protobuf.json_format import MessageToDict
    original_delivery=TrialReportDelivery.deliver
    async def delivery(self,trial,kind,report,deadline_ns):
        receipt=await original_delivery(self,trial,kind,report,deadline_ns)
        if receipt.failure.code:
            data=dict(kind=kind,host_ns=time.perf_counter_ns(),deadline_ns=deadline_ns,
                report=MessageToDict(report,preserving_proto_field_name=True),failure=MessageToDict(receipt.failure,preserving_proto_field_name=True))
            with (Path(os.environ['CEPHVR_START_OUTPUT'])/'rejected-lifecycle.jsonl').open('a') as stream:stream.write(json.dumps(data)+'\n')
        return receipt
    TrialReportDelivery.deliver=delivery
    from cephvr.acquisition.coordinator.trial_pulses import TrialPulseBoundaries
    original_boundary=TrialPulseBoundaries.execute
    async def boundary(self,session,trial,roles,**kwargs):
        try:return await original_boundary(self,session,trial,roles,**kwargs)
        finally:
            data=dict(kind='pulse_boundary',host_ns=time.perf_counter_ns(),boundary=kwargs,
                work=MessageToDict(trial.work,preserving_proto_field_name=True),interrupted=trial.interrupted,
                on=MessageToDict(trial.pulse_on,preserving_proto_field_name=True) if trial.pulse_on else None,
                off=MessageToDict(trial.pulse_off,preserving_proto_field_name=True) if trial.pulse_off else None)
            with (Path(os.environ['CEPHVR_START_OUTPUT'])/'pulse-boundary-probe.jsonl').open('a') as stream:stream.write(json.dumps(data)+'\n')
    TrialPulseBoundaries.execute=boundary
