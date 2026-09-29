"""Finite stimulus parameter/unit catalogue, shared by editor and pure validation.

No unit-expression parser, algebra engine, automatic conversion or runtime lookup.
The selected coordinate space and named parameter determine the receiving unit.
"""
from __future__ import annotations
from typing import Literal, get_args
from schema_common import Model

InputUnit = Literal['1','mm','deg','cycle','px','s','1/s','mm/s','deg/s','cycle/s','px/s']
ScalarUnit = Literal[
    '1','mm','deg','cycle','px','s','1/s','mm/s','deg/s','cycle/s','px/s',
    '1/s^2','mm/s^2','deg/s^2','cycle/s^2','px/s^2',
    'cycle/mm','cycle/deg','cycle/(mm*s)','cycle/(deg*s)'
]
RATE_UNIT = {
    '1':'1/s','mm':'mm/s','deg':'deg/s','cycle':'cycle/s','px':'px/s','s':'1',
    '1/s':'1/s^2','mm/s':'mm/s^2','deg/s':'deg/s^2',
    'cycle/s':'cycle/s^2','px/s':'px/s^2',
    'cycle/mm':'cycle/(mm*s)','cycle/deg':'cycle/(deg*s)',
}
# Documented literal domains (stimulus-schema.md): (minimum, minimum inclusive, maximum).
PARAMETER_RANGES = {
    'width':(0.0,False,None),'height':(0.0,False,None),
    'opacity':(0.0,True,1.0),'contrast':(0.0,True,1.0),
    'frequency':(0.0,True,None),'frequency_x':(0.0,True,None),'frequency_y':(0.0,True,None),
    'period_x':(0.0,False,None),'period_y':(0.0,False,None),
}
def check_range(name: str, value: float, path: str) -> None:
    low,inclusive,high=PARAMETER_RANGES[name]
    if (value<low if inclusive else value<=low) or (high is not None and value>high):
        raise ValueError(f'{path}: value {value!r} outside the declared {name} range')
STATE_UNITS = ('mm','deg','cycle')
# T36 tracking body frame: sideways/turn animal-left-positive; never bound to world x/y directly.
BODY_FRAME = 'anatomical_body'
APPEARANCE_UNITS = ('1','mm','deg','cycle/mm','cycle/deg')

class GainUnit(Model):
    """A finite source→target scaling descriptor for condition-table gain columns.

    A gain coefficient is not an independently editable unit on every function.
    The tagged descriptor avoids arbitrary expression strings such as mm/(px*s).
    """
    kind: Literal['feedback_gain']
    input_unit: InputUnit
    output_unit: ScalarUnit
    coefficient: Literal['value','slope_per_s']

ConditionUnit = ScalarUnit | GainUnit
DIRECT_GAIN_UNITS = {
    (source,target):GainUnit(kind='feedback_gain',input_unit=source,
                            output_unit=target,coefficient='value')
    for source in get_args(InputUnit)
    for target in set(STATE_UNITS+APPEARANCE_UNITS)
}
MOVEMENT_GAIN_UNITS = {
    (kind,source,target):GainUnit(kind='feedback_gain',input_unit=source,
                                output_unit=target if kind=='displacement' else RATE_UNIT[target],
                                coefficient='value')
    for kind,sources in (
        ('displacement',('1','mm','deg','cycle','px')),
        ('interval_average_rate',('1/s','mm/s','deg/s','cycle/s','px/s')))
    for source in sources for target in STATE_UNITS
}

def rate_unit(unit: ConditionUnit) -> ConditionUnit:
    if isinstance(unit,GainUnit):
        return unit.model_copy(update={'coefficient':'slope_per_s'})
    try:return RATE_UNIT[unit]
    except KeyError:raise ValueError(f'unsupported rate unit: {unit}') from None

def parameter_units(block) -> dict[str, str]:
    """Finite target catalogue; unavailable family/pattern targets are absent."""
    if block.kind=='arena':return {'x':'mm','y':'mm','yaw':'deg'}
    length='mm' if block.space.kind=='physical_surface' else 'deg'
    result={'x':length,'y':length,'rotation':'deg',
            'width':length,'height':length,'opacity':'1'}
    if block.kind=='video':result['playback']='s'
    if block.kind=='texture':
        result.update(phase_x='cycle',phase_y='cycle',contrast='1')
        frequency='cycle/mm' if length=='mm' else 'cycle/deg'
        if block.pattern.kind in ('sine_grating','square_grating'):result['frequency']=frequency
        elif block.pattern.kind=='checkerboard':result.update(frequency_x=frequency,frequency_y=frequency)
        else:result.update(period_x=length,period_y=length)
    return result

def validate_settings_units(block, scope, channels) -> None:
    """Check every Number reference against its actual receiving parameter unit.

    Range, writer/frame compatibility and full expansion remain separate compiler
    passes. Scope maps enclosing group IDs to their already validated tables.
    """
    units=parameter_units(block)
    base=block.instance_id
    def values(value):
        if getattr(value,'kind',None)!='condition':return [value]
        return [c.value for row in scope[value.group_id].rows for c in row.cells if c.column_id==value.column_id]
    def number(value,expected,path):
        if getattr(value,'kind',None)!='condition':return
        table=scope.get(value.group_id)
        column=next((c for c in table.columns if c.column_id==value.column_id),None) if table else None
        if column is None:raise ValueError(f'{base}.{path}: unknown condition column')
        if column.value_type!='number' or column.unit!=expected:
            raise ValueError(f'{base}.{path}: condition {value.group_id}.{value.column_id} requires unit {expected!r}, got {column.unit!r}')
    def function(fn,unit,path,domain=None):
        # Pure literal/condition-cell range checks on always-attained values: constants,
        # knots (their hull bounds every interpolant/hold), ramp initial values, and sine
        # frequency >= 0. Sine/ramp extrema on resolved durations stay a compiler pass.
        attained=[]
        if fn.kind=='constant':number(fn.value,unit,path+'.value');attained=values(fn.value)
        elif fn.kind=='ramp':
            number(fn.initial,unit,path+'.initial')
            number(fn.slope_per_s,rate_unit(unit),path+'.slope_per_s');attained=values(fn.initial)
        elif fn.kind=='sine':
            number(fn.mean,unit,path+'.mean');number(fn.amplitude,unit,path+'.amplitude')
            number(fn.frequency_hz,'1/s',path+'.frequency_hz');number(fn.phase_cycles,'cycle',path+'.phase_cycles')
            if any(f<0 for f in values(fn.frequency_hz)):raise ValueError(f'{base}.{path}.frequency_hz: sine frequency must be nonnegative')
        else:
            for i,knot in enumerate(fn.knots):number(knot.value,unit,f'{path}.knots[{i}].value')
            attained=[v for knot in fn.knots for v in values(knot.value)]
        if domain is not None:
            for v in attained:check_range(domain,v,f'{base}.{path}')
    def motion(value,unit,path):
        if value.kind!='hold':function(value.function,rate_unit(unit) if value.kind=='rate' else unit,path+'.function')
    if block.kind=='arena':
        for i,value in enumerate(block.initial.position_mm):number(value,'mm',f'initial.position_mm[{i}]')
        number(block.initial.yaw_deg,'deg','initial.yaw_deg')
        for name,unit in [('fixed_height_mm','mm'),('fixed_pitch_deg','deg'),('fixed_roll_deg','deg')]:number(getattr(block,name),unit,name)
        for name in ('x','y','yaw'):motion(getattr(block.motion,name),units[name],'motion.'+name)
    else:
        for name,unit in [('x',units['x']),('y',units['y']),('rotation_deg','deg')]:number(getattr(block.initial,name),unit,'initial.'+name)
        for name in ('width','height','opacity'):function(getattr(block,name),units[name],name,name)
        for name in ('x','y','rotation'):motion(getattr(block.motion,name),units[name],'motion.'+name)
        if block.kind=='texture':
            for name in ('x','y'):
                number(getattr(block,'initial_phase_'+name+'_cycles'),'cycle','initial_phase_'+name+'_cycles')
                motion(getattr(block,'phase_'+name),'cycle','phase_'+name)
            for name in ('mean_linear_rgb','modulation_linear_rgb'):
                for i,value in enumerate(getattr(block,name)):number(value,'1',f'{name}[{i}]')
            function(block.contrast,'1','contrast','contrast')
            for name in ('frequency','frequency_x','frequency_y','period_x','period_y'):
                if name in units:function(getattr(block.pattern,name),units[name],'pattern.'+name,name)
    state_targets={'x','y','yaw'} if block.kind=='arena' else {'x','y','rotation'}
    if block.kind=='texture':state_targets.update(('phase_x','phase_y'))
    if block.kind=='video':assignment_targets=state_targets|{'playback'}
    else:assignment_targets=state_targets
    for i,assignment in enumerate(block.assignments):
        if assignment.target not in assignment_targets:raise ValueError(f'{base}.assignments[{i}]: invalid family target')
        number(assignment.value,units[assignment.target],f'assignments[{i}].value')
    for i,binding in enumerate(block.feedback):
        path=f'feedback[{i}]'
        if binding.operation=='heading_relative_planar_integration':
            # feedback.md: one ordered body-frame pair of equal unit onto arena x/y (mm).
            pair=(channels[binding.forward_channel],channels[binding.sideways_channel])
            if (block.kind!='arena' or pair[0].channel_id==pair[1].channel_id or pair[0].unit!=pair[1].unit
                    or any(c.frame_id!=BODY_FRAME or c.value_kind!='interval_average_rate' for c in pair)):
                raise ValueError(f'{base}.{path}: heading-relative planar integration requires an arena and distinct {BODY_FRAME} interval_average_rate forward/sideways channels of one unit')
            gain=MOVEMENT_GAIN_UNITS.get(('interval_average_rate',pair[0].unit,'mm'))
            if gain is None:raise ValueError(f'{base}.{path}: source unit cannot supply planar increments')
            function(binding.gain,gain,path+'.gain');continue
        source=channels[binding.source_channel]
        if source.frame_id==BODY_FRAME and not (block.kind=='arena' and binding.operation=='movement_integration' and binding.target=='yaw'):
            raise ValueError(f'{base}.{path}: {BODY_FRAME} channels bind only through heading_relative_planar_integration or to arena yaw')
        if binding.target not in units or binding.target=='playback':raise ValueError(f'{base}.{path}: invalid feedback target')
        target=units[binding.target]
        if binding.operation=='direct_value':
            # feedback.md: positions, displacements and rates are not interchangeable.
            if source.value_kind!='absolute':raise ValueError(f'{base}.{path}: direct_value requires an absolute input channel')
            gain=DIRECT_GAIN_UNITS[(source.unit,target)];offset=target
        else:
            if binding.target not in state_targets:raise ValueError(f'{base}.{path}: integration requires a motion target')
            gain=MOVEMENT_GAIN_UNITS.get((source.value_kind,source.unit,target))
            if gain is None:raise ValueError(f'{base}.{path}: source kind/unit cannot supply movement increments')
            offset=RATE_UNIT[target]
        function(binding.gain,gain,path+'.gain');function(binding.offset,offset,path+'.offset')
