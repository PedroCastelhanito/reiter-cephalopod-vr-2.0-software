from pathlib import Path
from PyQt6.QtWidgets import QApplication, QLineEdit
from PyQt6.QtGui import QFontDatabase
from cephvr.gui.theme import apply_theme
from cephvr.gui.projector_measurements import ProjectorMeasurements
from cephvr.gui.projector_geometry import FACES

app = QApplication([])
print("QA font:", QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf"))
apply_theme(app)
drafts = {face: {"throw": "1.5"} for face in FACES}
card = ProjectorMeasurements(drafts)
distances = {(face, "distance"): QLineEdit() for face in FACES}
card.changed.connect(lambda: card.refresh({face: (1280, 720) for face in FACES}, distances))
card.refresh({face: (1280, 720) for face in FACES}, distances)
for face in FACES:
    card.fields[face, "reference_x_mm"].setText("160")
    card.fields[face, "reference_y_mm"].setText("90")
card.resize(760, card.sizeHint().height())
card.show()
app.processEvents()
output = Path("reports/tracking-evidence-2026-10-08/physical-reference-gui.png")
assert card.grab().save(str(output))
print(card.size().width(), card.size().height())
