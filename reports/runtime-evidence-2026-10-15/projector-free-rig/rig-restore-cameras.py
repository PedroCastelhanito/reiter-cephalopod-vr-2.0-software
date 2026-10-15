import json,hashlib
from pathlib import Path
from pypylon import pylon,genicam
out=Path.cwd()/'reports/runtime-evidence-2026-10-15/projector-free-rig';before=json.loads((out/'camera-readback.json').read_text(encoding='utf-8'));factory=pylon.TlFactory.GetInstance();result={}
for role in ['behavioral','tracking']:
 serial=before[role]['serial'];device=next(d for d in factory.EnumerateDevices() if d.GetSerialNumber()==serial);camera=pylon.InstantCamera(factory.CreateDevice(device));row={};result[role]=row
 try:
  camera.Open();text=(out/(role+'-before.pfs')).read_text(encoding='utf-8')
  for name in ['OffsetX','OffsetY']:
   node=camera.GetNodeMap().GetNode(name)
   if genicam.IsWritable(node):node.SetValue(node.GetMin())
  pylon.FeaturePersistence.LoadFromString(text,camera.GetNodeMap(),True);after=pylon.FeaturePersistence.SaveToString(camera.GetNodeMap());(out/(role+'-restored.pfs')).write_text(after,encoding='utf-8');row['pfs_exact_match']=after==text
  row['readback']={name:camera.GetNodeMap().GetNode(name).ToString() for name in before[role]['actual_readback'] if not name.endswith('_read_error')}
  row['values_match']=row['readback']=={k:v for k,v in before[role]['actual_readback'].items() if not k.endswith('_read_error')}
 finally:camera.Close();row['closed']=not camera.IsOpen()
last=out/'last_configuration.before.json';current=Path('config/last_configuration.json');result['saved_configuration_bytes_unchanged']=last.read_bytes()==current.read_bytes();(out/'restoration.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
