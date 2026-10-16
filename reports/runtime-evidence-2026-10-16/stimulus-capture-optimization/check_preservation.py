import ast,hashlib,json
from pathlib import Path
root=Path.cwd(); out=root/'reports/runtime-evidence-2026-10-16/stimulus-capture-optimization'
before=(out/'capture-before.py').read_text(); after=Path('src/cephvr/visual_stimulus/rendering/capture.py').read_text()
def funcs(src):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(src).body if isinstance(n,ast.FunctionDef)}
def constants(src):return {n.targets[0].id:ast.literal_eval(n.value) for n in ast.parse(src).body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in {'_VERTEX','_FRAGMENT'}}
def tile_loop(src):return next(ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(src)) if isinstance(n,ast.For) and ast.unparse(n.target)=='tile')
old_encoding=funcs((out/'encoding-before.py').read_text());new_encoding=funcs(Path('src/cephvr/visual_stimulus/recording/encoding.py').read_text())
checks={'compositor_shader_bytes':constants(before)==constants(after),'quad_geometry':funcs(before)['struct_quad']==funcs(after)['struct_quad'],'tile_render_loop':tile_loop(before)==tile_loop(after),'operator_configuration_bytes':(out/'config-before.toml').read_bytes()==Path('config/backends/visual_stimulus_config.toml').read_bytes()}
for name in ('_composite_geometry','_layout_size','build_review_argv','ffmpeg_input_format'):
 if name in old_encoding:checks[name]=old_encoding[name]==new_encoding[name]
assert all(checks.values()), checks
(out/'preservation.json').write_text(json.dumps({'comparison':'Exact pre-increment local snapshot, not HEAD; existing sequential changes preserved','checks':checks,'scope':'Static preservation; GL transfer output checked by host model in tests; native GPU pixels/performance remain pending'},indent=2)+'\n')
print(checks)
