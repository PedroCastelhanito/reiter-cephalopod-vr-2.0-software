"""Separate bounded-texture engineering GLB; preserve all original source bytes."""

import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import struct

from PIL import Image

out = Path(__file__).parent
saved = json.loads((out / "original-settings/last_configuration.json").read_text())["configuration"]
program = json.loads(saved["trials"][0]["stimulus"]["program"]["program_json"])
asset = next(a for a in program["assets"] if a["asset_id"] == "circular")
asset_root = Path(saved["asset_root"])
source = asset_root / asset["logical_path"]
raw = source.read_bytes()
magic,version,total = struct.unpack_from("<III",raw)
assert magic == 0x46546C67 and version == 2 and total == len(raw)
length,kind = struct.unpack_from("<II",raw,12)
assert kind == 0x4E4F534A
document = json.loads(raw[20:20+length])
original = copy.deepcopy(document)
bin_length,bin_kind = struct.unpack_from("<II",raw,20+length)
assert bin_kind == 0x004E4942
binary = bytearray(raw[28+length:28+length+bin_length])
resized = []
for index,image in enumerate(document.get("images",[])):
    assert "bufferView" in image
    view = document["bufferViews"][image["bufferView"]]
    begin = view.get("byteOffset",0)
    pixels = Image.open(BytesIO(binary[begin:begin+view["byteLength"]])).convert("RGBA")
    before = pixels.size
    pixels.thumbnail((512,512),Image.Resampling.LANCZOS)
    stream = BytesIO()
    pixels.save(stream,format="PNG")
    encoded = stream.getvalue()
    binary.extend(b"\x00"*(-len(binary)%4))
    document["bufferViews"].append({"buffer":0,"byteOffset":len(binary),"byteLength":len(encoded)})
    binary.extend(encoded)
    image["bufferView"] = len(document["bufferViews"])-1
    image["mimeType"] = "image/png"
    resized.append({"image":index,"original_size":before,"fixture_size":pixels.size})
document["buffers"][0]["byteLength"] = len(binary)
binary.extend(b"\x00"*(-len(binary)%4))
encoded = json.dumps(document,separators=(",",":")).encode()
encoded += b" "*(-len(encoded)%4)
derived = struct.pack("<III",magic,version,28+len(encoded)+len(binary))+struct.pack("<II",len(encoded),kind)+encoded+struct.pack("<II",len(binary),bin_kind)+binary
destination = asset_root / "media/arenas/cephvr-audit-20261015/arena512.glb"
destination.parent.mkdir(parents=True,exist_ok=True)
assert not destination.exists() or destination.read_bytes() == derived
destination.write_bytes(derived)
(out / "arena512.glb").write_bytes(derived)
assert document["meshes"] == original["meshes"] and document["nodes"] == original["nodes"] and document["materials"] == original["materials"]
record = {"scope":"Distinct reduced-texture engineering fixture, not original-scene fidelity/quality acceptance; original geometry/materials/BIN prefix retained, embedded images separately resized to at most512px", "source":str(source),"source_sha256":hashlib.sha256(raw).hexdigest(),"destination":str(destination),"logical_path":destination.relative_to(asset_root).as_posix(),"sha256":hashlib.sha256(derived).hexdigest(),"images":resized}
(out / "arena-fixture.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
print(json.dumps(record,indent=2))
