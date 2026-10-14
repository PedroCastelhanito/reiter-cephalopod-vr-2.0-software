from pathlib import Path

root = Path(__file__).parent
restore = root / 'restore-original.py'
b = restore.read_bytes()
old = b"'0de05a85-aad5-4c46-9eec-5708b8dde94e'"
assert old in b
if b'53d8525a-060d-4c12-90c5-085443051c8c' not in b:
    restore.write_bytes(b.replace(old, old + b",'53d8525a-060d-4c12-90c5-085443051c8c'"))
out = root / 'camera-only-abort'
out.mkdir(exist_ok=True)
s = (root / 'abort/run.py').read_text()
s = s.replace("backend.enabled=True\n                    backend.visual_stimulus.save_visual_stimulus_data=True", "backend.enabled=False\n                    backend.visual_stimulus.save_visual_stimulus_data=False")
s = s.replace("'scope':'real configured cameras plus stimulus recording; unpaired60s; original settings restored'", "'scope':'camera-only interrupted trial; projectors owner-deferred; original settings restored'")
(out / 'run.py').write_text(s)
(out / 'verify-partial.py').write_bytes((root / 'abort/verify-partial.py').read_bytes())
preview = root / 'final-preview'
preview.mkdir(exist_ok=True)
(preview / 'preview.py').write_text((root / 'preview.py').read_text().replace('for cycle in range(2):', 'for cycle in range(4):'))
