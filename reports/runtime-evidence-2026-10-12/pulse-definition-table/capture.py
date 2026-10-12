"""Isolated shared Synchronization-page layout capture, without device commands."""
from pathlib import Path
from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QColor, QPalette
from cephvr.gui.review import ReviewControls
from cephvr.gui.theme import apply_theme, COLORS
from cephvr.gui.window import DashboardWindow

app=QApplication([])
apply_theme(app)
w=DashboardWindow(sample=True,settings=QSettings('/tmp/cephvr-overlays.ini',QSettings.Format.IniFormat))
review=ReviewControls(w,simulate_projectors=True)
w.page_buttons[2].click()
w.devices.tabs.setCurrentIndex(2)
p=w.devices.projectors
p.setup_tabs.setCurrentIndex(1)
palette=p.setup_pages.currentWidget().palette()
palette.setColor(QPalette.ColorRole.Window,QColor(COLORS.page))
p.setup_pages.currentWidget().setPalette(palette)
p.setup_pages.currentWidget().setAutoFillBackground(True)
p.timing.pulse.setChecked(True)
p.timing.target.setCurrentIndex(0)
for key,value in dict(X=100,Y=120,Width=300,Height=200).items():
 p.timing.fields[key].setText(str(value))
for key,value in dict(X=20,Y=30,Width=50,Height=40).items():
 p.timing.pulse_fields[key].setText(str(value))
p.timing.blackouts.add(dict(face='Front',x=0,y=0,width=100,height=80))
for width in (1280,720):
 w.resize(width,940)
 w.show()
 for _ in range(5): app.processEvents()
 QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
 print("containers", [(x.__class__.__name__,x.height(),x.sizeHint().height(),x.minimumSizeHint().height(),x.minimumHeight(),x.maximumHeight()) for x in (p.timing.options,p.timing,p.setup_pages.currentWidget(),p.setup_pages)])
 print(width, [(e.accessibleName(), e.size().width(), e.size().height(), e.sizeHint().height(), e.parentWidget().size().height(), e.parentWidget().sizeHint().height(), e.geometry().y(), e.parentWidget().layout().itemAt(0).widget().height(), e.parentWidget().heightForWidth(e.parentWidget().width())) for e in (*p.timing.fields.values(), *p.timing.pulse_fields.values())])
 p.setup_pages.currentWidget().grab().save(str(Path(__file__).parent/f'controls-{width}.png'))
w.tracking.annotation.close()
w.hide()
w.deleteLater()
QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
app.processEvents()
