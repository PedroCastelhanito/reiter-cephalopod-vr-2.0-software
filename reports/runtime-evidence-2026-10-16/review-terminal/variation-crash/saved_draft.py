"""Variation open/hover exercise with callback errors captured before Qt can abort."""
import sys, traceback, json, os
from pathlib import Path
from PyQt6.QtCore import QEvent, QSettings, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from cephvr.gui.review import ReviewDashboardWindow, ReviewControls
from cephvr.gui.review_draft import load_review_draft, draft_path
from cephvr.gui.protocol_document import review_program
from cephvr.gui.protocol_batches import grouped_program
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import Phase, review_view
if os.environ.get("REPRO_LEGACY_HOVER") == "1":
 from PyQt6.QtGui import QCursor
 from cephvr.gui.variation_table import VariationTable
 from cephvr.gui.batch_variation import BatchVariationRow
 def legacy_filter(self, watched, event):
  if event is not None and event.type() == QEvent.Type.Enter:
   for rule in self.rules:
    rule.remove.setVisible(watched in (rule.target,rule.layer,rule.parameter,rule.method,rule,rule.remove))
  return super(VariationTable,self).eventFilter(watched,event)
 def legacy_leave(self,event):
  if not self.rect().contains(self.mapFromGlobal(QCursor.pos())):
   for rule in self.rules: rule.remove.hide()
  super(VariationTable,self).leaveEvent(event)
 def legacy_enter(self,event):
  self.remove.show()
  super(BatchVariationRow,self).enterEvent(event)
 VariationTable.eventFilter=legacy_filter
 VariationTable.leaveEvent=legacy_leave
 BatchVariationRow.enterEvent=legacy_enter

errors=[]
def error(kind, value, tb):
 errors.append(''.join(traceback.format_exception(kind,value,tb)))
sys.excepthook=error
app=QApplication([]);apply_theme(app)
w=ReviewDashboardWindow(sample=True,settings=QSettings('/tmp/cephvr-variation-crash.ini',QSettings.Format.IniFormat))
w.appearance.select(os.environ.get('REPRO_STYLE','retro_console'),persist=False)
w.apply_view(review_view(Phase.CONFIGURATION))
w.resize(1175,1000);w.page_buttons[1].click();w.show()
controls=ReviewControls(w,simulate_projectors=True)
assert load_review_draft(w,draft_path())
e=w.protocol.editor;e.enter_group()
form=e.subgroup
repeat=0
widths=(1440,1175,720)
def prepare():
 global repeat
 if repeat == 3 or errors:
  app.quit()
  return
 w.resize(widths[repeat%3],960)
 w.protocol.config_scroll.ensureWidgetVisible(form.add_rule)
 w.raise_();w.activateWindow()
 QTimer.singleShot(250,hover)
def hover():
 QTest.mouseMove(form.add_rule,form.add_rule.rect().center())
 QTimer.singleShot(250,click)
def click():
 QTest.mouseClick(form.add_rule,Qt.MouseButton.LeftButton)
 QTimer.singleShot(500,clean)
def clean():
 global repeat
 for rule in tuple(form.rows): form.remove_variation(rule)
 repeat+=1
 QTimer.singleShot(150,prepare)
QTimer.singleShot(500,prepare)
app.exec()
print(json.dumps({'callback_errors':errors,'iterations':repeat,'style':os.environ.get('REPRO_STYLE','retro_console')},indent=2))
w.appearance.select('standard',persist=False);w.hide();w.deleteLater()
app.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
assert not errors
