import asyncio, threading, gc
from cephvr.synchronization.sdk_io import SpikeGLXIOOwner, SpikeGLXIOBusy
async def main():
    events=[]
    loop=asyncio.get_running_loop()
    loop.set_exception_handler(lambda loop,context: events.append(context))
    owner=SpikeGLXIOOwner(); release=threading.Event()
    def fail_late():
        release.wait(timeout=2)
        raise RuntimeError('audit injected late SDK failure')
    try:
        try: await owner.run(fail_late,0.01)
        except TimeoutError: print('initial timeout: observed')
        try: await owner.run(lambda: None,0.1)
        except SpikeGLXIOBusy: print('in-flight ownership: retained')
        release.set()
        for _ in range(20):
            await asyncio.sleep(0.01)
            gc.collect()
            if events: break
        print('loop exception events:',[(e.get('message'),str(e.get('exception'))) for e in events])
        assert len(events)==1 and str(events[0].get('exception'))=='audit injected late SDK failure'
    finally:
        release.set(); owner.close(wait=True)
asyncio.run(main())
