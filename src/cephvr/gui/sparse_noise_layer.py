"""Inline sparse-noise parameters for one epoch layer; patterns are generated in playback."""

import secrets
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from cephvr.gui.components import button, label
from cephvr.gui.notices import readable_error
from cephvr.gui.stimulus_form import ValueEditor, title
from cephvr.visual_stimulus.config.models.program_model import Settings
from cephvr.visual_stimulus.config.models.sparse_noise import SparseNoisePatternRecipe

# Form keys in display order; captions come from stimulus_form.TITLES (shared wording).
CAPTIONS = {
    key: title(key)
    for key in (
        "square_size_mm",
        "min_active_cell_distance_mm",
        "active_probability",
        "background_linear",
        "seed",
        "pattern_count",
        "pattern_duration",
    )
}
APPEARANCE_KEYS = tuple(CAPTIONS)[:5]


class SparseNoiseLayer(QWidget):
    """Edits a ``sparse_noise`` layer's settings; the epoch editor commits via ``read``."""

    edited = pyqtSignal()

    def __init__(self, setting: Settings) -> None:
        super().__init__()
        assert setting.kind == "sparse_noise"
        appearance = setting.appearance.model_dump(mode="json")
        count = setting.pattern_count
        duration = setting.pattern_duration
        schema = SparseNoisePatternRecipe.model_json_schema()
        values = dict(
            appearance,
            pattern_count=count,
            pattern_duration=duration.model_dump(mode="json"),
        )
        keys = tuple(CAPTIONS)
        self.form = ValueEditor(
            {
                "type": "object",
                "properties": {key: schema["properties"][key] for key in keys},
            },
            {key: values[key] for key in keys},
            schema.get("$defs", {}),
        )
        self.form.changed.connect(self.mark_changed)
        self.new_seed = button("New seed")
        self.new_seed.clicked.connect(self.randomize_seed)
        self.error = label("", wrap=True)
        self.summary = label(
            "Patterns are generated during playback; the final pattern is held "
            "until the epoch ends.",
            wrap=True,
        )
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self.form)
        body.addWidget(self.new_seed)
        body.addWidget(self.summary)
        body.addWidget(self.error)

    def randomize_seed(self) -> None:
        seed = self.form.children_by_key["seed"].control
        assert isinstance(seed, QLineEdit)
        seed.setText(str(secrets.randbits(64)))
        self.mark_changed()

    def read(self) -> dict[str, Any]:
        """Setting fields for the layer. Raises ValueError."""
        values = self.form.read()
        SparseNoisePatternRecipe.model_validate(
            dict(
                values,
                format_version=2,
                kind="sparse_noise",
                surfaces=("front",),  # Placeholder: the real surface is compile-time.
            )
        )
        return dict(
            appearance=dict(
                format_version=2,
                kind="sparse_noise",
                **{key: values[key] for key in APPEARANCE_KEYS},
            ),
            pattern_count=values["pattern_count"],
            pattern_duration=values["pattern_duration"],
        )

    def mark_changed(self) -> None:
        try:
            self.read()
            self.error.setText("")
        except ValueError as error:
            self.error.setText(readable_error(error))
        self.edited.emit()
