"""Variation open/hover exercise with callback errors captured before Qt can abort."""
import sys, traceback, json, os
from pathlib import Path
from PyQt6.QtCore import QEvent, QSettings, Qt, QTimer
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
w.appearance.select(os.environ.get('REPRO_STYLE','retro_console'),persist=False)
w.apply_view(review_view(Phase.CONFIGURATION))
w.resize(1175,1000);w.page_buttons[1].click();w.show()
e=w.protocol.editor;e.set_program(grouped_program(review_program()));e.enter_group()
e.timeline.set_screens(('Front','Left','Right','Bottom'))
e.hierarchy.contents.choose(1,Qt.KeyboardModifier.NoModifier)
form=e.subgroup
repeat=0
widths=(1440,1175,720)
def prepare():
 global repeat
 if repeat == 9 or errors:
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
