import time, numpy as np, io, sys
from cephvr.visual_stimulus.resources.media import ImagePixels
from cephvr.visual_stimulus.rendering.upload import linear_rgba_bytes
import imagecodecs
rng=np.random.default_rng(0)
W,H=3840,2160
def t(f,n=3):
    best=1e9
    for _ in range(n):
        s=time.perf_counter(); r=f(); best=min(best,time.perf_counter()-s)
    return best,r
for ch,alpha,tr in [(3,"none","srgb"),(4,"straight","srgb"),(3,"none","linear")]:
    px=rng.integers(0,256,(H,W,ch),dtype=np.uint8)
    order=("red","green","blue","alpha")[:ch]
    ip=ImagePixels(W,H,"uint8",ch,order,px,tr,alpha)
    dt,ref=t(lambda: linear_rgba_bytes(ip))
    # LUT variant
    def lut():
        v=np.arange(256,dtype=np.float32)/255
        l=np.where(v<=0.04045,v/12.92,((v+0.055)/1.055)**2.4).astype(np.float32) if tr=="srgb" else v
        out=np.empty((H,W,4),np.float32)
        src=px[::-1]
        out[...,:3]=l[src[...,:3]]
        if ch==4:
            out[...,3]=v[src[...,3]]; out[...,:3]*=out[...,3:4]
        else: out[...,3]=1
        return out.tobytes()
    dl,r2=t(lut)
    a=np.frombuffer(ref,np.float32); b=np.frombuffer(r2,np.float32)
    print(f"{ch}ch {alpha} {tr}: current {dt*1000:.0f} ms, LUT {dl*1000:.0f} ms, maxabs {np.abs(a-b).max():.2e}, out {len(ref)/2**20:.0f} MiB")
px=rng.integers(0,256,(H,W,3),dtype=np.uint8)
png=imagecodecs.png_encode(px); 
d,_=t(lambda: imagecodecs.imread(png)); print(f"PNG decode 4K RGB8 noise ({len(png)/2**20:.0f} MiB): {d*1000:.0f} ms")
import hashlib; d,_=t(lambda: hashlib.sha256(png).hexdigest()); print(f"sha256 of it: {d*1000:.0f} ms")
