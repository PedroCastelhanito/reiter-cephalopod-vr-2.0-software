"""Verify new ALDER imports against originals and prepare/apply scoped overrides."""
import hashlib
import json
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

from cephvr.gui.protocol_snapshot import validate_protocol
from cephvr.visual_stimulus.config.models.program_model import ColorOverride

OUT = Path(__file__).parent / 'full-alder'
OUT.mkdir(exist_ok=True)
TARGET = Path('C:/Users/ReiterU_PC/Desktop/Alsu/protocols/texture-presentation-1hr_protocol.json')
ORIGINALS = Path('C:/Users/ReiterU_PC/Desktop/Alsu/Cuttlebase_3840x2000_1to1_ALDER/stimuli')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


if '--apply' in sys.argv:
    manifest = json.loads((OUT/'provenance.json').read_text('utf-8'))
    before = (OUT/'before.protocol.json').read_bytes()
    payload = (OUT/'linear.protocol.json').read_bytes()
    assert TARGET.read_bytes() == before, 'Concurrent protocol edit'
    assert hashlib.sha256(before).hexdigest() == manifest['protocol_sha256']
    validate_protocol(json.loads(payload))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=TARGET.parent, prefix='.cephvr-linear-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        assert TARGET.read_bytes() == before, 'Concurrent protocol edit'
        os.replace(temporary, TARGET)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    print('Applied verified linear declarations; no image bytes changed.', flush=True)
else:
    raw = TARGET.read_bytes()
    document = json.loads(raw)
    validate_protocol(document)
    assets = document['trials'][0]['program']['assets']
    assert len(assets) == 600
    rows = []
    for index, asset in enumerate(assets, 1):
        imported = Path(document['asset_root'])/asset['logical_path']
        original = ORIGINALS/imported.name
        assert imported.is_file() and original.is_file(), imported
        sha = digest(imported)
        assert sha == digest(original), f'Original mismatch: {imported}'
        assert asset['profile'] == 'png_uint_v1' and asset['color_override'] is None
        rows.append(dict(asset_id=asset['asset_id'], logical_path=asset['logical_path'], source_sha256=sha))
        if index % 50 == 0:
            print(f'Original/imported hashes match: {index}/600', flush=True)
    selected = {(a['asset_id'],a['logical_path']) for a in assets}
    override = ColorOverride(transfer='linear',primaries='rec709_d65',range='full',matrix='rgb',chroma_location='none',
        reason='Owner-selected linear interpretation for ALDER normalized grayscale stimuli (2026-10-28). Imported PNG SHA256 matches original; MATLAB save_img writes normalized values directly to uint8 RGB without gamma encoding.').model_dump(mode='json')
    proposed = deepcopy(document)
    changed = []

    def update(value):
        if isinstance(value,dict):
            asset_id,path = value.get('asset_id'),value.get('logical_path')
            if isinstance(asset_id,str) and isinstance(path,str) and (asset_id,path) in selected:
                assert value['color_override'] is None
                value['color_override'] = dict(override)
                changed.append(asset_id)
            for child in value.values():
                update(child)
        elif isinstance(value,list):
            for child in value:
                update(child)

    update(proposed)
    assert set(changed) == {a['asset_id'] for a in assets}
    validate_protocol(proposed)
    assert TARGET.read_bytes() == raw, 'Concurrent protocol edit'
    (OUT/'before.protocol.json').write_bytes(raw)
    (OUT/'linear.protocol.json').write_text(json.dumps(proposed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'provenance.json').write_text(json.dumps(dict(protocol_sha256=hashlib.sha256(raw).hexdigest(),
        declarations_changed=len(changed), assets=rows),indent=2),encoding='utf-8')
    print(f'Prepared {len(changed)} declarations for600 verified ALDER images.',flush=True)
