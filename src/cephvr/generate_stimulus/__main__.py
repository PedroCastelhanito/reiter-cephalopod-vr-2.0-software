"""Launch the standalone offline editor, without experiment services."""

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="CephVR2 stimulus authoring")
    parser.add_argument("--asset-root", type=Path, default=Path.cwd())
    parser.add_argument("--geometry", type=Path)
    parser.add_argument("--geometry-json")
    args = parser.parse_args()
    from PyQt6.QtCore import QSettings
    from PyQt6.QtGui import QSurfaceFormat
    from PyQt6.QtWidgets import QApplication

    from cephvr.gui.splash import saved_style
    from cephvr.gui.theme import (
        RETRO_PALETTES,
        apply_theme,
        load_terminal_font,
        phosphor_stylesheet,
        retro_stylesheet,
    )
    from cephvr.visual_stimulus.config.models.display_profile import Geometry

    from .textures import load_geometry
    from .window import AuthoringWindow

    format = QSurfaceFormat()
    format.setVersion(3, 3)
    format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    format.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(format)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("CephVR stimulus authoring")
    apply_theme(app)
    load_terminal_font()
    geometry = (
        Geometry.model_validate_json(args.geometry_json)
        if args.geometry_json
        else load_geometry(args.geometry)
        if args.geometry
        else None
    )
    window = AuthoringWindow(args.asset_root, geometry)
    name = saved_style(QSettings("CephVR", "Frontend"))
    if name in RETRO_PALETTES:
        colors = RETRO_PALETTES[name][0]
        window.setProperty("retroConsole", True)
        window.setProperty("retroPalette", name)
        window.setStyleSheet(
            retro_stylesheet(colors)
            + (phosphor_stylesheet(colors) if name == "amber_phosphor" else "")
        )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
