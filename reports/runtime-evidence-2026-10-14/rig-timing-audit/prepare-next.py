from pathlib import Path

root = Path(__file__).parent
probe = root / 'fault-recheck5/cleanup-probe/sitecustomize.py'
s = probe.read_text()
if "if 'cephvr.controller.main'" not in s:
    pos = s.index('try:\n')
    boot = "if 'cephvr.controller.main' in ' '.join(sys.argv[1:]) and os.environ.get('CEPHVR_CLEANUP_TRACE'):\n"
    boot += "    manifest = json.loads((Path(sys.executable).parent / 'cephvr-python.runtime.json').read_text())\n"
    boot += "    handles = [os.add_dll_directory(x) for x in manifest['dll_directories']]\n"
    probe.write_text(s[:pos] + boot + ''.join('    ' + line if line.strip() else line for line in s[pos:].splitlines(keepends=True)))
restore = root / 'restore-original.py'
b = restore.read_bytes()
old = b"'30645d86-accc-4df3-a29b-70b12f9d9012'"
assert old in b
if b'921dbb6e-b845-452b-9a4d-fcadd9079fb0' not in b:
    restore.write_bytes(b.replace(old, old + b",'921dbb6e-b845-452b-9a4d-fcadd9079fb0'"))
dest = root / 'fault-recheck6'
dest.mkdir(exist_ok=True)
(dest / 'run.py').write_bytes((root / 'fault-recheck5/run.py').read_bytes())
