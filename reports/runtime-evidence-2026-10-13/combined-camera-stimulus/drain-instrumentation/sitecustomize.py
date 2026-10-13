"""Temporary managed preview timing probe; never loaded by normal launches."""
import dataclasses
import functools
import json
import os
from pathlib import Path
import sys
import time

if any('cephvr.acquisition' in arg for arg in sys.argv):
    manifest = json.loads((Path(sys.executable).parent / 'cephvr-python.runtime.json').read_text())
    handles = [os.add_dll_directory(p) for p in manifest['dll_directories']]
    from cephvr.acquisition.camera.basler import BaslerCameraAdapter
    from cephvr.acquisition.worker.capture_runtime import WorkerCaptureResources
    from cephvr.acquisition.microcontroller_client import ControllerMicrocontrollerClient
    from google.protobuf.json_format import MessageToDict

    output = Path(os.environ['CEPHVR_DRAIN_OUTPUT']) / f'events-{os.getpid()}.jsonl'
    def event(kind, **values):
        with output.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(kind=kind, host_ns=time.perf_counter_ns(), pid=os.getpid(), **values)) + '\n')
    event('instrumentation', argv=sys.argv, observation_ms=2000)
    retrieve = BaslerCameraAdapter.retrieve
    def receive(self, *args, **kwargs):
        result = retrieve(self, *args, **kwargs)
        if result is not None:
            event('frame', serial=self._device_id, valid=result.valid_image, counter=result.camera_frame_counter)
        return result
    BaslerCameraAdapter.retrieve = receive
    settings = BaslerCameraAdapter.read_settings
    def read(self, *args, **kwargs):
        value = settings(self, *args, **kwargs)
        event('settings', serial=self._device_id, value=dataclasses.asdict(value))
        return value
    BaslerCameraAdapter.read_settings = read
    begin = BaslerCameraAdapter.begin_terminal_drain
    def terminal(self):
        event('generation_stop_begin', serial=self._device_id)
        result = begin(self)
        event('generation_stop_end', serial=self._device_id, confirmed=result)
        return result
    BaslerCameraAdapter.begin_terminal_drain = terminal
    stop = WorkerCaptureResources.stop
    native_stop = BaslerCameraAdapter.stop_capture
    def observe_native(self, deadline_ns, **kwargs):
        if getattr(self, '_diagnostic_preview_stop', False):
            end = min(time.perf_counter_ns() + 2_000_000_000, deadline_ns)
            while time.perf_counter_ns() < end and kwargs['should_continue_drain']():
                result = self.retrieve(min(10_000_000, end - time.perf_counter_ns()))
                if result is not None:
                    result.release()
            event('observation_tail_end', serial=self._device_id)
        return native_stop(self, deadline_ns, **kwargs)
    BaslerCameraAdapter.stop_capture = observe_native
    def observe(self, deadline_ns, **kwargs):
        # Only sessionless previews: no recording or production policy amendment.
        if self._preview_run_id is not None and self._session_run_id is None and self.active:
            event('observation_begin', serial=self.adapter._device_id, run_id=str(self._preview_run_id), deadline_ns=deadline_ns)
            self.adapter._diagnostic_preview_stop = True
            try:
                result = stop(self, deadline_ns, **kwargs)
            finally:
                self.adapter._diagnostic_preview_stop = False
            event('observation_end', serial=self.adapter._device_id, evidence=dataclasses.asdict(result))
            return result
        return stop(self, deadline_ns, **kwargs)
    WorkerCaptureResources.stop = observe
    for method in ('on', 'off'):
        original = getattr(ControllerMicrocontrollerClient, method)
        def wrap(original, method):
            @functools.wraps(original)
            async def call(self, roles, **kwargs):
                event(method + '_begin', roles=roles)
                result = await original(self, roles, **kwargs)
                event(method + '_end', roles=roles, evidence=MessageToDict(result, preserving_proto_field_name=True))
                return result
            return call
        setattr(ControllerMicrocontrollerClient, method, wrap(original, method))
