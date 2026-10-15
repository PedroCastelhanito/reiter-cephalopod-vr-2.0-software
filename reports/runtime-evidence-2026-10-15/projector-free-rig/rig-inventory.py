import asyncio,json,os,platform,shutil,subprocess,sys,tomllib
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from pypylon import pylon
from serial.tools import list_ports
from cephvr.synchronization.diagnostic import SpikeGLXDiagnostic
from cephvr.gui.calibration_profile import active_monitor_bindings
from dataclasses import asdict
root=Path.cwd();out=root/'reports/runtime-evidence-2026-10-15/projector-free-rig'
r={'python':sys.version,'platform':platform.platform(),'storage':dict(zip(['total','used','free'],shutil.disk_usage(root))),'cameras':[{'serial':d.GetSerialNumber(),'model':d.GetModelName(),'device_class':d.GetDeviceClass()} for d in pylon.TlFactory.GetInstance().EnumerateDevices()],'ports':[{'device':p.device,'description':p.description} for p in list_ports.comports()],'displays':[asdict(m) for m in active_monitor_bindings()]}
r['spikeglx']=MessageToDict(asyncio.run(SpikeGLXDiagnostic(root).check()),preserving_proto_field_name=True)
for tool,args in {'ffmpeg':['-version'],'ffprobe':['-version'],'nvidia-smi':['--query-gpu=index,name,uuid,driver_version','--format=csv,noheader']}.items():
 p=subprocess.run([tool,*args],capture_output=True,text=True,timeout=20);r[tool]={'path':shutil.which(tool),'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
f=root/'config/last_configuration.json'
if f.exists():
 (out/'last_configuration.before.json').write_bytes(f.read_bytes())
 r['saved_configuration_present']=True
(out/'inventory.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in r.items() if k not in ['ffmpeg','ffprobe']},indent=2))
