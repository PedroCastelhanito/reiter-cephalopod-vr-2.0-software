import json,os,subprocess,sys,threading,time
from pathlib import Path
root=Path.cwd();out=root/'.tmp/rig-encoding-current';stop=threading.Event();state={'case':'initial'};rows=[]
def sample():
 with (out/'gpu-processes.jsonl').open('w',encoding='utf-8') as f:
  while not stop.is_set():
   try:
    p=subprocess.run(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,process_name','--format=csv,noheader'],capture_output=True,text=True,timeout=5)
    f.write(json.dumps({'case':state['case'],'time':time.time(),'exit':p.returncode,'rows':p.stdout.strip().splitlines(),'error':p.stderr})+'\n');f.flush()
   except Exception as exc:f.write(json.dumps({'error':str(exc)})+'\n')
   stop.wait(1)
thread=threading.Thread(target=sample,daemon=True);thread.start()
def run(label,sources,cq,seconds):
 state['case']=label;print('START',label,flush=True);cmd=[sys.executable,'tools/encoding_probe.py','bench','--profiles',str(out/'profiles.json'),'--sources',sources,'--cq',str(cq),'--gpu','1','--seconds',str(seconds),'--timeout','300','--output',str(out/label)];began=time.time()
 with (out/(label+'.log')).open('w') as log:p=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=1000)
 row={'label':label,'command':cmd,'exit_code':p.returncode,'wall_s':time.time()-began};path=out/label/'summary.json'
 if path.exists():row['results']=json.loads(path.read_text(encoding='utf-8'))
 rows.append(row);(out/'matrix-summary.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8');print('DONE',label,'exit',p.returncode,flush=True)
 if p.returncode:raise RuntimeError('matrix stopped on failed case '+label)
try:
 run('warmup','behavioral,tracking,stimulus',16,10)
 cases=[('behavioral','behavioral'),('tracking','tracking'),('stimulus','stimulus'),('cameras','behavioral,tracking'),('all','behavioral,tracking,stimulus')]
 for repeat in [1,2,3]:
  for label,sources in cases:
   for cq in ([23,16] if repeat==2 else [16,23]):run(f'r{repeat}-{label}-cq{cq}',sources,cq,60)
 print('MATRIX COMPLETE',flush=True)
finally:stop.set();thread.join(6)
