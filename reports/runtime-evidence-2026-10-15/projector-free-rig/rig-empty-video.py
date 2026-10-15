import json,subprocess,tomllib,shutil,os
from pathlib import Path
out=Path('reports/runtime-evidence-2026-10-15/projector-free-rig');media=Path('.tmp/rig-empty-video');media.mkdir(exist_ok=True)
profiles=json.loads(Path('.tmp/rig-encoding-current/profiles.json').read_text());config=tomllib.loads(Path('config/backends/acquisition_config.toml').read_text());rows=[]
for role in ['behavioral','tracking']:
 p=profiles[role];args=config['cameras'][role]['ffmpeg_args'];path=media/(role+'-verified.mp4')
 cmd=[shutil.which('ffmpeg'),'-hide_banner','-nostdin','-progress','pipe:1','-f','rawvideo','-pix_fmt',p['input_pixel_format'],'-s',f"{p['width']}x{p['height']}",'-framerate',str(p['fps']),'-i','-','-map','0:v:0','-an','-sn','-dn',*args,'-gpu','1','-bf','0','-force_key_frames','expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+1))','-fps_mode:v','passthrough','-map_metadata','-1','-movflags','+hybrid_fragmented+frag_keyframe+use_metadata_tags','-n','-forced-idr','1','-f','mp4',str(path)]
 result=subprocess.run(cmd,input=b'',capture_output=True,timeout=30)
 row={'role':role,'command':cmd,'stdin_bytes':0,'exit':result.returncode,'stderr':result.stderr.decode(errors='replace'),'progress':result.stdout.decode(errors='replace'),'artifact_present':path.exists(),'bytes':path.stat().st_size if path.exists() else None,'scope':'Direct native raw-input/muxer capability, no camera/session accounting or runtime ownership acceptance; identity tags omitted for this standalone probe.'}
 if path.exists():
  with path.open('r+b') as file:os.fsync(file.fileno())
  probe=subprocess.run(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,timeout=20);row['ffprobe_exit']=probe.returncode;row['ffprobe']=probe.stdout;row['ffprobe_error']=probe.stderr
 rows.append(row);(out/'empty-video.json').write_text(json.dumps(rows,indent=2)+'\n');print(role,result.returncode,row['bytes'],flush=True)
