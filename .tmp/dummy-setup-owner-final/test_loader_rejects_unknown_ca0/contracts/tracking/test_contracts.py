"""Pure tracking boundary tests. No hardware, runtime or experimental-file I/O."""
import copy
import json
from pathlib import Path
import sys
import tomllib
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'visual_stimulus'))
from method_models import parse_method
from record_models import PoseUse, TrackingRecord, parse_record
from record_codec import encode_line, decode_lines
from schema_common import parse_json

BUDGET=100_000
UUID='12345678-1234-4234-8234-123456789abc'
MANIFEST=dict(schema_version=1,adapter='onnx_triplet_v1',model={'relative_path':'model.onnx'},
 external_weights=[{'relative_path':'weights.bin'}],input_name='image',output_name='pose',
 input_width_px=640,input_height_px=480,channels='rgb',mean=[0.,0.,0.],std=[1.,1.,1.],
 padding_source_fraction=[0.,0.,0.],maximum_candidates=16)
FLOW=dict(schema_version=1,adapter='nvof_cuda_v1',device_ordinal=0,output_grid_px=4,
 preset='medium',temporal_hints=True,output_cost=False,input_mapping='declared_full_range_gray8_v1')
GEOMETRY=dict(schema_version=2,front_fraction=.6,
 taper=.4,squareness=3.5,inner_clearance_fraction=.1,outer_extent_fraction=.3)
# Test inputs only; these shape/band numbers are not adopted runtime defaults.
POSE=dict(kind='pose',observation_id='p0',reset_generation='1',
 source={'frame_id':0,'host_receipt_ns':100},completion_host_ns=110,method='keypoint_model',
 validity='valid',reason=None,landmarks={'tip':{'x_px':1.1234567890123457,'y_px':2.0},
 'left_base':{'x_px':4.0,'y_px':5.0},'right_base':{'x_px':6.0,'y_px':7.0}},
 eligible_candidate_count=1,selected_score=0.9,top_score_tie=False,disposition='published')
USE=dict(disposition='valid',observation_id='p0',manual_geometry_id=None,check_host_ns=110,
 pose_source_host_ns=100,age_ns=10,maximum_age_ns=10)

def record(value):return parse_record(json.dumps({'record':value}),max_bytes=BUDGET)
def parse(model,value):return parse_json(model,json.dumps(value),max_bytes=BUDGET)

class ContractTests(unittest.TestCase):
    def test_model_layout_and_weight_paths(self):
        self.assertEqual(parse_method('model-manifest',json.dumps(MANIFEST),max_bytes=BUDGET).channels,'rgb')
        for path in ('../weights','/absolute','a//b','a\\b'):
            with self.subTest(path=path),self.assertRaises(ValueError):
                m=copy.deepcopy(MANIFEST);m['external_weights'][0]['relative_path']=path
                parse_method('model-manifest',json.dumps(m),max_bytes=BUDGET)
    def test_model_channel_normalization_mismatch(self):
        for change in ({'std':[1.,1.]},{'std':[1.,0.,1.]},{'input_width_px':0}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                parse_method('model-manifest',json.dumps(MANIFEST|change),max_bytes=BUDGET)
    def test_duplicate_weights(self):
        m=MANIFEST|{'external_weights':[{'relative_path':'model.onnx'}]}
        with self.assertRaises(ValueError):parse_method('model-manifest',json.dumps(m),max_bytes=BUDGET)
    def test_flow_grid_is_exact_integer_and_fixed_mapping(self):
        self.assertEqual(parse_method('flow-settings',json.dumps(FLOW),max_bytes=BUDGET).output_grid_px,4)
        for change in ({'output_grid_px':True},{'output_grid_px':4.0},{'output_grid_px':8},
                       {'input_mapping':'auto_histogram'},{'adapter':'dis'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                parse_method('flow-settings',json.dumps(FLOW|change),max_bytes=BUDGET)
    def test_contour_area_bounds(self):
        x=dict(schema_version=2,minimum_axis_anisotropy=.1,threshold_level=100.,
               foreground_polarity="dark",minimum_area_px2=20,maximum_area_px2=100,
               geometry_quality=dict(minimum_axis_px=1.,minimum_base_width_px=1.,minimum_triangle_area_px2=1.))
        parse_method('contour-settings',json.dumps(x),max_bytes=BUDGET)
        with self.assertRaises(ValueError):
            parse_method('contour-settings',json.dumps(x|{'maximum_area_px2':10}),max_bytes=BUDGET)

    def test_contour_requires_explicit_valid_axis_quality_and_new_version(self):
        x=dict(schema_version=2,minimum_axis_anisotropy=1.,threshold_level=100.,
               foreground_polarity="dark",minimum_area_px2=20,maximum_area_px2=100,
               geometry_quality=dict(minimum_axis_px=1.,minimum_base_width_px=1.,minimum_triangle_area_px2=1.))
        parse_method('contour-settings',json.dumps(x),max_bytes=BUDGET)
        for change in ({'schema_version':1},{'minimum_axis_anisotropy':0.},
                       {'minimum_axis_anisotropy':1.1},{'minimum_axis_anisotropy':True},
                       {'minimum_axis_anisotropy':float('nan')},{'minimum_axis_anisotropy':'0.1'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                parse_method('contour-settings',json.dumps(x|change),max_bytes=BUDGET)
        x.pop('minimum_axis_anisotropy')
        with self.assertRaises(ValueError):
            parse_method('contour-settings',json.dumps(x),max_bytes=BUDGET)

    def test_contour_registry_requires_matching_v2_contract(self):
        from stage_registry import builtin_registry
        from method_models import StageConfiguration
        payload=dict(schema_version=2,minimum_axis_anisotropy=.1,threshold_level=100.,
                     foreground_polarity="dark",minimum_area_px2=20,maximum_area_px2=100,
                     geometry_quality=dict(minimum_axis_px=1.,minimum_base_width_px=1.,minimum_triangle_area_px2=1.))
        selection=StageConfiguration(stage_id='pose',implementation_id='threshold_contour',
                                     settings_schema_id='tracking.contour-settings.v2',settings_json=json.dumps(payload))
        registry=builtin_registry()
        spec,_=registry.resolve(selection,max_bytes=BUDGET)
        self.assertEqual(spec.implementation_version,'2')
        with self.assertRaises(ValueError):
            registry.resolve(selection.model_copy(update={'settings_schema_id':'tracking.contour-settings.v1'}),max_bytes=BUDGET)

    def test_deadlines_resolve_to_ns(self):
        x=dict(schema_version=1,max_document_bytes=1,max_asset_bytes=1,max_native_bytes=1,
               maximum_message_bytes=1,pose_progress_timeout_s=.000000001,movement_progress_timeout_s=1.)
        parse_method('file-limits',json.dumps(x),max_bytes=BUDGET)
        for bad in (0.,1e-10,1e20):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                parse_method('file-limits',json.dumps(x|{'pose_progress_timeout_s':bad}),max_bytes=BUDGET)
    def test_strict_json_and_record_bounds(self):
        src=json.dumps({'record':POSE})
        for bad in (src.replace('"frame_id": 0','"frame_id": 0, "frame_id": 1'),
                    src.replace('0.9','NaN'),src.replace('"kind": "pose"','"kind": "pose", "extra": 1')):
            with self.subTest(bad=bad),self.assertRaises(ValueError):parse_record(bad,max_bytes=BUDGET)
        with self.assertRaises(ValueError):parse_record(src,max_bytes=1)
    def test_float64_triplet_json_line_roundtrip(self):
        r=record(POSE);data=encode_line(r,max_bytes=BUDGET)
        self.assertEqual((data.count(b'\n'),data[-1:]),(1,b'\n'))
        restored,tail=decode_lines(data,max_bytes=BUDGET)
        self.assertEqual((restored,tail),((r,),0))
        self.assertEqual(restored[0].record.landmarks.tip.x_px,1.1234567890123457)
    def test_incomplete_final_line_discarded_complete_lines_strict(self):
        # T19: no envelope/checksum; only bytes after the last LF are discarded.
        data=encode_line(record(POSE),max_bytes=BUDGET)
        self.assertEqual(decode_lines(data*2+data[:-5],max_bytes=BUDGET)[1],len(data)-5)
        self.assertEqual(decode_lines(data[:-1],max_bytes=BUDGET),((),len(data)-1))
        for bad in (data[:-5]+b'\n'+data,b'\n'+data):
            with self.subTest(size=len(bad)),self.assertRaises(ValueError):decode_lines(bad,max_bytes=BUDGET)
    def test_line_limit_excludes_lf(self):
        data=encode_line(record(POSE),max_bytes=BUDGET)
        encode_line(record(POSE),max_bytes=len(data)-1)
        with self.assertRaises(ValueError):encode_line(record(POSE),max_bytes=len(data)-2)
    def test_native_frame_zero_and_invalid_candidate_evidence(self):
        self.assertEqual(record(POSE).record.source.frame_id,0)
        for change in ({'eligible_candidate_count':0},{'top_score_tie':True},{'completion_host_ns':99},
                       {'validity':'invalid'},{'selected_score':0.}):
            with self.subTest(change=change),self.assertRaises(ValueError):record(POSE|change)
        invalid=POSE|dict(validity='invalid',reason='no_candidate',landmarks=None,
                          eligible_candidate_count=0,selected_score=None,top_score_tie=False)
        self.assertIsNone(record(invalid).record.landmarks)
    def test_pose_age_accepts_equality_rejects_stale_as_valid(self):
        self.assertEqual(parse(PoseUse,USE).age_ns,10)
        with self.assertRaises(ValueError):parse(PoseUse,USE|{'maximum_age_ns':9})
        self.assertEqual(parse(PoseUse,USE|{'disposition':'stale','maximum_age_ns':9}).disposition,'stale')
        with self.assertRaises(ValueError):parse(PoseUse,USE|{'disposition':'stale'})
    def test_pose_age_arithmetic_and_missing_identity(self):
        with self.assertRaises(ValueError):parse(PoseUse,USE|{'age_ns':9})
        with self.assertRaises(ValueError):parse(PoseUse,USE|{'disposition':'missing'})
        missing=USE|dict(disposition='missing',observation_id=None,pose_source_host_ns=None,age_ns=None)
        parse(PoseUse,missing)
    def test_manual_pose_has_no_fabricated_age(self):
        manual=USE|dict(disposition='manual',observation_id=None,manual_geometry_id='manual',
                        pose_source_host_ns=None,age_ns=None,maximum_age_ns=None)
        parse(PoseUse,manual)
        with self.assertRaises(ValueError):parse(PoseUse,manual|{'age_ns':0})
    def test_decoded_feedback_uses_owning_descriptor(self):
        x=dict(kind='result',feedback_result={'resultId':'exact','resultSequence':'9007199254740993'},produced_host_ns=111,pose=USE,stage_evidence=[])
        self.assertEqual(json.loads(record(x).record.feedback_result),x['feedback_result'])
        for bad in ({'protobuf_base64':'CA=='},{'unknown':1},{'resultSequence':9007199254740993}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):record(x|{'feedback_result':bad})
    def test_reset_line_has_generation_and_causes_not_marker_payload(self):
        # A06: the reset is a newer result generation; saving records it with its cause.
        x=dict(kind='reset',reset_generation='2',causes=['camera_gap','result_overflow'],observed_host_ns=5)
        self.assertEqual(record(x).record.causes,('camera_gap','result_overflow'))
        for change in ({'causes':[]},{'causes':['camera_gap','camera_gap']},{'causes':['visual_stimulus_stale']},
                       {'reset_generation':'0'},{'reset_generation':UUID},
                       {'feedback_reset_marker':{'protobuf_base64':'CA=='}},{'prior_generation':'1'}):
            with self.subTest(change=change),self.assertRaises(ValueError):record(x|change)

class EstimatorSubsetTests(unittest.TestCase):
    def test_fin_region_accepts_wrap_boundary_and_full_band(self):
        for offset,span in ((-180.,360.),(0.,90.),(179.9,0.01)):
            value=dict(schema_version=1,offset_degrees=offset,span_degrees=span)
            parsed=parse_method('fin-region-settings',json.dumps(value),max_bytes=BUDGET)
            self.assertEqual((parsed.offset_degrees,parsed.span_degrees),(offset,span))

    def test_fin_region_rejects_silent_clamping_and_implicit_defaults(self):
        base=dict(schema_version=1,offset_degrees=0.,span_degrees=180.)
        for change in ({'offset_degrees':180.},{'offset_degrees':-181.},
                       {'span_degrees':0.},{'span_degrees':361.},
                       {'offset_degrees':True},{'span_degrees':'90'},
                       {'span_degrees':float('nan')},{'schema_version':True},
                       {'split_wedge':True}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                parse_method('fin-region-settings',json.dumps(base|change),max_bytes=BUDGET)
        for field in ('offset_degrees','span_degrees'):
            with self.subTest(missing=field),self.assertRaises(ValueError):
                parse_method('fin-region-settings',json.dumps({k:v for k,v in base.items() if k!=field}),max_bytes=BUDGET)

    def test_support_fraction_requires_explicit_nonzero_bounded_value(self):
        base={'schema_version':1,'minimum_accepted_area_fraction':1.0}
        self.assertEqual(parse_method('section-flow-support-settings',json.dumps(base),max_bytes=BUDGET).minimum_accepted_area_fraction,1.)
        for bad in (0.,-0.1,1.1,True,'0.8',float('inf')):
            with self.subTest(value=bad),self.assertRaises(ValueError):
                parse_method('section-flow-support-settings',json.dumps(base|{'minimum_accepted_area_fraction':bad}),max_bytes=BUDGET)
        with self.assertRaises(ValueError):
            parse_method('section-flow-support-settings','{"schema_version":1}',max_bytes=BUDGET)

    def test_smoothing_requires_time_not_frame_count_or_disable_sentinel(self):
        base={'schema_version':1,'time_constant_s':.05} # Test value, not a default.
        self.assertEqual(parse_method('exponential-smoothing-settings',json.dumps(base),max_bytes=BUDGET).time_constant_s,.05)
        for change in ({'time_constant_s':0.},{'time_constant_s':-1.},
                       {'time_constant_s':True},{'time_constant_s':float('nan')},
                       {'time_constant_s':'0.05'},{'schema_version':True},
                       {'frames':3},{'retain_on_invalid':True}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                parse_method('exponential-smoothing-settings',json.dumps(base|change),max_bytes=BUDGET)
        with self.assertRaises(ValueError):
            parse_method('exponential-smoothing-settings','{"schema_version":1}',max_bytes=BUDGET)

class ExtensionTests(unittest.TestCase):
    def test_new_implementation_uses_same_selection_boundary(self):
        from stage_registry import StageSpec, builtin_registry
        from method_models import StageConfiguration
        from schema_common import Model
        class ResearchSettings(Model):
            gain: float
        registry=builtin_registry()
        spec=StageSpec('geometry','test_schema_only','research-1','test.settings.v1',
                       ResearchSettings,('tracking.landmark-triplet.v1',),'tracking.sampling-geometry.v1')
        registry.register(spec)
        selection=StageConfiguration(stage_id='geometry',implementation_id='test_schema_only',
                                     settings_schema_id='test.settings.v1',settings_json='{"gain":2.0}')
        chosen,settings=registry.resolve(selection,max_bytes=100)
        self.assertEqual(chosen,spec)
        self.assertEqual(settings.gain,2.)
        # Schema registration only; no test/fake runtime backend is created.
        with self.assertRaises(ValueError):registry.register(spec)
        with self.assertRaises(ValueError):registry.resolve(selection.model_copy(update={'settings_json':'{"gain":2,"hidden":1}'}),max_bytes=100)
    def test_unknown_implementation_schema_and_oversize_fail(self):
        from stage_registry import builtin_registry
        from method_models import StageConfiguration
        registry=builtin_registry()
        selection=StageConfiguration(stage_id='geometry',implementation_id='three_point_ellipse',
            settings_schema_id='tracking.ellipse-settings.v2',
            settings_json=json.dumps(GEOMETRY))
        _,settings=registry.resolve(selection,max_bytes=1000)
        self.assertEqual(settings.front_fraction,.6)
        for change in ({'implementation_id':'unknown'},{'settings_schema_id':'unknown'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                registry.resolve(selection.model_copy(update=change),max_bytes=1000)
        with self.assertRaises(ValueError):registry.resolve(selection,max_bytes=1)
    def test_ellipse_fraction_and_coverage_must_be_valid(self):
        x=GEOMETRY
        parse_method('ellipse-settings',json.dumps(x),max_bytes=BUDGET)
        for change in ({'front_fraction':0.},{'front_fraction':1.1},{'front_fraction':float('inf')},
                       {'minimum_visible_fraction':.9}): # T26/T44: no separate visibility gate.
            with self.subTest(change=change),self.assertRaises(ValueError):
                parse_method('ellipse-settings',json.dumps(x|change),max_bytes=BUDGET)
    def test_band_geometry_rejects_degenerate_missing_and_legacy_settings(self):
        parse_method('ellipse-settings',json.dumps(GEOMETRY|{'taper':0.,'squareness':2.,
                     'inner_clearance_fraction':0.}),max_bytes=BUDGET)
        changes=({'taper':-1.},{'taper':1.},{'squareness':0.},
                 {'inner_clearance_fraction':-.1},{'outer_extent_fraction':.1},
                 {'outer_extent_fraction':.05},{'outer_extent_fraction':float('inf')},
                 {'schema_version':1},{'schema_version':True},{'schema_version':2.0},
                 {'sectors':[]},{'camera_fixed':True})
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):
                parse_method('ellipse-settings',json.dumps(GEOMETRY|change),max_bytes=BUDGET)
        for field in ('taper','squareness','inner_clearance_fraction','outer_extent_fraction'):
            missing={k:v for k,v in GEOMETRY.items() if k!=field}
            with self.subTest(missing=field),self.assertRaises(ValueError):
                parse_method('ellipse-settings',json.dumps(missing),max_bytes=BUDGET)
    def test_geometry_registration_requires_new_schema(self):
        from stage_registry import builtin_registry
        from method_models import StageConfiguration
        registry=builtin_registry()
        selection=StageConfiguration(stage_id='geometry',implementation_id='three_point_ellipse',
             settings_schema_id='tracking.ellipse-settings.v2',settings_json=json.dumps(GEOMETRY))
        spec,settings=registry.resolve(selection,max_bytes=BUDGET)
        self.assertEqual(spec.implementation_version,'2')
        self.assertEqual(settings.outer_extent_fraction,.3)
        with self.assertRaises(ValueError):
            registry.resolve(selection.model_copy(update={'settings_schema_id':'tracking.ellipse-settings.v1'}),max_bytes=BUDGET)
    def test_section_count_is_explicit_exact_and_bounded(self):
        settings=parse_method('arc-section-settings','{"schema_version":1,"count":1}',max_bytes=BUDGET)
        self.assertEqual(settings.count,1)
        for count in (0,-1,True,1.0,'4',2**32):
            with self.subTest(count=count),self.assertRaises(ValueError):
                parse_method('arc-section-settings',json.dumps({'schema_version':1,'count':count}),max_bytes=BUDGET)
        for value in ({'schema_version':1},{'schema_version':1,'count':4,'method':'angular'},
                      {'schema_version':1,'count':4,'offset_degrees':90}):
            with self.subTest(value=value),self.assertRaises(ValueError):
                parse_method('arc-section-settings',json.dumps(value),max_bytes=BUDGET)
    def test_geometry_evidence_retains_missing_support(self):
        from record_models import GeometryEvidence
        x=dict(schema_version=1,regions=[dict(region_id='left',requested_pixels=100,
               visible_pixels=90,clipped_fraction=.1)])
        evidence=parse(GeometryEvidence,x)
        self.assertEqual(evidence.regions[0].visible_pixels,90)
        for change in ({'visible_pixels':101},{'clipped_fraction':0.},{'requested_pixels':0},
                       {'minimum_visible_fraction':.9}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                parse(GeometryEvidence,x|{'regions':[x['regions'][0]|change]})
        # Insufficient coverage is real evidence to retain, not a malformed record.
        low=x|{'regions':[x['regions'][0]|{'visible_pixels':50,'clipped_fraction':.5}]}
        self.assertEqual(parse(GeometryEvidence,low).regions[0].clipped_fraction,.5)
        with self.assertRaises(ValueError):parse(GeometryEvidence,x|{'regions':x['regions']*2})
    def test_stage_evidence_uses_registered_concrete_schema(self):
        from stage_registry import builtin_registry
        from method_models import StageConfiguration
        registry=builtin_registry()
        selection=StageConfiguration(stage_id='geometry',implementation_id='three_point_ellipse',
             settings_schema_id='tracking.ellipse-settings.v2',
             settings_json=json.dumps(GEOMETRY))
        spec,_=registry.resolve(selection,max_bytes=1000)
        registry.validate_evidence(spec,'tracking.geometry-evidence.v1','{"schema_version":1,"regions":[]}',max_bytes=1000)
        with self.assertRaises(ValueError):registry.validate_evidence(spec,'other','{}',max_bytes=1000)
        with self.assertRaises(ValueError):registry.validate_evidence(spec,'tracking.geometry-evidence.v1','{"dense_flow":[]}',max_bytes=1000)




class AuditBoundaryTests(unittest.TestCase):
    def test_landmark_coordinates_and_degeneracy(self):
        from record_models import Triplet
        valid=dict(tip={'x_px':0.,'y_px':0.},left_base={'x_px':2.,'y_px':1.},right_base={'x_px':2.,'y_px':3.})
        parse(Triplet,valid)
        for update in ({'tip':{'x_px':-1.,'y_px':0.}}, {'tip':valid['left_base']},
                       {'tip':{'x_px':2.,'y_px':2.}}):
            with self.subTest(update=update),self.assertRaises(ValueError):parse(Triplet,valid|update)

    def test_exact_prepared_methods_digest(self):
        import hashlib
        from record_models import Header
        methods='{"label":"é"}'
        identity=dict(session_id=UUID,trial_id=UUID,tracking_process_instance_id=UUID,
                      writer_generation=UUID,configuration_revision=1,prepared_generation=UUID,source_allocation_id=UUID)
        header=dict(kind='header',schema_version=2,stream_kind='tracking',identity=identity,
                    trial_start_host_ns=0,trial_normal_end_host_ns=100,pipeline_id='water_flow',pose_mode='manual',
                    prepared_methods_json=methods,prepared_methods_sha256=hashlib.sha256(methods.encode('utf8')).hexdigest(),
                    resolved_settings_json='{}',image_width_px=10,image_height_px=10)
        parse(Header,header)
        with self.assertRaises(ValueError):parse(Header,header|{'prepared_methods_json':methods+' '})

    def test_discard_source_ids_and_generation(self):
        from record_models import Discard
        base=dict(kind='discard',reset_generation=str((1<<64)-1),observed_host_ns=1,target='source_frame',ids=['0',str((1<<64)-1)],reason='input_age')
        parse(Discard,base)
        for value in ('01','-1','+1',' 1','1.0',str(1<<64)):
            with self.subTest(value=value),self.assertRaises(ValueError):parse(Discard,base|{'ids':[value]})
        for value in ('not-a-generation','0','01',str(1<<64),UUID):
            with self.subTest(generation=value),self.assertRaises(ValueError):parse(Discard,base|{'reset_generation':value})

class ConfigDefaultTests(unittest.TestCase):
    def test_tracking_config_defaults_load_and_validate(self):
        from pipeline_catalogue import resolve_pipeline
        from stage_registry import builtin_registry
        from method_models import StageConfiguration
        root=Path(__file__).resolve().parents[2]
        cfg=tomllib.loads((root/'config/backends/tracking_config.toml').read_text())
        policy=tomllib.loads((root/'contracts/policy/tracking_policy.toml').read_text())
        self.assertEqual(cfg['policy_version'],policy['policy_version'])
        self.assertEqual((cfg['pipeline']['name'],cfg['pose']['mode'],cfg['pose']['automatic_method'],
                          cfg['pose']['max_age_ms']),('water_flow','manual','threshold_contour',500))
        est=cfg['estimator']
        settings=dict(schema_version=1,sections=dict(schema_version=1,**est['sections']),
            quality=dict(schema_version=1,maximum_native_cost=None,**est['quality']),
            support=dict(schema_version=1,**est['support']),smoothing=dict(schema_version=1,**est['smoothing']))
        flow=dict(schema_version=1,adapter=policy['flow']['adapter'],input_mapping=policy['flow']['input_mapping'],**cfg['flow'])
        geometry=dict(schema_version=2,**cfg['geometry'])
        # Rig inputs have no defaults; these test values stand in for threshold/contour limits.
        contour=dict(schema_version=2,minimum_axis_anisotropy=.1,threshold_level=100.,foreground_polarity='dark',
            minimum_area_px2=20,maximum_area_px2=100,
            geometry_quality=dict(minimum_axis_px=1.,minimum_base_width_px=1.,minimum_triangle_area_px2=1.))
        rows=(('image_flow','nvidia_optical_flow','flow-settings',1,flow),
              ('geometry','three_point_ellipse','ellipse-settings',2,geometry),
              ('estimator','water_flow_proxy','water-flow-settings',1,settings))
        selections=tuple(StageConfiguration(stage_id=r,implementation_id=i,settings_schema_id=f'tracking.{n}.v{v}',
                         settings_json=json.dumps(x)) for r,i,n,v,x in rows)
        p=resolve_pipeline(cfg['pipeline']['name'],cfg['pose']['mode'],selections,builtin_registry(),max_bytes=BUDGET)
        resolved={s.stage_id:m for s,m in p.stages}
        self.assertEqual((resolved['geometry'].taper,resolved['geometry'].outer_extent_fraction,
                          resolved['estimator'].sections.count,resolved['estimator'].support.minimum_accepted_area_fraction,
                          resolved['estimator'].smoothing.time_constant_s,resolved['image_flow'].preset),
                         (.4,.75,12,.25,.08,'slow'))
        self.assertNotIn('minimum_visible_fraction',cfg['geometry'])

if __name__=='__main__':unittest.main()
