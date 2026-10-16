"""Portable output-audit reproductions; no device/GL/encoder execution."""
import json
import runpy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from tests.visual_stimulus.support import make_program
from cephvr.acquisition.recording.session_outputs import failed_outputs
from cephvr.control.v1 import types_pb2 as pb
from cephvr.visual_stimulus.resources.budget import BoundedBudget
from cephvr.visual_stimulus.resources.prepare import prepare_resources
from cephvr.visual_stimulus.rendering import shaders

with TemporaryDirectory() as directory:
    root = Path(directory)
    program = make_program()

    def prepare():
        return prepare_resources(
            program, root, BoundedBudget(cpu_limit=1_000_000, gpu_limit=1_000_000),
            announce=lambda *_: None, snapshot_limit_bytes=1_000_000,
            video_index_limit_bytes=1_000_000, glb_element_limit=1_000_000,
        )

    before = prepare()
    original = shaders._LAYER_FRAGMENT
    try:
        shaders._LAYER_FRAGMENT = original.replace('float wave = cos(', 'float wave = sin(')
        assert shaders._LAYER_FRAGMENT != original
        after = prepare()
    finally:
        shaders._LAYER_FRAGMENT = original
    roles = sorted({item.role for item in before.manifest.provenance})
    fingerprints = [item.content_sha256 for item in before.manifest.provenance]
    resource_ids = {item.fingerprint.resource_id for item in before.manifest.resources}
    referenced_shader_ids = {item.shader_resource_id for item in before.uniform_layouts}
    assert before.manifest == after.manifest
    assert not {'shader', 'graphics_driver', 'gpu', 'color_transform'} & set(roles)
    assert all(value is None for value in fingerprints)
    assert referenced_shader_ids - resource_ids
    print(json.dumps({
        'manifest_roles': roles,
        'renderer': before.manifest.provenance[0].model_dump(),
        'unresolved_shader_ids': sorted(referenced_shader_ids - resource_ids),
        'manifest_unchanged_after_shader_change': before.manifest == after.manifest,
    }, indent=2))
    print('REPRODUCED: production manifest builder does not retain exact shader/renderer or graphics-environment provenance.')

    fixtures = runpy.run_path('tests/acquisition/test_recording_cleanup.py')
    video_path, log_path = root / 'trial.mp4', root / 'trial.jsonl'
    schedule = fixtures['_schedule'](video_path, log_path)
    video_path.write_bytes(b'present but ownership not proved')
    results = failed_outputs(
        schedule, video_path, log_path, encoder=SimpleNamespace(exit_code=0),
        video_identity=None, stat_identity=lambda path: ('present-identity' if path.exists() else None),
        completion_failed=False,
    )
    assert video_path.exists()
    assert results[0].closure == pb.OUTPUT_CLOSURE_UNCONFIRMED
    assert results[0].HasField('artifact_present') and not results[0].artifact_present
    print('REPRODUCED: video exists at reserved path, identity proof missing, failed_outputs reports artifact_present=false.')
    print(results[0])
