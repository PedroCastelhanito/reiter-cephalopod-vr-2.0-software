from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QEvent
from cephvr.gui.window import DashboardWindow
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
from cephvr.gui.protocol_document import review_program
from cephvr.gui.protocol_groups import make_group
app=QApplication([]);apply_theme(app)
w=DashboardWindow(sample=True);ReviewControls(w)
w.page_buttons[1].click()
e=w.protocol.editor
p,_=make_group(review_program(),(),0,1,300,False)
e.set_program(p)
e.timeline.choose(0,Qt.KeyboardModifier.NoModifier)
w.show()
for width in (1280,720):
 w.resize(width,1100)
 for _ in range(6):app.processEvents()
 w.grab().save(str(Path(__file__).parent/f'group-{width}.png'))
print('Captured wide/narrow grouped editor.')
w.close()
w.deleteLater()
app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
