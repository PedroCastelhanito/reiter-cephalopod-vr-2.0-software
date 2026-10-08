"""Pure composition/record checks; test values are not rig tuning defaults."""
import copy
import json
import unittest
from dataclasses import replace
from test_contracts import FLOW, GEOMETRY, BUDGET, parse
from method_models import StageConfiguration, LocalMedianSettings, PreparedMethods
from record_models import FlowProxyEvidence
from stage_registry import builtin_registry, StageRegistry
from pipeline_catalogue import resolve_pipeline, validate_prepared, validate_proxy_evidence

QUALITY=dict(schema_version=1,radius_cells=1,minimum_neighbors=3,noise_floor_px=.1,
             maximum_normalized_residual=2.,maximum_native_cost=None)
SETTINGS=dict(schema_version=1,sections=dict(schema_version=1,count=2),quality=QUALITY,
              support=dict(schema_version=1,minimum_accepted_area_fraction=.8),
              smoothing=dict(schema_version=1,time_constant_s=.05))
CONTOUR=dict(schema_version=2,minimum_axis_anisotropy=.1,threshold_level=100.,foreground_polarity='dark',
             minimum_area_px2=20,maximum_area_px2=100,
             geometry_quality=dict(minimum_axis_px=1.,minimum_base_width_px=1.,minimum_triangle_area_px2=1.))

def configurations(family='water_flow', automatic=False, cost=False):
    settings=copy.deepcopy(SETTINGS)
    if family=='fin_flow':settings['fin_region']=dict(schema_version=1,offset_degrees=0.,span_degrees=90.)
    if cost:settings['quality']['maximum_native_cost']=100
    rows=[('image_flow','nvidia_optical_flow','flow-settings',1,FLOW|{'output_cost':cost}),
          ('geometry','three_point_ellipse','ellipse-settings',2,GEOMETRY),
          ('estimator',family+'_proxy',family.replace('_','-')+'-settings',1,settings)]
    if automatic:rows.append(('pose','threshold_contour','contour-settings',2,CONTOUR))
    return tuple(StageConfiguration(stage_id=role,implementation_id=impl,
                 settings_schema_id=f'tracking.{schema}.v{version}',settings_json=json.dumps(value))
                 for role,impl,schema,version,value in rows)

def resolved(family='water_flow',automatic=False,cost=False):
    return resolve_pipeline(family,'automatic' if automatic else 'manual',
                            configurations(family,automatic,cost),builtin_registry(),max_bytes=BUDGET)

def evidence(family='water_flow'):
    drives=dict(forward_drive=-1.,sideways_drive=-2.,turn_drive=-2.)
    return dict(schema_version=1,pipeline_id=family,validity='valid',reason=None,
                sections=[dict(section_index=i,intended_area_px2=10.,visible_area_px2=9.,accepted_area_px2=9.) for i in range(2)],
                counts=dict(selected=2,unavailable=0,nonfinite=0,cost_rejected=0,neighbor_unevaluable=0,median_rejected=0,accepted=2),
                centroid_body_px=[1.,1.],mean_velocity_body_px_per_s=[1.,2.],centred_moment_px2_per_s=3.,
                centred_second_moment_px2=1.5,
                raw=drives,filtered_average=drives,filter_end=drives,filter_disposition='seeded')

class PipelineTests(unittest.TestCase):
    def test_both_families_both_pose_modes_compose_canonical_stages(self):
        for family in ('water_flow','fin_flow'):
            for automatic in (False,True):
                with self.subTest(family=family,automatic=automatic):
                    p=resolved(family,automatic)
                    self.assertEqual([s.stage_id for s,m in p.stages],(['pose'] if automatic else [])+['image_flow','geometry','estimator'])
                    self.assertEqual([c.unit for c in p.channels],['px/s','px/s','1/s'])
    def test_missing_duplicate_extra_and_inactive_stages_fail(self):
        rows=configurations()
        for bad in (rows[:-1],rows+rows[:1],configurations(automatic=True)):
            with self.subTest(count=len(bad)),self.assertRaises(ValueError):
                resolve_pipeline('water_flow','manual',bad,builtin_registry(),max_bytes=BUDGET)
        for family,mode in (('unknown','manual'),('water_flow','guess'),('water_flow','automatic')):
            with self.subTest(family=family,mode=mode),self.assertRaises(ValueError):
                resolve_pipeline(family,mode,rows,builtin_registry(),max_bytes=BUDGET)
    def test_cost_configuration_and_family_mismatch_rejected(self):
        resolved(cost=True)
        rows=list(configurations(cost=True));rows[0]=configurations()[0]
        with self.assertRaises(ValueError):resolve_pipeline('water_flow','manual',tuple(rows),builtin_registry(),max_bytes=BUDGET)
        with self.assertRaises(ValueError):resolve_pipeline('fin_flow','manual',configurations(),builtin_registry(),max_bytes=BUDGET)
    def test_water_rejects_fin_parameters_and_fin_requires_them(self):
        for family in ('water_flow','fin_flow'):
            rows=list(configurations(family));body=json.loads(rows[-1].settings_json)
            if family=='water_flow':body['fin_region']=dict(schema_version=1,offset_degrees=0.,span_degrees=90.)
            else:body.pop('fin_region')
            rows[-1]=rows[-1].model_copy(update={'settings_json':json.dumps(body)})
            with self.assertRaises(ValueError):resolve_pipeline(family,'manual',tuple(rows),builtin_registry(),max_bytes=BUDGET)
    def test_ports_cannot_be_relabelled_as_compatible(self):
        registry=StageRegistry()
        for s,m in resolved().stages:
            registry.register(replace(s,output_contract='tracking.wrong.v1') if s.stage_id=='image_flow' else s)
        with self.assertRaises(ValueError):resolve_pipeline('water_flow','manual',configurations(),registry,max_bytes=BUDGET)
    def test_local_quality_bounds_and_no_implicit_defaults(self):
        parse(LocalMedianSettings,QUALITY)
        for change in ({'radius_cells':0},{'radius_cells':True},{'minimum_neighbors':9},
                       {'noise_floor_px':0.},{'maximum_native_cost':256},{'maximum_native_cost':True},
                       {'maximum_normalized_residual':float('nan')}):
            with self.subTest(change=change),self.assertRaises(ValueError):parse(LocalMedianSettings,QUALITY|change)
        for field in QUALITY:
            with self.subTest(missing=field),self.assertRaises(ValueError):parse(LocalMedianSettings,{k:v for k,v in QUALITY.items() if k!=field})
    def test_prepared_channel_units_and_binding_versions_checked(self):
        p=resolved()
        prepared=PreparedMethods(schema_version=1,prepared_generation='g',configuration_revision=1,
                  pipeline_id='water_flow',implementation_version='1',stages=p.bindings(),
                  source_allocation_id='source',source_layout_digest='0'*64,method_assets=(),
                  onnxruntime_version=None,cuda_device_identity='gpu',nvof_api_version='api',driver_version='driver',
                  cpu_graph_node_names=(),channels=p.channels,geometry_binding_id='geom',estimator_binding_id='est')
        validate_prepared(prepared,p)
        for change in ({'implementation_version':'2'},{'geometry_binding_id':None},
                       {'channels':p.channels[:-1]},{'stages':p.bindings()[:-1]}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate_prepared(prepared.model_copy(update=change),p)
    def test_valid_evidence_and_threshold_equality(self):
        for family in ('water_flow','fin_flow'):
            x=evidence(family)
            for s in x['sections']:s['accepted_area_px2']=8. # T44: 8/10 intended area == 0.8.
            validate_proxy_evidence(parse(FlowProxyEvidence,x),resolved(family))
    def test_malformed_evidence_and_unusable_invalid_controls_rejected(self):
        x=evidence()
        for change in ({'validity':'invalid','reason':'flow_coverage','filter_disposition':'cleared'},
                       {'counts':x['counts']|{'selected':3}},
                       {'raw':x['raw']|{'turn_drive':3.}},
                       {'raw':x['raw']|{'turn_drive':-3.}}, # Undivided moment is not the turn rate.
                       {'centred_second_moment_px2':0.},{'centred_second_moment_px2':-1.5},
                       {'centred_second_moment_px2':None},
                       {'filtered_average':x['raw']|{'forward_drive':0.}},
                       {'sections':[x['sections'][0],x['sections'][0]]}):
            with self.subTest(change=change),self.assertRaises(ValueError):parse(FlowProxyEvidence,x|change)
    def test_valid_evidence_requires_each_section_not_global_coverage(self):
        x=evidence();x['sections'][0]['accepted_area_px2']=0.
        with self.assertRaises(ValueError):validate_proxy_evidence(parse(FlowProxyEvidence,x),resolved())
        x=evidence();x['sections'][0]['visible_area_px2']=7.;x['sections'][0]['accepted_area_px2']=7.
        with self.assertRaises(ValueError):validate_proxy_evidence(parse(FlowProxyEvidence,x),resolved())
    def test_clipping_counts_as_missing_without_separate_visibility_gate(self):
        # T26/T44: accepted / intended (pre-clip) area is the only per-section gate.
        x=evidence();x['sections'][0].update(visible_area_px2=8.,accepted_area_px2=8.)
        validate_proxy_evidence(parse(FlowProxyEvidence,x),resolved())
        x['sections'][0].update(visible_area_px2=8.,accepted_area_px2=7.9)
        with self.assertRaises(ValueError):validate_proxy_evidence(parse(FlowProxyEvidence,x),resolved())
    def test_fin_excluded_section_is_allowed_but_not_relabelled_as_water(self):
        x=evidence('fin_flow');x['sections'][0].update(intended_area_px2=0.,visible_area_px2=0.,accepted_area_px2=0.)
        validate_proxy_evidence(parse(FlowProxyEvidence,x),resolved('fin_flow'))
        with self.assertRaises(ValueError):validate_proxy_evidence(parse(FlowProxyEvidence,x),resolved())
        x['pipeline_id']='water_flow'
        with self.assertRaises(ValueError):validate_proxy_evidence(parse(FlowProxyEvidence,x),resolved())
    def test_invalid_support_retained_and_missing_geometry_not_fabricated(self):
        x=evidence();x.update(validity='invalid',reason='flow_coverage',filter_disposition='cleared')
        for key in ('centroid_body_px','mean_velocity_body_px_per_s','centred_moment_px2_per_s','centred_second_moment_px2','raw','filtered_average','filter_end'):x[key]=None
        x['sections'][0]['accepted_area_px2']=0.
        validate_proxy_evidence(parse(FlowProxyEvidence,x),resolved())
        x.update(sections=[],counts=None,reason='pose_missing')
        validate_proxy_evidence(parse(FlowProxyEvidence,x),resolved())
    def test_evidence_requires_registered_schema_and_cost_policy(self):
        p=resolved();s,m=p.stages[-1];registry=builtin_registry();x=evidence()
        registry.validate_evidence(s,'tracking.flow-proxy-evidence.v1',json.dumps(x),max_bytes=BUDGET)
        with self.assertRaises(ValueError):registry.validate_evidence(s,'tracking.flow-proxy-evidence.v0',json.dumps(x),max_bytes=BUDGET)
        x['counts'].update(selected=3,cost_rejected=1)
        with self.assertRaises(ValueError):validate_proxy_evidence(parse(FlowProxyEvidence,x),p)

if __name__=='__main__':unittest.main()
