import json,tomllib
from pathlib import Path
from pypylon import pylon,genicam
from cephvr.controller.configuration import load_controller_configuration
root=Path.cwd();out=root/'reports/runtime-evidence-2026-10-15/projector-free-rig'
loaded=load_controller_configuration(root);acq=next(b.acquisition for b in loaded.configuration.backends if b.backend_name=='acquisition');defaults=tomllib.loads((root/'config/backends/acquisition_config.toml').read_text(encoding='utf-8'))['cameras'];result={};factory=pylon.TlFactory.GetInstance()
for role in ['behavioral','tracking','eye_tracking']:
 c=getattr(acq,role);serial=c.device.device_id;row={'enabled':c.enabled,'serial':serial,'file_nominal_rate_hz':defaults[role].get('pulse_frequency_hz'),'file_mcu_pin':defaults[role].get('microcontroller_pin'),'file_drain_ms':defaults[role].get('post_cutoff_drain_margin_ms')};result[role]=row
 dev=next((d for d in factory.EnumerateDevices() if d.GetSerialNumber()==serial),None)
 if dev is None:row['error']='device not enumerated';continue
 camera=pylon.InstantCamera(factory.CreateDevice(dev))
 try:
  camera.Open();values={}
  for name in ['Width','Height','OffsetX','OffsetY','PixelFormat','ExposureTime','ExposureTimeAbs','Gain','GainRaw','AcquisitionFrameRateEnable','AcquisitionFrameRate','AcquisitionFrameRateAbs','TriggerSelector','TriggerMode','TriggerSource','TriggerActivation','DeviceLinkThroughputLimit']:
   try:
    node=camera.GetNodeMap().GetNode(name)
    if node is not None and genicam.IsReadable(node):values[name]=node.ToString()
   except Exception as exc:values[name+'_read_error']=str(exc)
  row['actual_readback']=values
 finally:
  camera.Close();row['closed']=not camera.IsOpen()
(out/'camera-readback.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
