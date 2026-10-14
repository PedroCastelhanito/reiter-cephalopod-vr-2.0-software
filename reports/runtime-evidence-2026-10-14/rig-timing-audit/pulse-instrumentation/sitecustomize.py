"""Temporary controller-only protocol-event evidence; no frame hooks."""
import json,os,sys,time
from pathlib import Path
if 'cephvr.controller.main' in ' '.join(sys.argv[1:]) and os.environ.get('CEPHVR_PULSE_OUTPUT'):
 out=Path(os.environ['CEPHVR_PULSE_OUTPUT'])/('pulse-'+str(os.getpid())+'.jsonl')
 def emit(kind,**fields):
  try:
   with out.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(kind=kind,pid=os.getpid(),host_ns=time.perf_counter_ns(),**fields))+'\n')
  except Exception:pass
 try:
  manifest=json.loads((Path(sys.executable).parent/'cephvr-python.runtime.json').read_text())
  _handles=[os.add_dll_directory(x) for x in manifest['dll_directories']]
  from google.protobuf.json_format import MessageToDict
  from cephvr.controller.microcontroller.owner import SerialOwner
  def wrap(name):
   original=getattr(SerialOwner,name)
   def observed(self,*args,**kwargs):
    begin=time.perf_counter_ns()
    try:result=original(self,*args,**kwargs)
    except BaseException as error:
     emit('serial_event',method=name,begin_ns=begin,end_ns=time.perf_counter_ns(),error_type=type(error).__name__,error=str(error));raise
    emit('serial_event',method=name,begin_ns=begin,end_ns=time.perf_counter_ns(),result=MessageToDict(result,preserving_proto_field_name=True))
    return result
   setattr(SerialOwner,name,observed)
  for method in ('connect','configure','on','off','status','keepalive'):wrap(method)
  emit('pulse_probe_loaded',scope='controller serial events only')
 except Exception as error:emit('pulse_probe_load_error',error_type=type(error).__name__,error=str(error))
