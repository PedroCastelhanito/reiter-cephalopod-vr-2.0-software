"""Selection-bound reference composer shared by subgroup editing."""

from cephvr.gui.epoch_composer import EpochComposer
from cephvr.gui.formatting import clock_duration
from cephvr.gui.program_editing import node_at
from cephvr.gui.projector_layers import detach_layer
from cephvr.gui.protocol_document import blank_program
from cephvr.gui.stimulus_scope import surfaces
from cephvr.visual_stimulus.config.models.program_model import Epoch, Fixed, Program


class SelectionComposer(EpochComposer):
    variable_duration = False

    def bind_epoch(
        self, program: Program, path: tuple[int, ...], screens: tuple[str, ...]
    ) -> None:
        epoch = node_at(program, path)
        assert isinstance(epoch, Epoch)
        fixed = isinstance(epoch.duration, Fixed)
        self.variable_duration = not fixed
        self.duration.setReadOnly(not fixed)
        self.duration.setText(
            clock_duration(epoch.duration.duration.seconds)
            if isinstance(epoch.duration, Fixed)
            else "Variable"
        )
        duration = self.duration_value()
        self.reference_duration_ns = duration.duration.ns()
        self.batch_label.setText(epoch.batch_label or "")
        # A reference is not a complete trial; keep its placeholder valid under E05.
        blank = blank_program().sequence[0]
        assert isinstance(blank, Epoch)
        placeholder = blank.duration
        self.program = program.model_copy(
            update={
                "sequence": (
                    epoch.model_copy(
                        update={
                            "duration": placeholder,
                            "repetition_settings": (),
                            "repetition_rules": (),
                        }
                    ),
                )
            }
        )
        self.pending_assets.clear()
        arena = any(setting.kind == "arena" for setting in epoch.settings)
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(int(arena))
        self.active_mode = int(arena)
        self.mode.blockSignals(False)
        for setting in epoch.settings:
            if setting.kind != "arena":
                for face in surfaces(setting.model_dump(mode="json")):
                    name = face.title()
                    if name not in self.rows:
                        self.add_row(name)
        self.set_screens(screens)
        for row in self.rows.values():
            row.parameters.duration_override = duration
        self.refresh_rows()

    def duration_value(self) -> Fixed:
        if self.variable_duration:
            return Fixed.model_validate(
                {"kind": "fixed", "duration": {"seconds": "60"}}
            )
        return super().duration_value()

    def isolate(self, face: str) -> bool:
        row = self.rows[face]
        if row.parameters.layer_index < 0:
            return True
        try:
            original = self.reference_value()
            self.program, layer = detach_layer(
                original, 0, row.parameters.layer_index, face
            )
            if self.program is not original:
                self.refresh_rows(face, layer)
            return True
        except ValueError as exc:
            self.message.setText(str(exc))
            return False

    def change_type(self, face: str, kind: str) -> None:
        if self.isEnabled() and self.isolate(face):
            super().change_type(face, kind)

    def remove_layer(self, face: str) -> None:
        if self.isEnabled() and self.isolate(face):
            super().remove_layer(face)
