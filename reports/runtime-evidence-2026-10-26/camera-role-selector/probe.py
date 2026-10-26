from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QObject, QEvent
from cephvr.gui.window import DashboardWindow
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme
app=QApplication([]); apply_theme(app)
w=DashboardWindow(sample=True); r=ReviewControls(w)
w.appearance.select('amber_phosphor',persist=False); w.select_page(2)
w.setWindowTitle('Camera role selector verification - local fixtures'); w.resize(1442,972); w.show()
c=w.devices.cameras.role
class Observe(QObject):
 def eventFilter(self,obj,event):
  if event.type() in (QEvent.Type.Show,QEvent.Type.Hide,QEvent.Type.Resize):
   print(event.type().name,obj.geometry(),flush=True)
  return False
obs=Observe(); c.view().window().installEventFilter(obs)
QTimer.singleShot(120000,app.quit)
app.exec()
