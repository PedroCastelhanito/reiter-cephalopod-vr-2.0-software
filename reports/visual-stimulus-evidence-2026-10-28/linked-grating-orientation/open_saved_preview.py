"""Open the actual planning dialog from saved owner inputs, without device access."""

import json
import faulthandler
import sys
from pathlib import Path

faulthandler.dump_traceback_later(10)

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from cephvr.gui.projector_geometry import RigDimensions
from cephvr.gui.trial_preview import TrialPreview
from cephvr.gui.theme import apply_theme, load_terminal_font
from cephvr.gui.trial_preview_surfaces import PreviewGeometry
from cephvr.visual_stimulus.config.models.program_model import Program

PROTOCOL = Path("C:/Users/ReiterU_PC/Desktop/Alsu/protocols/gratings_protocol.json")
CALIBRATION = Path("C:/Users/ReiterU_PC/Desktop/Pedro/configs/projectors_config.json")


def main() -> None:
    payload = json.loads(PROTOCOL.read_text())
    trial = payload["trials"][payload["selected_trial"]]
    orientation = "180" if "--left-motion-example" in sys.argv else None
    if "--orientation" in sys.argv:
        orientation = sys.argv[sys.argv.index("--orientation") + 1]
    if orientation is not None:
        from cephvr.gui.rig_parameter_edits import patch_setting

        epoch = trial["program"]["sequence"][0]["body"][0]
        epoch["repetition_rules"] = []
        source = next(s for s in epoch["settings"] if s.get("linked_to") is None)
        patch_setting(source, {"Orientation": orientation, "Speed": "20"})
    program = Program.model_validate_json(json.dumps(trial["program"]))
    values = json.loads(CALIBRATION.read_text())["values"]
    rig = RigDimensions(
        *(values[f"rig.{key}"] for key in ("width", "depth", "height")),
        tuple(values[f"rig.subject_{axis}"] for axis in "xyz"),
    )
    faces = ("Front", "Left", "Right", "Bottom")
    drafts = {
        face: {
            key.rsplit(".", 1)[-1]: str(value)
            for key, value in values.items()
            if key.startswith(f"screens.{face}.")
        }
        for face in faces
    }
    resolutions = {
        face: (
            int(values[f"screens.{face}.reference_width_px"]),
            int(values[f"screens.{face}.reference_height_px"]),
        )
        for face in faces
    }
    geometry = PreviewGeometry.from_drafts(rig, drafts, resolutions)
    app = QApplication([])
    load_terminal_font()
    apply_theme(app)
    app.setFont(QFont("IBM Plex Mono"))
    parent = QWidget()
    preview = TrialPreview(program, faces, payload["asset_root"], geometry, parent)
    preview.setParent(None, Qt.WindowType.Window)
    preview.setWindowTitle("Trial preview — saved Gratings (read only)")
    if "--azimuth" in sys.argv:
        preview.rig_view.azimuth = float(sys.argv[sys.argv.index("--azimuth") + 1])
    if "--side-orientation-candidate" in sys.argv:
        from dataclasses import replace

        layers = tuple(
            replace(layer, values=dict(layer.values, rotation=-layer.values["rotation"]))
            if layer.setting.space.kind == "physical_surface"
            and layer.setting.space.mappings[0].surface_id in ("left", "right")
            else layer
            for layer in preview.plan.seek(preview.time_ns)
        )
        for canvas in preview.canvases.values():
            canvas.present(layers, 0, (0, 0, 0))
        preview.rig_view.invalidate_frames()
    preview.show()
    faulthandler.cancel_dump_traceback_later()
    if "--snapshot" in sys.argv:
        app.processEvents()
        if "--animation" in sys.argv:
            from io import BytesIO
            from PIL import Image
            from PyQt6.QtCore import QBuffer, QIODevice

            frames = []
            for index in range(25):
                preview.time_ns = index * 10_000_000
                preview.update_canvases()
                app.processEvents()
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                assert preview.rig_view.grab().save(buffer, "PNG")
                frames.append(Image.open(BytesIO(bytes(buffer.data()))).convert("RGB"))
            assert frames[0].tobytes() != frames[12].tobytes()
            frames[0].save(Path(__file__).with_name("projected-sheet-motion.gif"),
                           save_all=True, append_images=frames[1:], duration=40, loop=0)
            preview.time_ns = 0
            preview.update_canvases()
            app.processEvents()
        name = "candidate-side-orientation.png" if "--side-orientation-candidate" in sys.argv else "straight-preview.png"
        if "--left-motion-example" in sys.argv:
            name = "left-motion-example.png"
        if "--orientation" in sys.argv:
            name = f"orientation-{float(orientation):g}.png"
        if "--azimuth" in sys.argv:
            name = f"corrected-sides-{float(orientation):g}-rotated.png"
        preview.rig_view.grab().save(str(Path(__file__).with_name(name)))
        preview.close()
        app.processEvents()
        return
    app.exec()


if __name__ == "__main__":
    main()
