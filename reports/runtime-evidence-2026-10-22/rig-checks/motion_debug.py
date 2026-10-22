import os,sys
sys.path.insert(0,os.getcwd())
os.environ['QT_QPA_PLATFORM']='offscreen'
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow
from cephvr.gui.review import ReviewControls
from cephvr.gui.protocol_document import blank_program
from tests.gui.test_dashboard import open_protocol_group
app=QApplication([]);apply_theme(app)
w=DashboardWindow(sample=True);ReviewControls(w);w.show();app.processEvents()
e=w.protocol.editor;e.set_program(blank_program());e.add_stimulus('Texture');e.timeline.set_screens(('Front',));open_protocol_group(e);w.page_buttons[1].click();app.processEvents()
m=e.subgroup.composer.rows['Front'].parameters.forms[0]
original=e.program
m.speed.setFocus();m.speed.selectAll();QTest.keyClicks(m.speed,'30')
print('edited',m.edited,'focus_speed',app.focusWidget() is m.speed,'visible',m.speed.isVisible(),'enabled',m.speed.isEnabled(),'dirty',e.subgroup.dirty,flush=True)
e.subgroup.composer.duration.setFocus();app.processEvents()
print('afterfocus','focus_duration',app.focusWidget() is e.subgroup.composer.duration,'timer',e.subgroup.update_timer.isActive(),'dirty',e.subgroup.dirty,'changed',e.program!=original,flush=True)
QTest.qWait(50)
print('motion',e.program.sequence[0].body[0].settings[0].motion,flush=True)
print('afterwait','dirty',e.subgroup.dirty,'changed',e.program!=original,'notice',e.subgroup.notice.text(),flush=True)
e.subgroup.queue_update();app.processEvents();QTest.qWait(10)
print('queued','changed',e.program!=original,'notice',e.subgroup.notice.text(),flush=True)
w.close();w.deleteLater();QApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
