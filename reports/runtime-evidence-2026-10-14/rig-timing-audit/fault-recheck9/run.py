"""Owner-authorized real combined60s recording, guarded by explicit A10 policies."""
import asyncio
import dataclasses
import json
import subprocess
import time
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from cephvr.acquisition.config.file_policies import load_file_policies
from cephvr.client.session import HeadlessClient, loopback_channel
from cephvr.control.v1 import services_pb2 as rpc, types_pb2 as pb
from cephvr.launcher.replacement import _existing_endpoint
from cephvr.shared.credentials import CredentialStore, default_runtime_root

OUT=Path(__file__).parent.resolve()
result={'scope':'real configured cameras plus stimulus recording; unpaired60s; original settings restored','checks':{}}
def keep(name,value):
    result['checks'][name]=value
    (OUT/'run.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(name,json.dumps(value),flush=True)
def view(s):
    return {key:MessageToDict(getattr(s,key),preserving_proto_field_name=True) for key in ('session','trial','configuration','reservation','acquisition_devices','visual_stimulus_display')} | {'errors':[MessageToDict(e,preserving_proto_field_name=True) for e in s.errors],'prompts':len(s.prompts)}
def gpu_sample():
    records={}
    commands=[['nvidia-smi','--query-compute-apps=pid,gpu_uuid,process_name','--format=csv,noheader'],['nvidia-smi','encodersessions','-i','GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc']]
    for command in commands:
        try:
            sample=subprocess.run(command,capture_output=True,text=True,timeout=2)
            records[' '.join(command)]={'stdout':sample.stdout,'stderr':sample.stderr,'returncode':sample.returncode}
        except subprocess.TimeoutExpired as sample:
            def text(value):return value if isinstance(value,str) else (value or b'').decode(errors='replace')
            records[' '.join(command)]={'stdout':text(sample.stdout),'stderr':text(sample.stderr),'bounded_continuous_sample':True}
    return {'host_monotonic_ns':time.perf_counter_ns(),'queries':records}
async def main():
    endpoint=_existing_endpoint(default_runtime_root())
    if endpoint is None:raise RuntimeError('No managed runtime')
    store=CredentialStore(default_runtime_root(),endpoint.controller_generation)
    principal=store.provision_client('cli')
    try:
        async with loopback_channel(50051,16777216) as channel:
            lifecycle_observations=[]
            seen_reports=set()
            def observe(snapshot):
                now=time.perf_counter_ns()
                for participant in snapshot.participants:
                    for kind in ('started','stopped','finished'):
                        if participant.HasField(kind):
                            report=getattr(participant,kind)
                            digest=report.SerializeToString(deterministic=True)
                            key=(participant.process.role,kind,digest)
                            if key not in seen_reports:
                                seen_reports.add(key)
                                lifecycle_observations.append(dict(backend=participant.process.role,kind=kind,client_observed_ns=now,controller_snapshot_ns=snapshot.captured_monotonic_ns,report=MessageToDict(report,preserving_proto_field_name=True)))
            client=HeadlessClient(channel,principal,on_snapshot=observe)
            original_execute=client.execute
            operation_timings=[]
            async def measured_execute(method, *args, **kwargs):
                begin=time.perf_counter_ns()
                try:
                    return await original_execute(method,*args,**kwargs)
                finally:
                    operation_timings.append(dict(method=method,begin_ns=begin,end_ns=time.perf_counter_ns()))
                    keep('operation_timings',operation_timings)
            client.execute=measured_execute
            state=await client.get_snapshot()
            ready_until=time.monotonic()+45
            while not state.visual_stimulus_display.complete:
                if time.monotonic()>=ready_until:raise RuntimeError('Managed backend/display initialization did not complete before diagnostic mutation')
                await asyncio.sleep(.5)
                state=await client.get_snapshot()
            original=pb.ExperimentConfiguration.FromString(state.configuration_values.current.SerializeToString())
            acquisition=next(b.acquisition for b in original.backends if b.backend_name=='acquisition')
            policies=load_file_policies(Path.cwd())
            active=[role for role in ('behavioral','tracking','eye_tracking') if getattr(acquisition,role).enabled]
            for index,role in enumerate(('behavioral','tracking','eye_tracking'),1):
                if role not in active:continue
                policy=next(p for p in policies.cameras if p.camera==index)
                if not policy.HasField('post_cutoff_drain_margin_ns') or policy.post_cutoff_drain_margin_ns<=0:
                    raise RuntimeError(f'{role}: explicit A10 drain allowance required before recording')
            if state.session.phase!=pb.SESSION_PHASE_CONFIGURATION or state.prompts:
                raise RuntimeError('Configuration with no unresolved prompts required; existing work preserved')
            (OUT/'run-original.pb').write_bytes(original.SerializeToString())
            keep('file_policies',MessageToDict(policies,preserving_proto_field_name=True))
            candidate=pb.ExperimentConfiguration.FromString(original.SerializeToString())
            candidate.subject='DUMMY'
            candidate.experiment='rig_timing_probe_20261014'
            candidate.recording_root=str(OUT/'recordings')
            Path(candidate.recording_root).mkdir(exist_ok=True)
            candidate.mode=pb.SESSION_MODE_OPEN_LOOP
            del candidate.trials[1:]
            del candidate.gaps[:]
            program=json.loads(candidate.trials[0].stimulus.program.program_json)
            for epoch,duration in zip(program['sequence'],('5','20','35'),strict=True):epoch['duration']['duration']['seconds']=duration
            candidate.trials[0].stimulus.program.program_json=json.dumps(program)
            for backend in candidate.backends:
                if backend.backend_name in ('tracking','synchronization'):backend.enabled=False
                elif backend.backend_name=='visual_stimulus':
                    backend.enabled=True
                    backend.visual_stimulus.save_visual_stimulus_data=True
                elif backend.backend_name=='acquisition':
                    backend.enabled=True
                    backend.acquisition.recording_queue_frames=17
                    for role in active:getattr(backend.acquisition,role).save_video=True
            (OUT/'run-candidate.pb').write_bytes(candidate.SerializeToString())
            keep('active_cameras',active)
            async with client.control(takeover=True):
                async def update(value):
                    return await client.execute('UpdateConfiguration',rpc.UpdateConfigurationRequest(command=client.operator_command(),expected_revision=client.snapshot.configuration.revision,proposed=value))
                try:
                    accepted=await update(candidate)
                    keep('configuration',dataclasses.asdict(accepted))
                    if not accepted.succeeded:return
                    setup=await asyncio.wait_for(client.execute('Setup'),100)
                    keep('setup',dataclasses.asdict(setup))
                    keep('setup_state',view(client.snapshot))
                    if not setup.succeeded:return
                    raise RuntimeError('Controlled budget rejection unexpectedly passed Setup; no trial dispatched')
                    started=await asyncio.wait_for(client.execute('StartSession'),45)
                    keep('start',dataclasses.asdict(started))
                    if started.succeeded:
                        samples=[]
                        for second in range(85):
                            await asyncio.sleep(1)
                            if second in (2,10,25,40):
                                samples.append(await asyncio.to_thread(gpu_sample))
                                keep('gpu_samples',samples)
                            if second%15==0:print('recording elapsed check',second,'phase',pb.SessionPhase.Name(client.snapshot.session.phase),flush=True)
                            if client.snapshot.session.phase==pb.SESSION_PHASE_ENDED:break
                        else:keep('abort_timeout',dataclasses.asdict(await client.execute('AbortNow')))
                    keep('lifecycle_observations',lifecycle_observations)
                    keep('final',view(client.snapshot))
                    (OUT/'run-final.pb').write_bytes(client.snapshot.SerializeToString())
                finally:
                    if client.snapshot.session.phase==pb.SESSION_PHASE_SETTING_UP:
                        keep('cancel_setup',dataclasses.asdict(await client.execute('CancelSetup')))
                    elif client.snapshot.session.phase in (pb.SESSION_PHASE_READY,pb.SESSION_PHASE_ENDED):
                        keep('new_session',dataclasses.asdict(await client.execute('NewSession')))
                    if client.snapshot.session.phase==pb.SESSION_PHASE_CONFIGURATION:
                        keep('restore',dataclasses.asdict(await update(original)))
                        keep('configuration_restored',client.snapshot.configuration_values.current==original)
    except Exception as error:
        keep('error',f'{type(error).__name__}: {error}')
        raise
    finally:store.remove_client(principal)
asyncio.run(main())
