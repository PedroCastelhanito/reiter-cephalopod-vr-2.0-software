from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings
from cephvr.gui.window import DashboardWindow
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import DashboardView, PreviewView

out = Path(__file__).parent
app = QApplication([])
apply_theme(app)
window = DashboardWindow(sample=True, settings=QSettings(str(out / 'render.ini'), QSettings.Format.IniFormat))
window.appearance.select('amber_phosphor', persist=False)
window.resize(1920, 1080)
window.show()
window.apply_view(DashboardView(sample=True, has_control=True, previews=(PreviewView('camera-1', 'Tracking', active=True), PreviewView('stimulus', 'Stimulus', active=True))))
window.select_page(1)
window.protocol.category.setCurrentText('Texture drift')
editor = window.protocol.editor
editor.timeline.screens = ('Left', 'Front', 'Right', 'Bottom')
editor.node_index = 1
editor.selected_paths = ((0, 1),)
editor.render_selection()
for _ in range(5):
    app.processEvents()
window.grab().save(str(out / 'category-protocol.png'))
window.select_page(0)
window.dashboard.set_runtime_layout(True)
window.update_preview_timeline()
workspace = window.dashboard.preview_workspace
workspace.advanced_toggle.setChecked(True)
workspace.timeline.set_playback(12, running=False)
for _ in range(5):
    app.processEvents()
window.grab().save(str(out / 'category-combined.png'))
workspace.stimulus_area.mode.setCurrentText('Per-projector')
for _ in range(5):
    app.processEvents()
window.grab().save(str(out / 'category-individual.png'))
from cephvr.gui.protocol_document import blank_program
from cephvr.gui.stimulus_presets import add_stimulus
for category, preset in [('media_presentation', 'Video'), ('navigation_3d', '3D arena')]:
    program = blank_program().model_copy(update={'category': category})
    program = add_stimulus(program, 0, preset, ('Front',), subject_height_mm=80)
    program = add_stimulus(program, 0, 'Image' if category == 'media_presentation' else 'Sine grating', ('Front',))
    workspace.stimulus_area.mode.setCurrentText('Combined')
    workspace.timeline.set_program(program, '', category)
    workspace.timeline.set_playback(3, running=False)
    for _ in range(5):
        app.processEvents()
    window.grab().save(str(out / ('category-' + category + '.png')))
window.close()
print('Rendered offscreen source UI; no native renderer or camera windows opened.')
