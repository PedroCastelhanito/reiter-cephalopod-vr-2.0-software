import collections,gc,json,time
from pathlib import Path
from cephvr.visual_stimulus.config.models.artifact_models import PreparedTrial
from cephvr.visual_stimulus.rendering.engine import RendererEngine
from cephvr.visual_stimulus.rendering.types import DisplayInitialization,OutputActivity,RenderedOutput,RenderPassResult
root=Path('cephvr-data/r22/20261022_full22fixed/SPRIGCHECK-114917/protocol-data')
artifacts=[PreparedTrial.model_validate_json(p.read_text(encoding='utf-8')) for p in sorted(root.glob('*_stimulus_LOG.json'))]
display=artifacts[0].display; outputs=display.active_outputs
class Port:
 def activity(self):return tuple(OutputActivity(o.output_id,1,2,display.requested_swap_interval(o.output_id)) for o in outputs)
 def initialize_display(self,d):return DisplayInitialization(tuple(o.output_id for o in outputs),tuple((o.output_id,o.rgb_bits_per_channel,o.rgb_bits_per_channel,o.rgb_bits_per_channel) for o in outputs),tuple((o.output_id,o.width_px,o.height_px) for o in outputs),tuple((o.output_id,display.requested_swap_interval(o.output_id)) for o in outputs),self.activity())
 def prepare_trial(self,*args):pass
 def render(self,scene,state):return RenderPassResult(tuple(RenderedOutput(o.output_id,o.width_px,o.height_px,8,None) for o in outputs),(),(),())
 def present(self,frames):return self.activity()
 def show_idle(self,d):return self.activity()
port=Port();engine=RendererEngine(port,clock_ns=lambda:0,resource_provider=lambda _:object())
engine.initialize_display(display)
for artifact in artifacts:engine.prepare_trial(artifact)
def census():return collections.Counter(f'{type(x).__module__}.{type(x).__qualname__}' for x in gc.get_objects())
gc.collect();gc.freeze();baseline=census();samples=[];start=time.perf_counter()
try:
 for trial,artifact in enumerate(artifacts):
  engine.begin_trial(artifact.identity.trial_id,0)
  for frame in range(36000):
   update=engine.render_tick(frame*1_000_000_000//60)
   if (frame+1)%12000==0:
    before=time.perf_counter_ns();collected=gc.collect(2);elapsed=time.perf_counter_ns()-before
    item={'trial':trial+1,'frames':frame+1,'gen2_ns':elapsed,'collected':collected,'growth':(census()-baseline).most_common(15)};samples.append(item);print(item,flush=True)
  engine.stop_trial(600_000_000_000)
finally:gc.unfreeze()
Path(__file__).with_suffix('.json').write_text(json.dumps({'scope':'actual prepared two-trial engine boundary/state/snapshot transitions, fake render port, no image residency/GL','elapsed_s':time.perf_counter()-start,'samples':samples},indent=2),encoding='utf-8')
