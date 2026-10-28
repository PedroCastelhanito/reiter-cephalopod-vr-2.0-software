"""Apply the owner-selected interpretation only to the ten verified ALDER images."""
import hashlib
import json
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

from cephvr.gui.protocol_snapshot import validate_protocol
from cephvr.visual_stimulus.config.models.program_model import ColorOverride

OUT = Path(__file__).parent
TARGET = Path('C:/Users/ReiterU_PC/Desktop/Alsu/protocols/texture-presentation-1hr_protocol.json')
original = TARGET.read_bytes()
expected = json.loads((OUT / 'results.json').read_text('utf-8'))['protocol_sha256']
assert hashlib.sha256(original).hexdigest() == expected, 'Protocol changed since validation; review first'
document = json.loads(original)
proposed = deepcopy(document)
assets = document['trials'][0]['program']['assets']
assert len(assets) == 10
selected = {(a['asset_id'], a['logical_path']) for a in assets}
override = ColorOverride(transfer='linear', primaries='rec709_d65', range='full',
    matrix='rgb', chroma_location='none', reason='Owner-selected linear intensity interpretation, 2026-10-28: ALDER MATLAB save_img writes normalized grayscale mean 0.5/std 0.2 directly to uint8 RGB without gamma encoding; preserve authored numerical intensities.').model_dump(mode='json')
changed = []


def update(value):
    if isinstance(value, dict):
        if (value.get('asset_id'), value.get('logical_path')) in selected:
            assert value['profile'] == 'png_uint_v1' and value['color_override'] is None
            value['color_override'] = dict(override)
            changed.append(value['asset_id'])
        for child in value.values():
            update(child)
    elif isinstance(value, list):
        for child in value:
            update(child)


update(proposed)
assert set(changed) == {a['asset_id'] for a in assets}
validate_protocol(proposed)
payload = (json.dumps(proposed, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')
(OUT / 'texture-presentation-linear.protocol.json').write_bytes(payload)
backup = OUT / 'texture-presentation-before-linear.protocol.json'
if backup.exists():
    assert backup.read_bytes() == original
else:
    backup.write_bytes(original)
if '--apply' in sys.argv:
    assert TARGET.read_bytes() == original, 'Concurrent protocol edit'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=TARGET.parent, prefix='.cephvr-linear-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        assert TARGET.read_bytes() == original, 'Concurrent protocol edit'
        os.replace(temporary, TARGET)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
print(json.dumps(dict(applied='--apply' in sys.argv, unique_assets=len(selected),
    declarations_changed=len(changed), original_sha256=expected,
    proposed_sha256=hashlib.sha256(payload).hexdigest(), target=str(TARGET))))
