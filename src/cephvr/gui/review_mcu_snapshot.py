"""Review input definitions stay in a file extension rejected by runtime readers."""

from typing import Any

from cephvr.gui.configuration_files import JSON
from cephvr.gui.microcontroller_snapshot import MicrocontrollerSnapshot
from cephvr.gui.review_mcu_inputs import validate_inputs
from cephvr.gui.review_mcu_outputs import ReviewMicrocontrollerSignals, validate_outputs


class ReviewMicrocontrollerSnapshot(MicrocontrollerSnapshot):
    def capture(self) -> JSON:
        result = super().capture()
        assert self.panel.review_inputs is not None
        result["review_inputs"] = self.panel.review_inputs.snapshot()
        assert isinstance(self.panel.signals, ReviewMicrocontrollerSignals)
        result["review_outputs"] = self.panel.signals.snapshot()
        return result

    def validate(
        self, value: Any, *, legacy_roles: dict[str, str] | None = None
    ) -> JSON:
        inputs = []
        outputs: JSON = dict(selected=[], templates=[])
        if isinstance(value, dict) and "review_outputs" in value:
            outputs = validate_outputs(value["review_outputs"])
            value = {
                key: item for key, item in value.items() if key != "review_outputs"
            }
        if isinstance(value, dict) and "review_inputs" in value:
            inputs = validate_inputs(value["review_inputs"])
            value = {key: item for key, item in value.items() if key != "review_inputs"}
        result = super().validate(value, legacy_roles=legacy_roles)
        result["review_inputs"] = inputs
        occupied = {key for key, pin in result["camera_pins"].items() if pin}
        if result["trial_state"]["pin"]:
            occupied.add("trial-state")
        result["review_outputs"] = validate_outputs(outputs, occupied)
        return result

    def restore(self, data: JSON) -> None:
        data = self.validate(data)
        super().restore(data)
        assert self.panel.review_inputs is not None
        self.panel.review_inputs.restore(data["review_inputs"])
        assert isinstance(self.panel.signals, ReviewMicrocontrollerSignals)
        self.panel.signals.restore(data["review_outputs"])
