"""Temporary one-run wrappers; not imported by committed production code."""
import functools
import json
import os
import sys
import time

from cephvr.acquisition.recording.frame_log import FrameLogWriter
from cephvr.acquisition.recording.session import RecordingSession
from cephvr.platform.windows.encoder_process import WindowsEncoderProcess
from cephvr.platform.windows.file_sync import WindowsVideoSync
from cephvr.shared.pixels.preparer import PixelPreparer

assert not getattr(RecordingSession,"_cephvr_audit_profile_installed",False)
RecordingSession._cephvr_audit_profile_installed=True
_audit_stages={}
_audit_queue={"sample_count":0,"max_waiting_pixels":0,"max_pending_records":0}

def _audit_observe(name,elapsed):
    value=_audit_stages.setdefault(name,{"count":0,"total_ns":0,"max_ns":0,"over_33ms":0,"over_100ms":0})
    value["count"]+=1;value["total_ns"]+=elapsed
    if elapsed>value["max_ns"]:
        value["max_ns"]=elapsed;value["max_end_monotonic_ns"]=time.perf_counter_ns()
    value["over_33ms"]+=elapsed>33_333_333
    value["over_100ms"]+=elapsed>100_000_000

def _audit_wrap(owner,method,name):
    original=getattr(owner,method)
    @functools.wraps(original)
    def measured(*args,**kwargs):
        started=time.perf_counter_ns()
        try:return original(*args,**kwargs)
        finally:_audit_observe(name,time.perf_counter_ns()-started)
    setattr(owner,method,measured)

for _owner,_method,_name in (
    (PixelPreparer,"prepare_recording_into","pixel_preparation"),
    (WindowsEncoderProcess,"write","encoder_pipe_write"),
    (WindowsEncoderProcess,"wait","encoder_drain_and_release"),
    (FrameLogWriter,"append_frame","frame_evidence_append"),
    (FrameLogWriter,"append_video_frame","mapping_evidence_append"),
    (FrameLogWriter,"_sync","frame_evidence_sync"),
    (WindowsVideoSync,"sync","video_sync"),
):_audit_wrap(_owner,_method,_name)

_audit_original_process_entry=RecordingSession._process_entry
@functools.wraps(_audit_original_process_entry)
def _audit_process_entry(self,*args,**kwargs):
    _audit_queue["sample_count"]+=1
    _audit_queue["max_waiting_pixels"]=max(_audit_queue["max_waiting_pixels"],self.queue.waiting_pixels)
    _audit_queue["max_pending_records"]=max(_audit_queue["max_pending_records"],self.queue.pending_records)
    _audit_queue["capacity_frames"]=self.queue.capacity_frames
    started=time.perf_counter_ns()
    try:return _audit_original_process_entry(self,*args,**kwargs)
    finally:_audit_observe("consumer_entry_total_nested",time.perf_counter_ns()-started)
RecordingSession._process_entry=_audit_process_entry

_audit_original_finish=RecordingSession.finish
@functools.wraps(_audit_original_finish)
def _audit_finish(self,*args,**kwargs):
    try:return _audit_original_finish(self,*args,**kwargs)
    finally:
        print(json.dumps({"event":"audit_acquisition_stage_metrics","installation_count":1,"pid":os.getpid(),"role":self.role,"frame_log_path":str(self._frame_log_path),"stages":_audit_stages,"queue_samples":_audit_queue,"scope":"Single-trial process-lifetime aggregate; sampled queue maxima at consumer boundaries, not continuous peak. Consumer total nests preparation/write/evidence/sync; no altered deadlines/queues or active-run added fsync"}),file=sys.stderr,flush=True)
RecordingSession.finish=_audit_finish
