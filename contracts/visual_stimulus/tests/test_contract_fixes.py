"""Pure regression checks for routine V02-V28 contract validator fixes."""
from pathlib import Path
import copy
import json
import sys
import tomllib
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schema_common import MINIMUM_TRIAL_DURATION_NS
from program_model import parse_program_json, TargetTotal
from artifact_models import Fingerprint, ResourceManifest, parse_prepared_json
from photometric_profile import OutputBinding
from evidence_model import parse_evidence_json

BUDGET = 10_000_000
ROOT = Path(__file__).resolve().parents[1]

def fixture():
    return json.loads((ROOT / 'examples/drift-hold.json').read_text())

def parse(document):
    return parse_program_json(json.dumps(document), max_bytes=BUDGET)

def settings(document, index=0):
    return document['sequence'][index]['settings'][0]

def rejects(case, document):
    with case.assertRaises(ValueError): parse(document)

class ProgramFixTests(unittest.TestCase):
    def test_duplicate_surface_ids_rejected(self):
        source = fixture(); space = settings(source)['space']
        space['mappings'].append(copy.deepcopy(space['mappings'][0])); rejects(self, source)
        source = fixture()
        settings(source)['space'] = {'kind': 'visual_angle', 'frame_id': 'observer',
            'frame_to_rig_xyzw': [0, 0, 0, 1], 'surfaces': ['front', 'front']}
        rejects(self, source)

    def test_orientation_quaternions_must_be_unit(self):
        source = fixture()
        settings(source)['space'] = {'kind': 'visual_angle', 'frame_id': 'observer',
            'frame_to_rig_xyzw': [0, 0, 0.6, 0.8], 'surfaces': ['front']}
        parse(source)
        for bad in ([0, 0, 0, 0], [0, 0, 0, 2], [0, 0, 0, 1 + 1e-6]):
            settings(source)['space']['frame_to_rig_xyzw'] = bad
            with self.subTest(q=bad): rejects(self, source)
        pose = {'payload': {'kind': 'render_group', 'group_id': 0, 'submissions': [], 'captures': [],
            'state': {'epoch_occurrence': 0,
            'scene_id': 'scene', 'evaluation_host_ns': 1, 'active_instance_ids': [],
            'uniforms': [], 'media': [], 'effective_poses': [{'instance_id': 'arena',
            'frame_id': 'world', 'position_mm': [0, 0, 0], 'orientation_xyzw': [0, 0, 0, 1]}]}}}
        parse_evidence_json(json.dumps(pose), max_bytes=BUDGET)
        pose['payload']['state']['effective_poses'][0]['orientation_xyzw'] = [0, 0, 1, 1]
        with self.assertRaises(ValueError): parse_evidence_json(json.dumps(pose), max_bytes=BUDGET)

    def test_declared_parameter_ranges(self):
        cases = [(['opacity'], {'kind': 'constant', 'value': 1.5}),
                 (['opacity'], {'kind': 'keyframes', 'interpolation': 'linear',
                   'knots': [{'time': {'seconds': '0'}, 'value': 0}, {'time': {'seconds': '1'}, 'value': -0.1}]}),
                 (['contrast'], {'kind': 'ramp', 'initial': 2, 'slope_per_s': 0}),
                 (['width'], {'kind': 'constant', 'value': 0}),
                 (['height'], {'kind': 'constant', 'value': -1}),
                 (['pattern', 'frequency'], {'kind': 'constant', 'value': -0.1}),
                 (['opacity'], {'kind': 'sine', 'mean': 0.5, 'amplitude': 0.1, 'frequency_hz': -1, 'phase_cycles': 0})]
        for path, value in cases:
            source = fixture(); block = settings(source)
            for key in path[:-1]: block = block[key]
            block[path[-1]] = value
            with self.subTest(path=path, value=value): rejects(self, source)
        source = fixture(); settings(source)['opacity'] = {'kind': 'constant', 'value': 0}
        settings(source)['pattern']['frequency'] = {'kind': 'constant', 'value': 0}
        parse(source)
        # Condition cells reaching a ranged parameter are checked too.
        source = fixture(); body = source['sequence']
        source['sequence'] = [{'kind': 'group', 'group_id': 'g', 'repetitions': 1, 'order': 'as_listed',
            'order_unit': 'condition_rows', 'conditions': {'columns': [{'column_id': 'o', 'value_type': 'number', 'unit': '1'}],
            'rows': [{'row_id': 'r', 'cells': [{'column_id': 'o', 'value': 0.5}]}]}, 'body': body}]
        body[0]['settings'][0]['opacity'] = {'kind': 'constant', 'value': {'kind': 'condition', 'group_id': 'g', 'column_id': 'o'}}
        parse(source)
        source['sequence'][0]['conditions']['rows'][0]['cells'][0]['value'] = 1.01
        rejects(self, source)

    def test_explicit_trial_minimum_duration(self):
        source = fixture(); parse(source)
        source['sequence'][1]['duration']['duration']['seconds'] = '29.999999999'
        rejects(self, source)
        # Repetitions count toward the expanded explicit total.
        source['sequence'] = [{'kind': 'group', 'group_id': 'g', 'repetitions': 2, 'order': 'as_listed',
            'order_unit': 'child_blocks', 'conditions': None, 'body': source['sequence']}]
        parse(source)

    def test_target_total_minimum_duration(self):
        t = lambda v: {'seconds': v}
        ok = {'kind': 'target_total_random_epochs', 'total': t('60'), 'minimum': t('1'), 'maximum': t('10')}
        TargetTotal.model_validate(ok)
        with self.assertRaises(ValueError):
            TargetTotal.model_validate({**ok, 'total': t('59.999999999')})

    def test_minimum_duration_matches_experiment_policy(self):
        policy = tomllib.loads((ROOT.parent / 'policy/experiment_policy.toml').read_text())
        self.assertEqual(policy['protocol']['minimum_trial_duration_s'] * 1_000_000_000, MINIMUM_TRIAL_DURATION_NS)

    def test_direct_value_feedback_requires_absolute_channel(self):
        for kind, unit, ok in (('absolute', 'mm', True), ('displacement', 'mm', False),
                               ('interval_average_rate', 'mm/s', False)):
            source = fixture(); block = settings(source)
            source['input_channels'] = [{'channel_id': 'c', 'stream_id': 's', 'value_kind': kind,
                                         'unit': unit, 'frame_id': 'camera'}]
            block['feedback'] = [{'binding_id': 'b', 'source_channel': 'c', 'target': 'x',
                'operation': 'direct_value', 'gain': {'kind': 'constant', 'value': 1},
                'offset': {'kind': 'constant', 'value': 0}}]
            with self.subTest(kind=kind):
                if ok: parse(source)
                else: rejects(self, source)

    def test_playback_assignment_uses_exact_time(self):
        source = fixture()
        source['assets'] = [{'asset_id': 'clip', 'logical_path': 'media/clip.mp4',
                             'color_override': None, 'profile': 'mp4_h264_sdr8_v1'}]
        source['instances'][0]['family'] = 'video'
        for epoch in source['sequence']:
            block = epoch['settings'][0]
            for key in ('pattern', 'initial_phase_x_cycles', 'initial_phase_y_cycles', 'phase_x',
                        'phase_y', 'mean_linear_rgb', 'modulation_linear_rgb', 'contrast'): block.pop(key)
            block.update(kind='video', asset_id='clip', sampling='linear',
                         initial_playback={'seconds': '0'}, end_behavior='loop')
        block = settings(source, 1)
        block['assignments'] = [{'target': 'playback', 'value': {'seconds': '1.000000001'}}]
        parse(source)
        block['assignments'] = [{'target': 'playback', 'value': 1.5}]
        rejects(self, source)
        block['assignments'] = [{'target': 'x', 'value': {'seconds': '1'}}]
        rejects(self, source)

def output(output_id='projector 1'):
    return {'output_id': output_id, 'device_identity': 'dev ' + output_id, 'width_px': 400,
            'height_px': 100, 'refresh_numerator': 60, 'refresh_denominator': 1,
            'rgb_bits_per_channel': 8, 'photometric_profile': None}

def display():
    def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    surfaces = []
    for sid, c, n, u in (('front', (0, 0, 500), (0, 0, -1), (0, 1, 0)), ('left', (-500, 0, 0), (1, 0, 0), (0, 1, 0)),
                         ('right', (500, 0, 0), (-1, 0, 0), (0, 1, 0)), ('bottom', (0, -500, 0), (0, 1, 0), (0, 0, 1))):
        r = cross(u, n)
        corner = lambda sr, su: [c[i] + 500*sr*r[i] + 500*su*u[i] for i in range(3)]
        surfaces.append({'surface_id': sid, 'bottom_left_mm': corner(-1, -1), 'bottom_right_mm': corner(1, -1),
                         'top_right_mm': corner(1, 1), 'top_left_mm': corner(-1, 1)})
    return {'format_version': 1,
            'geometry': {'frame_id': 'rig', 'observer_mm': [0, 0, 0], 'near_mm': 1, 'far_mm': 5000,
                         'positional_tolerance_mm': 0.01, 'orthogonality_tolerance': 1e-6, 'surfaces': surfaces},
            'outputs': [output()],
            'mappings': [{'mapping_id': s['surface_id'], 'surface_id': s['surface_id'], 'output_id': 'projector 1',
                          'viewport': {'x': 100*i, 'y': 0, 'width': 100, 'height': 100},
                          'geometric_profile': {'logical_path': f"geometry/{s['surface_id']}.json"}}
                         for i, s in enumerate(surfaces)],
            'presentation_mode': 'all_outputs_vsync', 'photometric_mode': 'uncalibrated',
            'idle_linear_rgb': [0, 0, 0], 'photodiode_output_id': 'projector 1',
            'photodiode_patch': {'rect': {'x': 0, 'y': 0, 'width': 10, 'height': 10},
                                 'high_linear_rgb': [1, 1, 1], 'low_linear_rgb': [0, 0, 0]}}

def timing():
    return {'pacing_output_id': 'projector 1', 'rate_numerator': 60, 'rate_denominator': 1,
            'implementation': 'impl', 'capability_evidence_id': 'cap'}

def arena_block():
    return {'kind': 'arena', 'instance_id': 'arena', 'asset_id': 'room', 'world_frame_id': 'world',
            'asset_to_world': [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            'initial': {'position_mm': [0, 0], 'yaw_deg': 0}, 'fixed_height_mm': 0,
            'fixed_pitch_deg': 0, 'fixed_roll_deg': 0,
            'motion': {'x': {'kind': 'hold'}, 'y': {'kind': 'hold'}, 'yaw': {'kind': 'hold'}},
            'reset': False, 'assignments': [], 'feedback': []}

def prepared(extra=()):
    source = fixture(); epochs = []; boundaries = []; cursor = 0; previous = None
    for i, node in enumerate(source['sequence']):
        blocks = [copy.deepcopy(node['settings'][0])] + [copy.deepcopy(x) for x in extra]
        end = cursor + 30_000_000_000
        epochs.append({'occurrence_index': i, 'source_epoch_id': node['epoch_id'], 'duration_origin': 'fixed',
                       'lineage': [], 'scene_id': 'scene', 'start_ns': cursor, 'end_ns': end,
                       'truncated_curves': [], 'settings': blocks})
        boundaries.append({'time_ns': cursor, 'before': previous, 'after': i, 'operations': [
            {'instance_id': b['instance_id'], 'action': 'initialize' if i == 0 else 'continue', 'reason': 'x',
             'next_settings_index': k, 'assignment_indices': []} for k, b in enumerate(blocks)]})
        cursor = end; previous = i
    boundaries.append({'time_ns': cursor, 'before': previous, 'after': None, 'operations': [
        {'instance_id': b['instance_id'], 'action': 'deactivate', 'reason': 'normal end',
         'next_settings_index': None, 'assignment_indices': []} for b in epochs[-1]['settings']]})
    identity = {'session_id': 's', 'trial_id': 't', 'configuration_revision': 1, 'prepared_generation': 'p',
                'renderer_generation': 'r', 'resource_generation': 'g'}
    return {'format_version': 2, 'identity': identity, 'source': source, 'source_sha256': '0'*64,
            'display': display(), 'seed_decimal': '1', 'order_implementation': 'o',
            'duration_implementation': 'd', 'duration_sampler_id': 'stafford_continuous_ns_v1',
            'epochs': epochs, 'boundaries': boundaries,
            'arena_boundaries': {'format_version': 1, 'bindings': []},
            'manifest': {'format_version': 1, 'resources': [], 'provenance': []},
            'uniform_layouts': [], 'model_compatibility': 'm', 'renderer_compatibility': 'r',
            'compiler_compatibility': 'c', 'review_encoding': None}

def load(document):
    return parse_prepared_json(json.dumps(document), max_bytes=BUDGET)

class PreparedFixTests(unittest.TestCase):
    def test_baseline_prepared_trial_is_valid(self):
        self.assertEqual(load(prepared()).resolved_duration_ns, 60_000_000_000)

    def test_terminal_boundary_deactivates_final_instances(self):
        bad = prepared(); bad['boundaries'][-1]['operations'] = []
        with self.assertRaises(ValueError): load(bad)
        bad = prepared(); bad['boundaries'][-1]['operations'][0]['action'] = 'pause'
        with self.assertRaises(ValueError): load(bad)
        bad = prepared(); bad['boundaries'][1]['operations'][0].update(action='deactivate', next_settings_index=None)
        with self.assertRaises(ValueError): load(bad)

    def test_new_profiles_default_to_photodiode_only_vsync(self):
        document = prepared(); del document['display']['presentation_mode']
        self.assertEqual(load(document).display.presentation_mode, 'photodiode_only_vsync')

    def test_trial_marker_required_in_both_pacing_modes(self):
        for mode in ('all_outputs_vsync', 'photodiode_only_vsync'):
            bad = prepared(); bad['display']['presentation_mode'] = mode; bad['display']['photodiode_patch'] = None
            with self.subTest(mode=mode), self.assertRaises(ValueError): load(bad)

    def test_exactly_one_tiled_composite_encoding_when_recording(self):
        document = prepared()
        for i in (2, 3):
            document['display']['outputs'].append(output(f'projector {i}'))
        document['display']['mappings'][2]['output_id'] = 'projector 2'
        document['display']['mappings'][3]['output_id'] = 'projector 3'
        document['display']['outputs'][2]['rgb_bits_per_channel'] = 10
        rect = lambda x, y: {'x': x, 'y': y, 'width': 200, 'height': 50}
        tile = lambda oid, x, y, bits=8: {'output_id': oid, 'rect': rect(x, y), 'source_code_bits': bits}
        # Three 400x100 outputs, k=2: two columns; row 1 = outputs 1-2, row 2 = output 3.
        tiles = [tile('projector 1', 0, 50), tile('projector 2', 200, 50), tile('projector 3', 0, 0, 10)]
        encoding = {'composite_width': 400, 'composite_height': 100, 'scale_denominator': 2, 'tiles': tiles,
                    'native_pixel_format': 'r10g10b10a2_le_bottom_up', 'input_pixel_format': 'x2bgr10le',
                    'encoder_pixel_format': 'p010le', 'encoder_gpu_ordinal': 0, 'force_idr': True,
                    'effective_ffmpeg_args': [], 'timing': timing()}
        load(document)  # Saving Off: no encoding.
        document['review_encoding'] = encoding; load(document)
        document['review_encoding'] = [encoding]
        with self.assertRaises(ValueError): load(document)  # Not a per-output list.
        bad_cases = {
            'missing tile': dict(encoding, tiles=tiles[:2]),
            'reordered': dict(encoding, tiles=[tiles[1], tiles[0], tiles[2]]),
            'wrong rect': dict(encoding, tiles=[tiles[0], tile('projector 2', 0, 0), tiles[2]]),
            'unknown output': dict(encoding, tiles=[tiles[0], tiles[1], tile('projector 4', 0, 0, 10)]),
            'wrong scale': dict(encoding, scale_denominator=1),
            'too small': dict(encoding, composite_width=399),
            'lost depth': dict(encoding, native_pixel_format='rgba8_bottom_up'),
            'tile depth': dict(encoding, tiles=[tiles[0], tiles[1], tile('projector 3', 0, 0)]),
            'rate': dict(encoding, timing=dict(timing(), rate_numerator=120)),
            'unknown pacing': dict(encoding, timing=dict(timing(), pacing_output_id='projector 9')),
        }
        for name, bad in bad_cases.items():
            document['review_encoding'] = bad
            with self.subTest(case=name), self.assertRaises(ValueError): load(document)

        document['display']['photodiode_enabled'] = False
        document['display']['pacing_output_id'] = None
        unpaced = dict(encoding, timing=dict(timing(), pacing_output_id=None))
        document['review_encoding'] = unpaced
        self.assertIsNone(load(document).review_encoding.timing.pacing_output_id)
        document['display']['outputs'][1]['refresh_numerator'] = 30
        with self.assertRaisesRegex(ValueError, 'common nominal'):
            load(document)

    def test_arena_boundary_coverage(self):
        document = prepared([arena_block()])
        with self.assertRaises(ValueError): load(document)
        document['arena_boundaries']['bindings'] = [{'instance_id': 'arena', 'world_frame_id': 'world',
                                                     'region': {'kind': 'unrestricted'}}]
        load(document)
        document['arena_boundaries']['bindings'][0]['world_frame_id'] = 'other'
        with self.assertRaises(ValueError): load(document)
        document = prepared()
        document['arena_boundaries']['bindings'] = [{'instance_id': 'unused', 'world_frame_id': 'world',
                                                     'region': {'kind': 'unrestricted'}}]
        with self.assertRaises(ValueError): load(document)

    def test_fingerprint_logical_path_is_portable(self):
        base = {'resource_id': 'r', 'subresource': None, 'sha256': '0'*64, 'bytes': 1}
        Fingerprint.model_validate_json(json.dumps(dict(base, logical_path='media/a.png')))
        for bad in ('../a.png', '/abs/a.png', 'C:/a.png', 'media\\a.png', 'a//b', './a'):
            with self.subTest(path=bad), self.assertRaises(ValueError):
                Fingerprint.model_validate_json(json.dumps(dict(base, logical_path=bad)))

    def test_manifest_cycle_check_is_iterative(self):
        def manifest(edges):
            return json.dumps({'format_version': 1, 'provenance': [], 'resources': [
                {'fingerprint': {'resource_id': f'r{i}', 'logical_path': f'r{i}.bin', 'subresource': None,
                                 'sha256': '0'*64, 'bytes': 1},
                 'kind': 'shader', 'profile_id': 'p', 'dependencies': deps, 'interpretation': None,
                 'cpu_bytes': 0, 'gpu_bytes': 0, 'provider_compatibility': 'c'} for i, deps in enumerate(edges)]})
        n = 3000
        chain = [[f'r{i+1}'] if i + 1 < n else [] for i in range(n)]
        ResourceManifest.model_validate_json(manifest(chain))
        chain[-1] = ['r0']
        with self.assertRaises(ValueError) as caught: ResourceManifest.model_validate_json(manifest(chain))
        self.assertIn('cycle', str(caught.exception))
        with self.assertRaises(ValueError): ResourceManifest.model_validate_json(manifest([['r0']]))
        ResourceManifest.model_validate_json(manifest([['r1', 'r2'], ['r2'], []]))  # Shared diamond, no cycle.

class EvidenceFixTests(unittest.TestCase):
    def submission(self, **fields):
        payload = {'output_id': 'projector 1', 'attempt_index': 0,
                   'phase': 'attempt', 'entry_host_ns': 10, 'return_host_ns': None, 'swap_interval': 1,
                   'marker_index': None, 'marker_high': None, 'failure_code': None}
        payload.update(fields)
        if payload['phase'] == 'cutoff_excluded':
            if 'entry_host_ns' not in fields: payload['entry_host_ns'] = None
            if 'attempt_index' not in fields: payload['attempt_index'] = None
        return parse_evidence_json(json.dumps({'payload': {'kind': 'group_update', 'group_id': 0,
            'submissions': [payload], 'captures': []}}), max_bytes=BUDGET)

    def test_submission_outcomes(self):
        self.submission(phase='failed', failure_code='device_lost', return_host_ns=12)
        for bad in ({'phase': 'failed'}, {'phase': 'failed', 'failure_code': ''},
                    {'phase': 'unknown', 'return_host_ns': 12}):
            with self.subTest(fields=bad), self.assertRaises(ValueError): self.submission(**bad)
        self.submission(phase='unknown')

    def test_cutoff_excluded_render_group_output(self):
        self.submission(phase='cutoff_excluded')
        for bad in ({'return_host_ns': 12}, {'failure_code': 'x'}, {'marker_index': 0, 'marker_high': True},
                    {'entry_host_ns': 10}, {'attempt_index': 0}):
            with self.subTest(fields=bad), self.assertRaises(ValueError): self.submission(phase='cutoff_excluded', **bad)

    def feedback(self, **fields):
        payload = {'kind': 'feedback', 'stream_id': 's', 'result_id': 'r', 'reset_generation': 'g',
                   'binding_id': 'b', 'group_id': 3, 'source_frame_ids': ['f1', 'f2'],
                   'source_receipt_ns': 100, 'application_check_ns': 100, 'age_limit_ns': 50,
                   'disposition': 'applied', 'requested_increment': [1.0], 'applied_increment': [1.0],
                   'target_units': ['mm'], 'target_frame_id': 'world'}
        payload.update(fields)
        return parse_evidence_json(json.dumps({'payload': payload}), max_bytes=BUDGET)

    def test_applied_feedback_identity_frames_and_age_order(self):
        self.assertEqual(self.feedback().payload.source_frame_ids, ('f1', 'f2'))
        for bad in ({'binding_id': None}, {'group_id': None}, {'source_frame_ids': []},
                    {'application_check_ns': 99}):
            with self.subTest(fields=bad), self.assertRaises(ValueError): self.feedback(**bad)
        self.feedback(disposition='absent', binding_id=None, group_id=None, source_frame_ids=[])

    def test_capture_carries_video_frame_index_not_timestamps(self):
        def outcome(**fields):
            capture = {'disposition': 'admitted', 'video_frame_index': 0,
                       'source_pixel_format': 'rgba8', 'encoder_pixel_format': None, 'failure_code': None}
            capture.update(fields)
            return json.dumps({'payload': {'kind': 'group_update', 'group_id': 0, 'submissions': [],
                'captures': [capture]}})
        parse_evidence_json(outcome(), max_bytes=BUDGET)
        parse_evidence_json(outcome(disposition='capacity_drop', video_frame_index=None), max_bytes=BUDGET)
        for bad in ({'output_id': 'o'},  # Capture refers to the single composite stream.
                    {'encoder_timestamp': None}, {'disposition': 'timestamp_collision_drop'}):
            with self.subTest(fields=bad), self.assertRaises(ValueError):
                parse_evidence_json(outcome(**bad), max_bytes=BUDGET)

class GroupedEvidenceTests(unittest.TestCase):
    def test_late_updates_cannot_replace_state_or_be_empty(self):
        update = {'kind': 'group_update', 'group_id': 3, 'submissions': [], 'captures': [
            {'disposition': 'transfer_complete', 'video_frame_index': 0,
             'source_pixel_format': 'rgba8', 'encoder_pixel_format': None, 'failure_code': None}]}
        def parse(value):
            return parse_evidence_json(json.dumps({'payload': value}), max_bytes=BUDGET)
        parse(update)  # Resolving the group's existing admission is a cross-record check.
        with self.assertRaises(ValueError): parse(dict(update, state={}))
        with self.assertRaises(ValueError): parse(dict(update, captures=[]))

    def test_reset_is_a_newer_result_generation_not_a_separate_line(self):
        # A06: results carry reset_generation; older pending results are old_generation lines.
        line = {'kind': 'feedback', 'stream_id': 's', 'result_id': 'r', 'reset_generation': '1',
                'binding_id': None, 'group_id': None, 'source_frame_ids': ['f1'],
                'source_receipt_ns': 100, 'application_check_ns': 100, 'age_limit_ns': None,
                'disposition': 'old_generation', 'requested_increment': [], 'applied_increment': [],
                'target_units': [], 'target_frame_id': None}
        parse_evidence_json(json.dumps({'payload': line}), max_bytes=BUDGET)
        reset = {'kind': 'feedback_reset', 'stream_id': 's', 'new_generation': 'g',
                 'entry_sequence': 1, 'observed_host_ns': 10, 'application_check_ns': 12}
        with self.assertRaises(ValueError):
            parse_evidence_json(json.dumps({'payload': reset}), max_bytes=BUDGET)

class PhotometricFixTests(unittest.TestCase):
    def test_conditions_required_and_unique(self):
        profile = {'output_id': 'p', 'device_identity': 'd', 'width_px': 1, 'height_px': 1,
                   'refresh_numerator': 60, 'refresh_denominator': 1, 'rgb_bits': [8, 8, 8],
                   'signal_encoding': 'full_range_rgb_device_codes',
                   'conditions': [{'name': 'mode', 'value': 'native'}]}
        OutputBinding.model_validate_json(json.dumps(profile))
        for bad in ([], [{'name': 'mode', 'value': 'a'}, {'name': 'mode', 'value': 'b'}]):
            with self.subTest(conditions=bad), self.assertRaises(ValueError):
                OutputBinding.model_validate_json(json.dumps(dict(profile, conditions=bad)))




class AuditBoundaryTests(unittest.TestCase):
    def test_feedback_age_boundary_and_stale_contribution(self):
        from evidence_model import FeedbackEvidence
        base=dict(kind='feedback',stream_id='s',result_id='r',reset_generation='g',
                  binding_id='b',group_id=0,source_frame_ids=('0',),source_receipt_ns=100,
                  application_check_ns=150,age_limit_ns=50,disposition='applied',
                  requested_increment=(1.,),applied_increment=(1.,),target_units=('mm',),target_frame_id='world')
        FeedbackEvidence.model_validate(base)
        FeedbackEvidence.model_validate(base|dict(disposition='stale',application_check_ns=151,applied_increment=(0.,)))
        for change in ({'age_limit_ns':None},{'age_limit_ns':0},{'application_check_ns':151},
                       {'disposition':'stale','applied_increment':(0.,)},
                       {'disposition':'stale','application_check_ns':151}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                FeedbackEvidence.model_validate(base|change)

    def test_expanded_duration_int64_overflow(self):
        doc=fixture()
        doc['sequence'][0]['duration']['duration']['seconds']='9223372036.854775807'
        with self.assertRaisesRegex(ValueError,'expanded duration'):
            parse(doc)

if __name__ == '__main__':
    unittest.main()
