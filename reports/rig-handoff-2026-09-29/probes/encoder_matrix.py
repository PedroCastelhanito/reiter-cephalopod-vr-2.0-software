"""Development-only encoder feasibility checks, not runtime code or throughput tests."""
import pathlib,json,subprocess,datetime,os
root=pathlib.Path(__file__).resolve().parents[1]; out=root/'evidence'
ff=os.environ.get('RIG_FFMPEG',r'C:\Users\ReiterU_PC\miniforge3\envs\CephVR\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe')
fp=os.environ.get('RIG_FFPROBE',r'C:\Dev\software\ffmpeg-4.3.2-2021\bin\ffprobe.exe')
# Resolve by UUID each run; do not assume GPU index 1 is permanent.
query=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,name','--format=csv,noheader'],text=True)
match=[s.split(',')[0].strip() for s in query.splitlines() if 'GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc' in s]
assert len(match)==1,query
gpu=match[0]
cases=[('behavior-current-h264-444',4096,3000,30,'rgb24','h264_nvenc','yuv444p'),('tracking-current-h264-444',2448,2048,60,'gray','h264_nvenc','yuv444p'),('behavior-sensor-max-h264',4112,3008,30,'rgb24','h264_nvenc','yuv444p'),('behavior-sensor-max-hevc',4112,3008,30,'rgb24','hevc_nvenc','yuv444p'),('tracking-hevc-10bit',2448,2048,60,'gray16le','hevc_nvenc','p010le'),('h264-10bit-negative',640,480,30,'gray16le','h264_nvenc','p010le'),('av1-negative',640,480,30,'rgb24','av1_nvenc','yuv420p')]
results=[]
for name,w,h,hz,source,codec,pix in cases:
    output=out/(name+'.mp4')
    args=[ff,'-hide_banner','-loglevel','warning','-n','-f','rawvideo','-pixel_format',source,'-video_size',f'{w}x{h}','-framerate',str(hz),'-i','pipe:0','-an','-c:v',codec,'-gpu',gpu,'-pix_fmt','+'+pix,'-vf',f'scale=w=iw:h=ih:in_range=full:out_range=full:out_color_matrix=bt709,format=pix_fmts={pix}','-color_range','pc','-colorspace','bt709','-preset','p4','-rc','vbr','-cq','18','-b:v','0','-rc-lookahead','0','-bf','0','-movflags','+hybrid_fragmented+frag_keyframe',str(output)]
    pixel={'rgb24':bytes([64,128,192]),'gray':bytes([128]),'gray16le':bytes([0,128])}[source]
    completed=subprocess.run(args,input=pixel*(w*h*3),capture_output=True,timeout=45)
    row={'case':name,'command':args,'returncode':completed.returncode,'stderr':completed.stderr.decode(errors='replace'),'input_frames':3}
    if completed.returncode==0:
        p=subprocess.run([fp,'-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=codec_name,pix_fmt,width,height,nb_read_frames,color_range,color_space','-of','json',str(output)],capture_output=True,text=True,timeout=15)
        row['ffprobe']=json.loads(p.stdout)
    results.append(row); print(json.dumps(row),flush=True)
(out/'encoder-matrix.json').write_text(json.dumps({'captured_at':datetime.datetime.now().astimezone().isoformat(),'gpu_uuid':'GPU-4d9915eb-bf04-59a8-8811-e0779366a0dc','tests':results},indent=2))
