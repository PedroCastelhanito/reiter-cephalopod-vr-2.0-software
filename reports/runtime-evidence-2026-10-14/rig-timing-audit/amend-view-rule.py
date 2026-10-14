from pathlib import Path

p = Path('docs/architecture/gui.md')
b = p.read_bytes()
start = b.index(b'### E03 ')
part = b[start:]
old = b'**Revision:** 34'
assert old in part
part = part.replace(old, b'**Revision:** 35', 1)
anchor = b'  lifecycle.'
at = part.index(anchor) + len(anchor)
newline = b'\r\n' if b'\r\n' in part else b'\n'
addition = newline + b'  Controller warning delivery may retain one exact preceding trial or just-retired' + newline + b'  session scope; session warnings must match its frozen configuration revision.' + newline + b'  Clear that allowance on a configuration revision change or another session.' + newline + b'  Preserve producer generation and occurrence validation; a late optional warning' + newline + b'  cannot reactivate work or prove resource/output closure.'
part = part[:at] + addition + part[at:]
p.write_bytes(b[:start] + part)
p = Path('architecture.md')
b = p.read_bytes()
old = b'[E03](docs/architecture/gui.md#e03) | GUI disconnection and control lease | Accepted | 34 |'
assert old in b
p.write_bytes(b.replace(old, old.replace(b'34 |', b'35 |'), 1))
