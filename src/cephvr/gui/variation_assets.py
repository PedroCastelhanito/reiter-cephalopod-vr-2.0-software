"""Folder picker and retained media candidate snapshot for an Asset rule."""

from hashlib import sha256
from pathlib import Path

from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QHideEvent

from cephvr.gui.paths import PathField
from cephvr.gui.stimulus_files import resolve_stimulus_file
from cephvr.visual_stimulus.config.models.program_model import Asset, Program


class VariationAssets(PathField):
    def __init__(self) -> None:
        super().__init__(
            title="Select variation media folder",
            placeholder="Select media subset folder",
        )
        self.setToolTip(
            "Choose a folder within Protocol Assets. Use compatible files directly "
            "in this folder; subfolders are excluded. Files are not copied."
        )
        self.asset_ids: tuple[str, ...] = ()
        self.grating_periods_mm: tuple[float, ...] = ()
        self.saved_folder = ""
        self.loaded: tuple[Asset, ...] = ()
        self.loaded_key: tuple[str, str, tuple[str, ...]] | None = None

    def restore(
        self,
        folder: str,
        asset_ids: tuple[str, ...],
        grating_periods_mm: tuple[float, ...] = (),
    ) -> None:
        self.editor.setText(folder)
        self.saved_folder, self.asset_ids = folder, asset_ids
        self.grating_periods_mm = grating_periods_mm
        self.loaded, self.loaded_key = (), None

    def load(
        self, program: Program, root: str, kinds: tuple[str, ...]
    ) -> tuple[Asset, ...]:
        if not kinds or any(
            kind not in ("image", "texture", "video", "grating") for kind in kinds
        ):
            raise ValueError("Asset variations require compatible media layers")
        if "grating" in kinds and kinds != ("grating",):
            raise ValueError("Choose only Grating layers for this Asset variation")
        folder = self.editor.text().strip()
        if not folder:
            raise ValueError("Choose a folder for the Asset variation")
        key = (root, folder, kinds)
        if self.loaded_key == key:
            return self.loaded
        by_id = {asset.asset_id: asset for asset in program.assets}
        if folder == self.saved_folder and self.asset_ids and self.loaded_key is None:
            if any(identity not in by_id for identity in self.asset_ids):
                raise ValueError("A saved Asset variation candidate is missing")
            candidates = tuple(by_id[identity] for identity in self.asset_ids)
        else:
            if not root or not Path(root).is_dir():
                raise ValueError("Choose the Assets folder first")
            directory = Path(folder).expanduser()
            if not directory.is_absolute():
                directory = Path(root) / directory
            if not directory.is_dir():
                raise ValueError("Choose an existing variation media folder")
            extensions = {
                "image": {".png", ".tif", ".tiff", ".jpg", ".jpeg"},
                "texture": {".png", ".tif", ".tiff", ".jpg", ".jpeg", ".json"},
                "grating": {".json"},
                "video": {".mp4", ".mkv"},
            }
            allowed = set.intersection(*(extensions[kind] for kind in kinds))
            paths = sorted(
                (
                    p
                    for p in directory.iterdir()
                    if p.is_file() and p.suffix.lower() in allowed
                ),
                key=lambda p: (p.name.casefold(), p.name),
            )
            if not 1 <= len(paths) <= 2000:
                raise ValueError(
                    "The folder must contain 1–2000 compatible media files"
                )
            selected = [
                resolve_stimulus_file(
                    root,
                    str(path),
                    texture=kinds in (("texture",), ("grating",)),
                    grating=kinds == ("grating",),
                )
                for path in paths
            ]
            candidates = tuple(
                Asset.model_validate(
                    dict(
                        asset_id="variation_"
                        + sha256(f"{file.profile}:{file.path}".encode()).hexdigest()[
                            :24
                        ],
                        logical_path=file.path,
                        profile=file.profile,
                        color_override=None,
                    )
                )
                for file in selected
            )
            self.grating_periods_mm = (
                tuple(
                    float(file.tile_width_mm)
                    for file in selected
                    if file.tile_width_mm is not None
                )
                if kinds == ("grating",)
                else ()
            )
        self.loaded, self.loaded_key = candidates, key
        self.saved_folder = folder
        self.asset_ids = tuple(asset.asset_id for asset in candidates)
        return candidates

    def close_dialog(self) -> None:
        if self.dialog is not None:
            self.dialog.reject()

    def changeEvent(self, event: QEvent | None) -> None:
        super().changeEvent(event)
        if (
            event is not None
            and event.type() == QEvent.Type.EnabledChange
            and not self.isEnabled()
        ):
            self.close_dialog()

    def hideEvent(self, event: QHideEvent | None) -> None:
        self.close_dialog()
        super().hideEvent(event)
