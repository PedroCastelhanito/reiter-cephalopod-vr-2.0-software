"""Pure V03/V05/V24/V28 regression checks; no backend or rig simulation."""
from pathlib import Path
import copy
import json
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schema_common import Model, Version1, parse_json
from program_model import parse_program_json
from artifact_models import GeometricProfile, PreparedTrial
from display_profile import Output
from photometric_profile import OutputBinding
from evidence_model import EvidenceRecord, parse_evidence_json

BUDGET = 1_000_000

def fixture():
    return json.loads((Path(__file__).resolve().parents[1] / 'examples/drift-hold.json').read_text())

def parse(document):
    return parse_program_json(json.dumps(document), max_bytes=BUDGET)

def group(document, unit):
    document['sequence'] = [{
        'kind': 'group', 'group_id': 'conditions', 'repetitions': 1,
        'order': 'as_listed', 'order_unit': 'condition_rows',
        'conditions': {'columns': [{'column_id': 'value', 'value_type': 'number', 'unit': unit}],
                       'rows': [{'row_id': 'row', 'cells': [{'column_id': 'value', 'value': 1}]}]},
        'body': document['sequence']}]
    return {'kind': 'condition', 'group_id': 'conditions', 'column_id': 'value'}

def settings(document):
    return document['sequence'][0]['settings'][0]

class ProgramTests(unittest.TestCase):
    def test_version_complete_settings_and_no_redundant_units(self):
        source = fixture()
        self.assertEqual(parse(source).format_version, 2)
        for version in (1, True, 2.0, '2'):
            bad = copy.deepcopy(source); bad['format_version'] = version
            with self.subTest(version=version), self.assertRaises(ValueError): parse(bad)
        for mutate in (lambda s: s.pop('opacity'),
                       lambda s: s['opacity'].update(unit='1'),
                       lambda s: s['opacity'].update(value=True)):
            bad = copy.deepcopy(source); mutate(settings(bad))
            with self.assertRaises(ValueError): parse(bad)

    def test_condition_coefficient_units_follow_destination(self):
        cases = [('width', 'constant', 'value', 'mm'),
                 ('width', 'ramp', 'slope_per_s', 'mm/s'),
                 ('opacity', 'sine', 'frequency_hz', '1/s'),
                 ('opacity', 'sine', 'phase_cycles', 'cycle')]
        templates = {'constant': {'kind': 'constant', 'value': 1},
                     'ramp': {'kind': 'ramp', 'initial': 1, 'slope_per_s': 1},
                     'sine': {'kind': 'sine', 'mean': 0.5, 'amplitude': 0.5,
                              'frequency_hz': 1, 'phase_cycles': 0}}
        for parameter, kind, coefficient, unit in cases:
            source = fixture(); block = settings(source)
            block[parameter] = copy.deepcopy(templates[kind])
            block[parameter][coefficient] = group(source, unit)
            with self.subTest(parameter=parameter, coefficient=coefficient):
                parse(source)
                source['sequence'][0]['conditions']['columns'][0]['unit'] = 'px'
                with self.assertRaises(ValueError): parse(source)

    def test_coordinate_choice_changes_receiving_unit(self):
        source = fixture(); block = settings(source)
        block['space'] = {'kind': 'visual_angle', 'frame_id': 'observer frame',
                          'frame_to_rig_xyzw': [0, 0, 0, 1], 'surfaces': ['front']}
        block['width']['value'] = group(source, 'deg')
        parse(source)
        source['sequence'][0]['conditions']['columns'][0]['unit'] = 'mm'
        with self.assertRaises(ValueError): parse(source)

    def test_feedback_gain_descriptor_and_movement_source(self):
        source = fixture(); block = settings(source)
        source['input_channels'] = [{'channel_id': 'movement', 'stream_id': 'tracking',
            'value_kind': 'displacement', 'unit': 'px', 'frame_id': 'camera frame'}]
        gain_unit = {'kind': 'feedback_gain', 'input_unit': 'px',
                     'output_unit': 'mm', 'coefficient': 'value'}
        reference = group(source, gain_unit)
        block['feedback'] = [{'binding_id': 'translate', 'source_channel': 'movement',
            'target': 'x', 'operation': 'movement_integration',
            'gain': {'kind': 'constant', 'value': reference},
            'offset': {'kind': 'constant', 'value': 0}}]
        parse(source)
        source['sequence'][0]['conditions']['columns'][0]['unit']['output_unit'] = 'deg'
        with self.assertRaises(ValueError): parse(source)
        source['sequence'][0]['conditions']['columns'][0]['unit']['output_unit'] = 'mm'
        source['input_channels'][0]['value_kind'] = 'absolute'
        with self.assertRaises(ValueError): parse(source)

    def test_movement_offset_rate_units_and_gain_slope(self):
        for gain in (False, True):
            source = fixture(); block = settings(source)
            source['input_channels'] = [{'channel_id': 'movement', 'stream_id': 'tracking',
                'value_kind': 'interval_average_rate', 'unit': 'px/s', 'frame_id': 'camera'}]
            unit = ({'kind': 'feedback_gain', 'input_unit': 'px/s', 'output_unit': 'mm/s',
                     'coefficient': 'slope_per_s'} if gain else 'mm/s')
            reference = group(source, unit)
            block['feedback'] = [{'binding_id': 'translate', 'source_channel': 'movement',
                'target': 'x', 'operation': 'movement_integration',
                'gain': {'kind': 'ramp', 'initial': 1, 'slope_per_s': reference if gain else 0},
                'offset': {'kind': 'constant', 'value': 0 if gain else reference}}]
            parse(source)
            source['sequence'][0]['conditions']['columns'][0]['unit'] = 'mm'
            with self.assertRaises(ValueError): parse(source)

class SharedSchemaTests(unittest.TestCase):
    def test_identical_opaque_output_ids_across_artifacts(self):
        output = {'output_id': 'projector 1', 'device_identity': r'\\?\DISPLAY#native',
                  'width_px': 100, 'height_px': 100, 'refresh_numerator': 60,
                  'refresh_denominator': 1, 'rgb_bits_per_channel': 8}
        self.assertEqual(Output.model_validate_json(json.dumps(output)).output_id, 'projector 1')
        profile = {k:v for k,v in output.items() if k != 'rgb_bits_per_channel'}
        profile.update(rgb_bits=[8,8,8], signal_encoding='full_range_rgb_device_codes',
                       conditions=[{'name': 'picture_mode', 'value': 'native'}])
        self.assertEqual(OutputBinding.model_validate_json(json.dumps(profile)).output_id, 'projector 1')
        geom = {'format_version': 1, 'calibration_id': 'calibration 1', 'mapping_id': 'mapping 1',
                'surface_id': 'front', 'output_id': 'projector 1', 'output_width': 100,
                'output_height': 100, 'viewport': {'x':0,'y':0,'width':100,'height':100},
                'rows':2,'columns':2,
                'vertices':[{'uv':p,'xy':p} for p in ([0,0],[1,0],[0,1],[1,1])],
                'orientation':'preserving','diagonal':'bottom_left_to_top_right',
                'mask':None,'weight':None,'overlap_group':None,
                'intended_coverage':[[0,0],[1,0],[1,1],[0,1]],
                'coverage_tolerance':0.001,'triangle_area_tolerance':0.001}
        self.assertEqual(GeometricProfile.model_validate_json(json.dumps(geom)).output_id, 'projector 1')
        for points in ([], [[0,0]], [[0,0],[1,0]]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                GeometricProfile.model_validate_json(json.dumps(geom | {'intended_coverage':points}))
        record = parse_evidence_json(evidence(), max_bytes=BUDGET)
        self.assertEqual(record.payload.submissions[0].output_id, 'projector 1')

    def test_shared_parser_rejects_duplicates_nonfinite_and_invalid_limits(self):
        class Sample(Model):
            format_version: Version1
            text: str
        good = json.dumps({'format_version':1,'text':'escaped " [ { \\ text'})
        self.assertEqual(parse_json(Sample,good,max_bytes=1000,max_depth=1).format_version,1)
        for bad in ('{"format_version":1,"format_version":1,"text":"x"}',
                    '{"format_version":1,"text":NaN}',
                    '{"format_version":true,"text":"x"}',
                    '{"format_version":1.0,"text":"x"}'):
            with self.assertRaises(ValueError): parse_json(Sample,bad,max_bytes=1000)
        with self.assertRaises(ValueError): parse_json(Sample,good,max_bytes=1)
        with self.assertRaises(ValueError): parse_json(Sample,'{"text":[[]]}',max_bytes=100,max_depth=1)
        for depth in (True,0,-1,64.5):
            with self.assertRaises(ValueError): parse_program_json(json.dumps(fixture()),max_bytes=BUDGET,max_depth=depth)

    def test_single_prepared_plan_has_nested_manifest(self):
        schema = PreparedTrial.model_json_schema()
        self.assertIn('manifest',schema['properties'])
        self.assertNotIn('schedule',schema['properties'])
        self.assertNotIn('resolved_duration_ns',schema['properties'])
        epoch = schema['$defs']['CompiledEpoch']['properties']
        self.assertIn('duration_origin',epoch)
        self.assertIn('settings',epoch)

def evidence():
    # One JSON line; noncanonical spaces/escaping are valid JSON.
    return '{ "payload" : { "kind":"group_update", "group_id":0, "captures":[], "submissions":[{ "output_id":"projector\\u00201", "attempt_index":0, "phase":"attempt", "entry_host_ns":10, "return_host_ns":null, "swap_interval":1, "marker_index":null, "marker_high":null, "failure_code":null }] } }'

class EvidenceTests(unittest.TestCase):
    def test_json_line_round_trips_as_one_line(self):
        record = parse_evidence_json(evidence(),max_bytes=BUDGET)
        self.assertIsInstance(record,EvidenceRecord)
        line = record.model_dump_json()
        self.assertNotIn('\n',line)
        self.assertEqual(parse_evidence_json(line,max_bytes=BUDGET),record)

    def test_bounds_and_duplicate_rejection(self):
        payload = evidence()
        with self.assertRaises(ValueError): parse_evidence_json(payload,max_bytes=1)
        with self.assertRaises(ValueError): parse_evidence_json(payload.replace('"group_id":0','"group_id":0,"group_id":1'),max_bytes=BUDGET)

if __name__ == '__main__':
    unittest.main()
