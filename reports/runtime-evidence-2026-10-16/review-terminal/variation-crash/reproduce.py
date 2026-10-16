"""Variation open/hover exercise with callback errors captured before Qt can abort."""
import sys, traceback, json
from pathlib import Path
from PyQt6.QtCore import QEvent, QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from cephvr.gui.review import ReviewDashboardWindow
from cephvr.gui.protocol_document import review_program
from cephvr.gui.protocol_batches import grouped_program
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import Phase, review_view
errors=[]
def error(kind, value, tb):
 errors.append(''.join(traceback.format_exception(kind,value,tb)))
sys.excepthook=error
app=QApplication([]);apply_theme(app)
w=ReviewDashboardWindow(sample=True,settings=QSettings('/tmp/cephvr-variation-crash.ini',QSettings.Format.IniFormat))
w.appearance.select('retro_console',persist=False)
w.apply_view(review_view(Phase.CONFIGURATION))
w.resize(1175,1000);w.page_buttons[1].click();w.show()
e=w.protocol.editor;e.set_program(grouped_program(review_program()));e.enter_group()
e.timeline.set_screens(('Front','Left','Right','Bottom'))
e.hierarchy.contents.choose(1,Qt.KeyboardModifier.NoModifier)
form=e.subgroup
for repeat in range(8):
 w.protocol.config_scroll.ensureWidgetVisible(form.add_rule)
 for _ in range(5): app.processEvents()
 QTest.mouseMove(form.add_rule,form.add_rule.rect().center())
 QTest.mouseClick(form.add_rule,Qt.MouseButton.LeftButton)
 for _ in range(5): app.processEvents()
 for rule in tuple(form.rows):
  for widget in (rule.target,rule.method,rule,rule.remove,form.add_rule):
   QTest.mouseMove(widget,widget.rect().center())
   app.processEvents()
 for rule in tuple(form.rows): form.remove_variation(rule)
 for _ in range(5): app.processEvents()
 if errors: break
print(json.dumps({'callback_errors':errors,'iterations':repeat+1},indent=2))
w.appearance.select('standard',persist=False);w.hide();w.deleteLater()
app.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
assert not errors
