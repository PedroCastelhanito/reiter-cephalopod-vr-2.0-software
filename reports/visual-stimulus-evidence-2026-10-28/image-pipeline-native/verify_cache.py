import hashlib,json,time
from pathlib import Path
from cephvr.gui.protocol_snapshot import validate_protocol
from cephvr.visual_stimulus.config.models.program_model import Asset
from cephvr.visual_stimulus.resources.assets import PreparedAsset
from cephvr.visual_stimulus.resources.image_interpretation import image_validation_key
from cephvr.visual_stimulus.resources.image_validation_index import ImageValidationIndex,validator_identity
out=Path(__file__).parent
protocol=Path("C:/Users/ReiterU_PC/Desktop/Alsu/protocols/texture-presentation-1hr_protocol.json")
document=validate_protocol(json.loads(protocol.read_bytes()))
root=Path(document["asset_root"]);index=ImageValidationIndex(root);results=[]
stored=json.loads(index.path.read_text(encoding="utf-8"))
# Inspect facts for the completed native run; do not treat them as valid for changed software.
assert stored["validator"] == "32e95961a9724d32367407523b88a5b40407614487ecd826b46e239b125e9695"
index.entries=stored["images"]
for item in document["trials"][0]["program"]["assets"]:
    asset=Asset.model_validate(item);path=root/asset.logical_path
    with path.open("rb") as f: digest=hashlib.file_digest(f,"sha256").hexdigest()
    source=PreparedAsset(asset.asset_id,asset.logical_path,asset.profile,digest,path.stat().st_size,None,None)
    key=image_validation_key(asset,source,display=None,output_count=4,dependency_asset=None,dependency_source=None)
    info=index.get(key)
    results.append({"asset":asset.asset_id,"sha256":digest,"key":key,"hit":info is not None})
record={"tested_renderer_validator":stored["validator"],"current_disk_validator":validator_identity(),"scope":"Offline content-key/fact verification for completed native run; later source edits require cache invalidation","hits":sum(r["hit"] for r in results),"count":len(results),"images":results}
(out/"cache-verification.json").write_text(json.dumps(record,indent=2),encoding="utf-8")
print({k:v for k,v in record.items() if k!="images"})
assert record["hits"]==record["count"]==600
