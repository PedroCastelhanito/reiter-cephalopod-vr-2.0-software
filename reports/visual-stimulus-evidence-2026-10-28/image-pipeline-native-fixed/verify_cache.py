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
# Verify the normal index reader against current source/software identity.
assert stored["validator"] == validator_identity()
for item in document["trials"][0]["program"]["assets"]:
    asset=Asset.model_validate(item);path=root/asset.logical_path
    with path.open("rb") as f: digest=hashlib.file_digest(f,"sha256").hexdigest()
    source=PreparedAsset(asset.asset_id,asset.logical_path,asset.profile,digest,path.stat().st_size,None,None)
    key=image_validation_key(asset,source,display=None,output_count=4,dependency_asset=None,dependency_source=None)
    info=index.get(key)
    results.append({"asset":asset.asset_id,"sha256":digest,"key":key,"hit":info is not None})
record={"tested_renderer_validator":stored["validator"],"current_disk_validator":validator_identity(),"scope":"Normal index reader with current validator and independently recomputed source hashes","hits":sum(r["hit"] for r in results),"count":len(results),"images":results}
(out/"cache-verification.json").write_text(json.dumps(record,indent=2),encoding="utf-8")
print({k:v for k,v in record.items() if k!="images"})
assert record["hits"]==record["count"]==600
