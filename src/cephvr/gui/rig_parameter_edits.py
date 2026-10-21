"""GUI numeric edits use rig angles; legacy source rules retain local semantics."""

from functools import partial

from cephvr.visual_stimulus.config import parameter_edits

motion_numbers = partial(parameter_edits.motion_numbers, rig_coordinates=True)
varied_fields = partial(parameter_edits.varied_fields, rig_coordinates=True)
parameter_value = partial(parameter_edits.parameter_value, rig_coordinates=True)
patch_setting = partial(parameter_edits.patch_setting, rig_coordinates=True)
