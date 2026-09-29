"""Pure V24/T36 heading-relative feedback checks; no renderer or tracking runtime."""
from pathlib import Path
import copy
import json
import math
import sys
import unittest
from typing import get_args
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT.parent / 'tracking'))
from program_model import parse_program_json
from parameter_catalogue import InputUnit, MOVEMENT_GAIN_UNITS
from planar_feedback import planar_feedback_increment
from pipeline_catalogue import CHANNELS

BUDGET = 1_000_000

def constant(value):
    return {'kind': 'constant', 'value': value}

def arena_program(bindings, channels=None):
    source = json.loads((ROOT / 'examples/drift-hold.json').read_text())
    source['assets'] = [{'asset_id': 'room', 'logical_path': 'arena/room.glb',
                         'color_override': None, 'profile': 'glb2_static_unlit_v1'}]
    source['instances'] = [{'instance_id': 'arena', 'family': 'arena'}]
    source['scenes'] = [{'scene_id': 'scene', 'background_linear_rgb': [0, 0, 0],
                         'arena_instance_id': 'arena', 'layer_instance_ids': []}]
    source['input_channels'] = channels if channels is not None else [
        {'channel_id': c.channel_id, 'stream_id': 'tracking', 'value_kind': c.quantity,
         'unit': c.unit, 'frame_id': c.coordinate_frame} for c in CHANNELS]
    block = {'kind': 'arena', 'instance_id': 'arena', 'asset_id': 'room', 'world_frame_id': 'world',
             'asset_to_world': [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
             'initial': {'position_mm': [0, 0], 'yaw_deg': 0}, 'fixed_height_mm': 0,
             'fixed_pitch_deg': 0, 'fixed_roll_deg': 0,
             'motion': {'x': {'kind': 'hold'}, 'y': {'kind': 'hold'}, 'yaw': {'kind': 'hold'}},
             'reset': False, 'assignments': [], 'feedback': bindings}
    for epoch in source['sequence']: epoch['settings'] = [copy.deepcopy(block)]
    return source

def parse(document):
    return parse_program_json(json.dumps(document), max_bytes=BUDGET)

PLANAR = {'binding_id': 'walk', 'operation': 'heading_relative_planar_integration',
          'forward_channel': 'forward_drive', 'sideways_channel': 'sideways_drive',
          'gain': constant(0.1)}
TURN = {'binding_id': 'turn', 'source_channel': 'turn_drive', 'target': 'yaw',
        'operation': 'movement_integration', 'gain': constant(1), 'offset': constant(0)}

class SignConventionTests(unittest.TestCase):
    def step(self, yaw=0., forward=0., sideways=0., turn=0.):
        return planar_feedback_increment(yaw_before_deg=yaw, forward=forward, sideways=sideways,
            linear_gain_mm=1., turn=turn, turn_gain_deg_per_rad=math.degrees(1.),
            turn_offset_deg_per_s=0., dt_s=1.)
    def close(self, actual, expected):
        for a, e in zip(actual, expected): self.assertAlmostEqual(a, e, places=12)
    def test_player_motion_sign_convention(self):
        self.close(self.step(forward=1.), (0., 1., 0.))       # forward at psi=0 is +Y.
        self.close(self.step(sideways=1.), (-1., 0., 0.))     # animal-left at psi=0 is -X.
        self.assertGreater(self.step(turn=1.)[2], 0.)          # +turn (animal-left) raises yaw.
        self.close(self.step(yaw=90., forward=1.), (-1., 0., 0.))
    def test_midpoint_heading_and_rejected_interval(self):
        dx, dy, dyaw = self.step(forward=1., turn=math.pi/2)  # 90 deg turn over the interval.
        self.assertAlmostEqual(dyaw, 90.)
        self.close((dx, dy), (-math.sin(math.pi/4), math.cos(math.pi/4)))
        for dt in (0., -1., math.nan):
            with self.subTest(dt=dt), self.assertRaises(ValueError):
                planar_feedback_increment(yaw_before_deg=0., forward=1., sideways=0., linear_gain_mm=1.,
                    turn=0., turn_gain_deg_per_rad=1., turn_offset_deg_per_s=0., dt_s=dt)

class TrackingChannelBindingTests(unittest.TestCase):
    def test_every_tracking_channel_is_a_vr_input_and_binds(self):
        self.assertEqual({c.channel_id for c in CHANNELS}, {'forward_drive', 'sideways_drive', 'turn_drive'})
        for c in CHANNELS:
            with self.subTest(channel=c.channel_id):
                self.assertIn(c.unit, get_args(InputUnit))
                self.assertEqual((c.quantity, c.coordinate_frame), ('interval_average_rate', 'anatomical_body'))
        units = {c.channel_id: c.unit for c in CHANNELS}
        self.assertEqual(MOVEMENT_GAIN_UNITS[('interval_average_rate', units['forward_drive'], 'mm')].output_unit, 'mm/s')
        self.assertEqual(MOVEMENT_GAIN_UNITS[('interval_average_rate', units['turn_drive'], 'deg')].output_unit, 'deg/s')
        parse(arena_program([PLANAR, TURN]))

    def test_condition_gain_units_follow_input_units(self):
        source = arena_program([PLANAR | {'gain': constant({'kind': 'condition', 'group_id': 'g', 'column_id': 'gain'})}])
        source['sequence'] = [{'kind': 'group', 'group_id': 'g', 'repetitions': 1, 'order': 'as_listed',
            'order_unit': 'condition_rows', 'conditions': {'columns': [{'column_id': 'gain', 'value_type': 'number',
            'unit': {'kind': 'feedback_gain', 'input_unit': 'px/s', 'output_unit': 'mm/s', 'coefficient': 'value'}}],
            'rows': [{'row_id': 'r', 'cells': [{'column_id': 'gain', 'value': 0.1}]}]}, 'body': source['sequence']}]
        parse(source)
        source['sequence'][0]['conditions']['columns'][0]['unit']['output_unit'] = 'deg/s'
        with self.assertRaises(ValueError): parse(source)

    def test_body_frame_and_pair_violations_rejected(self):
        world = [{'channel_id': 'forward_drive', 'stream_id': 'tracking', 'value_kind': 'interval_average_rate',
                  'unit': 'px/s', 'frame_id': 'camera'},
                 {'channel_id': 'sideways_drive', 'stream_id': 'tracking', 'value_kind': 'interval_average_rate',
                  'unit': 'px/s', 'frame_id': 'camera'}]
        direct = {'binding_id': 'b', 'source_channel': 'forward_drive', 'operation': 'movement_integration',
                  'gain': constant(1), 'offset': constant(0)}
        cases = {'forward to world x': arena_program([direct | {'target': 'x'}]),
                 'sideways to world y': arena_program([direct | {'source_channel': 'sideways_drive', 'target': 'y'}]),
                 'turn as direct yaw': arena_program([TURN | {'operation': 'direct_value'}]),
                 'same channel twice': arena_program([PLANAR | {'sideways_channel': 'forward_drive'}]),
                 'turn as sideways': arena_program([PLANAR | {'sideways_channel': 'turn_drive'}]),
                 'unknown channel': arena_program([PLANAR | {'sideways_channel': 'missing'}]),
                 'offset on planar': arena_program([PLANAR | {'offset': constant(0)}]),
                 'world-frame pair': arena_program([PLANAR], world)}
        texture = json.loads((ROOT / 'examples/drift-hold.json').read_text())
        texture['input_channels'] = arena_program([])['input_channels']
        texture['sequence'][0]['settings'][0]['feedback'] = [PLANAR]
        cases['non-arena target'] = texture
        for name, document in cases.items():
            with self.subTest(case=name), self.assertRaises(ValueError): parse(document)
        parse(arena_program([direct | {'target': 'x'}], world))  # World-frame channels keep V24 bindings.

if __name__ == '__main__':
    unittest.main()
