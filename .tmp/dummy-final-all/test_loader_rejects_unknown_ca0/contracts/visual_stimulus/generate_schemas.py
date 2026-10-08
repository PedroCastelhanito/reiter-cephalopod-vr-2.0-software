"""Generate/check the published Visual Stimulus schemas from their sole Python definitions."""
from pathlib import Path
import argparse
import json
from program_model import Program, TrialArenaBoundaries
from artifact_models import PreparedTrial, ResourceManifest, GeometricProfile
from display_profile import DisplayProfile
from photometric_profile import PhotometricProfile
from evidence_model import EvidenceRecord, ReplayRequest, ReplayReport, ExportIndex
MODELS = {
    'program': Program, 'arena-boundaries': TrialArenaBoundaries,
    'prepared-trial': PreparedTrial, 'resource-manifest': ResourceManifest,
    'geometric-profile': GeometricProfile, 'display-profile': DisplayProfile,
    'photometric-profile': PhotometricProfile, 'evidence-record': EvidenceRecord,
    'replay-request': ReplayRequest, 'replay-report': ReplayReport,
    'export-index': ExportIndex,
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    changed = []
    for name, model in MODELS.items():
        path = Path(__file__).with_name(name + '.schema.json')
        content = json.dumps(model.model_json_schema(mode='validation'), indent=2) + '\n'
        if not path.exists() or path.read_text() != content:
            changed.append(path.name)
            if not args.check:
                path.write_text(content)
    if args.check and changed:
        parser.exit(1, 'Schema drift: ' + ', '.join(changed) + '\n')
    print(f'{len(MODELS)} schemas checked; {len(changed)} needed regeneration')

if __name__ == '__main__':
    main()
