"""Same validated synthetic protocol as the review; offscreen timing only."""
import json
from time import perf_counter
from PyQt6.QtWidgets import QApplication
from cephvr.gui.preview_timeline import StimulusTimeline
from cephvr.gui.protocol_document import review_program
from cephvr.visual_stimulus.config.models.program_model import Group, Program, Instance
app = QApplication([])
base = review_program()
flow = base.sequence[1]
settings = tuple(flow.settings[0].model_copy(update={"instance_id": f"layer{i}", "space": flow.settings[0].space.model_copy(update={"surfaces": ("left", "front", "right", "bottom")})}) for i in range(4))
flow = flow.model_copy(update={"settings": settings})
scene = base.scenes[1].model_copy(update={"layer_instance_ids": tuple(s.instance_id for s in settings)})
group = Group(kind="group", group_id="bench", repetitions=666, order="as_listed", order_unit="child_blocks", conditions=None, body=(base.sequence[0], flow, base.sequence[2]))
program = Program.model_validate(base.model_copy(update={"instances": tuple(Instance(instance_id=s.instance_id, family="texture") for s in settings), "scenes": (base.scenes[0], scene), "sequence": (group,)}).model_dump())
results = []
for _ in range(3):
    widget = StimulusTimeline()
    widget.timer.stop()
    start = perf_counter()
    widget.set_program(program, "", "4 layers x 4 surfaces")
    hidden_s = perf_counter() - start
    names = widget.projector_names()
    hidden_widgets = len(widget.dials) + len(widget.maps) + len(widget.shared_dials)
    start = perf_counter()
    widget.set_advanced(True)
    first_open_s = perf_counter() - start
    widget.set_advanced(False)
    start = perf_counter()
    widget.set_advanced(True)
    reopen_s = perf_counter() - start
    results.append({"epochs": len(widget.epochs), "panels": len(widget.all_panels), "hidden_widgets": hidden_widgets, "projectors": names, "hidden_set_program_s": hidden_s, "first_advanced_open_s": first_open_s, "advanced_reopen_s": reopen_s})
    widget.close()
    widget.deleteLater()
    app.processEvents()
print(json.dumps(results, indent=2))
