"""Check generated declarations; --write refreshes schemas, never experimental data."""
from pathlib import Path
import argparse
import json
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'vr'))
from method_models import SCHEMAS as METHODS
from record_models import SCHEMAS as RECORDS

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    for name,model in {**METHODS,**RECORDS}.items():
        text=json.dumps(model.model_json_schema(),indent=2,ensure_ascii=False)+'\n'
        path=HERE/(name+'.schema.json')
        if args.write:path.write_text(text)
        elif not path.exists() or path.read_text()!=text:
            raise SystemExit('stale generated schema: '+str(path))
    print(f'{len(METHODS)+len(RECORDS)} tracking JSON schemas match the canonical models.')
if __name__=='__main__':main()
