from pathlib import Path
from PyQt6.QtWidgets import QApplication
from cephvr.gui.window import DashboardWindow
from cephvr.gui.review import ReviewControls
from cephvr.gui.view import review_view,Phase
from cephvr.gui.theme import apply_theme
out=Path(__file__).parent
app=QApplication([]);apply_theme(app)
window=DashboardWindow(sample=True);ReviewControls(window)
window.resize(1920,1000);window.apply_view(review_view(Phase.CONFIGURATION));window.show();app.processEvents()
for style in ("standard","retro_console"):
 window.appearance.select(style);app.processEvents()
 assert window.dashboard.subject_id.text()=="0007"
 assert window.dashboard.subject_id.hasAcceptableInput()
 assert window.dashboard.species.count()==3 and not window.dashboard.species.isEditable()
 assert window.dashboard.subject_card.grab().save(str(out/(style+".png")))
window.dashboard.species.showPopup();app.processEvents()
assert window.dashboard.species.view().window().grab().save(str(out/"species-options.png"))
window.dashboard.species.hidePopup();window.close()
