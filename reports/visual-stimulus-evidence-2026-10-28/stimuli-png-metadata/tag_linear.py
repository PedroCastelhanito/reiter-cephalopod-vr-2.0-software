"""Lossless, scoped PNG metadata edit with preflight hashes and reversible checks."""
import hashlib
import json
import os
import struct
import sys
import tempfile
import zlib
from pathlib import Path

from cephvr.visual_stimulus.resources.media import _png_transfer

ROOT = Path('C:/Users/ReiterU_PC/Desktop/Alsu/media').resolve()
OUT = Path(__file__).parent
FAMILIES = ('Cuttlebase_3840x2000_1to1_ALDER', 'Primate_3840x2000_1to1_POPLAR')
SIGNATURE = b'\x89PNG\r\n\x1a\n'
COLOUR = {b'gAMA', b'cHRM', b'sRGB', b'iCCP', b'cICP'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def chunk(kind, payload):
    return struct.pack('>I', len(payload))+kind+payload+struct.pack('>I', zlib.crc32(kind+payload)&0xffffffff)


TAGS = chunk(b'gAMA', struct.pack('>I', 100000))+chunk(b'cHRM', struct.pack('>8I', 31270,32900,64000,33000,30000,60000,15000,6000))


def chunks(raw):
    assert raw.startswith(SIGNATURE), 'Invalid PNG signature'
    offset = 8
    result = []
    while offset < len(raw):
        assert offset+12 <= len(raw), 'Truncated PNG chunk'
        size = int.from_bytes(raw[offset:offset+4], 'big')
        end = offset+12+size
        assert end <= len(raw), 'Truncated PNG payload'
        block = raw[offset:end]
        assert zlib.crc32(block[4:-4])&0xffffffff == int.from_bytes(block[-4:], 'big'), 'Bad PNG CRC'
        result.append((block[4:8], block))
        offset = end
        if block[4:8] == b'IEND':
            break
    assert offset == len(raw) and result[-1][0] == b'IEND', 'Invalid PNG ending'
    assert result[0][0] == b'IHDR' and len(result[0][1]) == 25
    assert any(kind == b'IDAT' for kind,_ in result)
    return result


def tagged(raw):
    parts = chunks(raw)
    assert not any(kind in COLOUR for kind,_ in parts), 'Existing colour declaration needs review'
    result = SIGNATURE+parts[0][1]+TAGS+b''.join(block for _,block in parts[1:])
    assert _png_transfer(result) == 'linear'
    after = chunks(result)
    assert SIGNATURE+b''.join(block for kind,block in after if kind not in COLOUR) == raw
    assert [block for kind,block in after if kind == b'IDAT'] == [block for kind,block in parts if kind == b'IDAT']
    return result


def target(relative):
    path = (ROOT/relative).resolve(strict=True)
    assert path.is_relative_to(ROOT) and path.parent == ROOT/Path(relative).parts[0]/'stimuli'
    assert Path(relative).parts[0] in FAMILIES and path.suffix.lower() == '.png'
    return path


def self_check():
    import imagecodecs
    import numpy as np
    raw = imagecodecs.png_encode(np.arange(24,dtype=np.uint8).reshape(2,4,3))
    result = tagged(raw)
    assert np.array_equal(imagecodecs.png_decode(raw),imagecodecs.png_decode(result))
    for invalid in (raw[:-1], raw[:40]+bytes([raw[40]^1])+raw[41:]):
        try:
            tagged(invalid)
        except AssertionError:
            pass
        else:
            raise AssertionError('Corrupt PNG accepted')


self_check()
mode = sys.argv[1]
if mode == '--plan':
    files = sorted(p for family in FAMILIES for p in (ROOT/family/'stimuli').glob('*.png'))
    assert len(files) == 1200
    old_alder = json.loads((OUT.parent/'image-cpu-capacity/full-alder/provenance.json').read_text('utf-8'))
    alder_hashes = {Path(row['logical_path']).name:row['source_sha256'] for row in old_alder['assets']}
    for family in FAMILIES:
        generator = ROOT/family/'generation_code/ps_3840x2000_task.m'
        assert sha(generator.read_bytes()) == '9ae5458130158d1c8584b75ca23313b6d54ecb1aac0dafeb249668ad9345ec34'
        expected_names = set()
        for fi in range(40):
            number = fi+1 if family == FAMILIES[0] else fi
            expected_names.update(f'{fi*15+k:04d}_{number}_metamer{k}.png' for k in range(1,11))
            expected_names.update(f'{fi*15+10+k:04d}_{number}_noise{k}.png' for k in range(1,6))
        assert {p.name for p in (ROOT/family/'stimuli').glob('*.png')} == expected_names
    rows = []
    for index,path in enumerate(files,1):
        relative = path.relative_to(ROOT).as_posix()
        assert target(relative) == path
        raw = path.read_bytes()
        if relative.startswith(FAMILIES[0]+'/'):
            assert sha(raw) == alder_hashes[path.name], f'Prior ALDER hash mismatch: {path}'
        parts = chunks(raw)
        assert struct.unpack('>IIBB',parts[0][1][8:18]) == (3840,2000,8,2)
        changed = tagged(raw)
        rows.append(dict(path=relative, before_sha256=sha(raw), after_sha256=sha(changed),
            original_bytes=len(raw),
            idat_sha256=sha(b''.join(block for kind,block in chunks(raw) if kind == b'IDAT'))))
        if index%100 == 0:
            print(f'Preflight/provenance/CRC/unchanged-IDAT proof: {index}/1200',flush=True)
    selected = {r['path'] for r in rows}
    excluded = {p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in ROOT.rglob('*')
                if p.is_file() and p.relative_to(ROOT).as_posix() not in selected}
    (OUT/'plan.json').write_text(json.dumps(dict(root=str(ROOT), inserted_chunks_hex=TAGS.hex(),
        files=rows, excluded=excluded),indent=2),encoding='utf-8')
    print(f'Plan ready:1200 targets; {len(excluded)} non-target files protected by hashes.',flush=True)
elif mode == '--apply':
    plan = json.loads((OUT/'plan.json').read_text('utf-8'))
    assert plan['root'] == str(ROOT) and plan['inserted_chunks_hex'] == TAGS.hex()
    for index,row in enumerate(plan['files'],1):
        path = target(row['path'])
        raw = path.read_bytes()
        if sha(raw) == row['after_sha256']:
            continue
        assert sha(raw) == row['before_sha256'], f'Concurrent edit: {path}'
        payload = tagged(raw)
        assert sha(payload) == row['after_sha256']
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.cephvr-linear-',suffix='.tmp',delete=False) as stream:
                temporary = Path(stream.name).resolve()
                assert temporary.parent == path.parent and temporary.is_relative_to(ROOT)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            assert sha(path.read_bytes()) == row['before_sha256'], f'Concurrent edit: {path}'
            os.replace(temporary,path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        with (OUT/'applied.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(dict(path=row['path'],sha256=row['after_sha256']))+'\n')
        if index%100 == 0:
            print(f'Metadata tagged atomically: {index}/1200',flush=True)
elif mode == '--verify':
    import imagecodecs
    import numpy as np
    from cephvr.platform.windows.protected_source import ProtectedWindowsSource
    from cephvr.visual_stimulus.config.models.program_model import Asset
    from cephvr.visual_stimulus.configuration import load_file_policies
    from cephvr.visual_stimulus.resources.assets import PreparedAsset
    from cephvr.visual_stimulus.resources.budget import BoundedBudget
    from cephvr.visual_stimulus.resources.image_source import validate_image_source
    limits = load_file_policies(Path.cwd()).limits
    plan = json.loads((OUT/'plan.json').read_text('utf-8'))
    samples = []
    for index,row in enumerate(plan['files']):
        path = target(row['path'])
        raw = path.read_bytes()
        assert sha(raw) == row['after_sha256'] and _png_transfer(raw) == 'linear'
        parts = chunks(raw)
        assert sha(b''.join(block for kind,block in parts if kind == b'IDAT')) == row['idat_sha256']
        restored = SIGNATURE+b''.join(block for kind,block in parts if kind not in COLOUR)
        assert sha(restored) == row['before_sha256']
        if index in (0,599,600,1199):
            assert np.array_equal(imagecodecs.png_decode(restored),imagecodecs.png_decode(raw))
            source = ProtectedWindowsSource(path)
            try:
                asset = Asset(asset_id=f'sample-{index}',logical_path=row['path'],profile='png_uint_v1',color_override=None)
                prepared = PreparedAsset(asset.asset_id,asset.logical_path,asset.profile,sha(raw),len(raw),source,None)
                budget = BoundedBudget(cpu_limit=limits.max_asset_cpu_bytes,gpu_limit=limits.max_asset_gpu_bytes)
                _,info = validate_image_source(asset,prepared,budget=budget,owner='sample',output_count=4,max_document_bytes=limits.max_document_bytes)
                assert info.transfer == 'linear' and budget.usage.cpu_bytes == 0
                samples.append(dict(path=row['path'],transfer=info.transfer,full_validation=True,pixel_equal=True))
            finally:
                source.close_after_consumers()
    for relative,expected in plan['excluded'].items():
        assert sha((ROOT/relative).read_bytes()) == expected, f'Non-target changed: {relative}'
    result = dict(tagged=len(plan['files']),unchanged_non_targets=len(plan['excluded']),
                  all_idat_unchanged=True,all_original_bytes_recoverable=True,samples=samples)
    (OUT/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
else:
    raise ValueError('Use --plan, --apply or --verify')
