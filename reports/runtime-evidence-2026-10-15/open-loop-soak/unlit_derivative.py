"""Prepare a separate base-color-only test floor; preserve original and BIN bytes."""

import copy
import hashlib
import json
from pathlib import Path
import struct

OUT = Path(__file__).resolve().parent
source = Path(r"C:\Users\ReiterU_PC\Desktop\Pedro\media\arenas\circular_blackwalls_filterednoisefloor\arena.glb")
raw = source.read_bytes()
magic, version, total = struct.unpack_from("<III", raw)
assert magic == 0x46546C67 and version == 2 and total == len(raw)
length, kind = struct.unpack_from("<II", raw, 12)
assert kind == 0x4E4F534A
document = json.loads(raw[20:20 + length])
original = copy.deepcopy(document)
for material in document["materials"]:
    material.setdefault("extensions", {})["KHR_materials_unlit"] = {}
for key in ("extensionsUsed", "extensionsRequired"):
    values = document.setdefault(key, [])
    if "KHR_materials_unlit" not in values:
        values.append("KHR_materials_unlit")
encoded = json.dumps(document, separators=(",", ":")).encode()
encoded += b" " * (-len(encoded) % 4)
tail = raw[20 + length:]
derived = struct.pack("<III", magic, version, 20 + len(encoded) + len(tail)) + struct.pack("<II", len(encoded), kind) + encoded + tail
destination = OUT / "derived-assets" / "arena-unlit-engineering.glb"
destination.parent.mkdir(exist_ok=True)
if destination.exists() and destination.read_bytes() != derived:
    raise RuntimeError("Distinct derivative path already contains different bytes")
destination.write_bytes(derived)
check = copy.deepcopy(document)
for material in check["materials"]:
    material["extensions"].pop("KHR_materials_unlit")
    if not material["extensions"]:
        material.pop("extensions")
for key in ("extensionsUsed", "extensionsRequired"):
    check[key].remove("KHR_materials_unlit")
    if not check[key]:
        check.pop(key)
assert check == original
assert derived[20 + len(encoded):] == tail
record = dict(scope="Separate engineering unlit derivative of supplied circular floor only; no walls present; no physical calibration or bake claim", source=str(source), source_sha256=hashlib.sha256(raw).hexdigest(), destination=str(destination), derived_sha256=hashlib.sha256(derived).hexdigest(), bin_chunk_and_tail_sha256=hashlib.sha256(tail).hexdigest(), bin_and_tail_identical=True, only_semantic_changes=["KHR_materials_unlit on existing materials", "extensionsUsed/Required declaration"], material_count=len(document["materials"]))
(OUT / "unlit-derivative.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, indent=2))
