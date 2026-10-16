import ast,hashlib,json,subprocess,tomllib
from pathlib import Path
from cephvr.visual_stimulus.config.models.display_profile import DisplayProfile
from cephvr.visual_stimulus.recording.encoding import _composite_geometry
root=Path.cwd(); out=root/'reports/runtime-evidence-2026-10-16/stimulus-sequential-recording'
def old(path): return subprocess.check_output(['git','show',f'HEAD:{path}'],text=True)
path='src/cephvr/visual_stimulus/recording/encoding.py'
def functions(text): return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
a,b=functions(old(path)),functions(Path(path).read_text())
unchanged={name:a[name]==b[name] for name in ('_composite_geometry','build_review_argv','ffmpeg_input_format')}
assert all(unchanged.values())
path='src/cephvr/visual_stimulus/rendering/capture.py'
unchanged['GPU_compositor_and_readback']=old(path)==Path(path).read_text()
assert unchanged['GPU_compositor_and_readback']
path='config/backends/visual_stimulus_config.toml'; a=tomllib.loads(old(path));b=tomllib.loads(Path(path).read_text()); a.pop('policy_version');b.pop('policy_version');assert a==b
unchanged['all_stimulus_operator_values_except_policy_version']=True
profile_path=Path('reports/runtime-evidence-2026-10-15/open-loop-soak/display-profile.json')
profile=DisplayProfile.model_validate_json(profile_path.read_text())
w,h,k,tiles=_composite_geometry(profile,(8192,8192),2)
assert (w,h)==(1280,1000)
result={'method':'AST equality with HEAD for geometry/input-argv helpers; byte equality for compositor; TOML equality for operator settings except policy version. Geometry calculation uses retained Oct15 profile, not live rig state.', 'unchanged':unchanged,'example_geometry':{'profile':str(profile_path),'assumed_encoder_maximum':[8192,8192],'review_scale_factor':2,'width':w,'height':h,'scale_denominator':k,'tiles':tiles}, 'new_rate_mode':'nominal playback only; scientific timestamps external'}
(out/'preserved-output-path.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
