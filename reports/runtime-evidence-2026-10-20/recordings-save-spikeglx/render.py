import json
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import review_view, Phase
from cephvr.gui.window import DashboardWindow
from cephvr.gui.review import ReviewControls
OUT=Path(__file__).parent
app=QApplication([]);apply_theme(app)
window=DashboardWindow(sample=True);ReviewControls(window)
window.resize(1920,1000);window.apply_view(review_view(Phase.CONFIGURATION))
window.show();app.processEvents()
for style in ("standard","retro_console"):
 window.appearance.select(style)
 app.processEvents()
 card=window.recordings
 assert card.isAncestorOf(card.spikeglx) and card.spikeglx.isVisible()
 assert card.spikeglx_label.isVisible()
 assert card.rect().contains(card.spikeglx_label.mapTo(card,card.spikeglx_label.rect().bottomRight()))
 assert card.grab().save(str(OUT/(style+".png")))
(OUT/"layout.json").write_text(json.dumps({"label":card.spikeglx_label.text(),"accessible_name":card.spikeglx.accessibleName(),"same_existing_pairing_widget":card.spikeglx is window.devices.spikeglx.pairing,"parent_card":"Recordings","native_rig_operations":False},indent=2))
window.close()
