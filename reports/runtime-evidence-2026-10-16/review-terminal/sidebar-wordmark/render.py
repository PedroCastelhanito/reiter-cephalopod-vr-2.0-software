"""Offscreen sidebar brand composition at wide and narrow window sizes."""
from pathlib import Path
from PyQt6.QtCore import QEvent, QPoint, QRect
from PyQt6.QtWidgets import QApplication, QFrame
from cephvr.gui.appearance import ReviewAppearance
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow
app=QApplication([])
apply_theme(app)
window=DashboardWindow(sample=True, device_review=True)
appearance=ReviewAppearance(window, window.dashboard, window.page_header, None)
appearance.select('retro_console')
window.show()
root=Path(__file__).parent
sidebar=window.findChild(QFrame,'Sidebar')
assert sidebar is not None
for width in (1440,720):
 window.resize(width,940)
 for _ in range(5): app.processEvents()
 assert appearance.brand.text() == 'CEPHVR'
 assert appearance.brand.width() >= appearance.brand.sizeHint().width()
 shot=window.grab().copy(QRect(sidebar.mapTo(window,QPoint()),sidebar.size()))
 shot.save(str(root/f'sidebar-{width}.png'))
 shot.copy(0,0,shot.width(),255).save(str(root/f'brand-{width}.png'))
appearance.select("standard")
window.close()
window.deleteLater()
app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
