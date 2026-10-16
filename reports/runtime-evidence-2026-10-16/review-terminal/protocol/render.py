"""Offscreen Protocol Retro fixtures; no runtime or device operations."""
from pathlib import Path
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtWidgets import QApplication
from cephvr.gui.appearance import ReviewAppearance
from cephvr.gui.protocol_batches import grouped_program
from cephvr.gui.protocol_document import review_program
from cephvr.gui.theme import apply_theme
from cephvr.gui.view import Phase, review_view
from cephvr.gui.window import DashboardWindow
app=QApplication([])
apply_theme(app)
window=DashboardWindow(sample=True,device_review=True)
window.apply_view(review_view(Phase.CONFIGURATION))
editor=window.protocol.editor
editor.set_program(grouped_program(review_program()))
editor.enter_group()
window.page_buttons[1].click()
appearance=ReviewAppearance(window,window.dashboard,window.page_header,None)
appearance.select('retro_console')
window.show()
editor.timeline.set_screens(('Front','Left','Right','Bottom'))
editor.hierarchy.contents.choose(1, Qt.KeyboardModifier.NoModifier)
root=Path(__file__).parent

for width in (1440,1175,720):
 window.resize(width,1000)
 for _ in range(8): app.processEvents()
 window.protocol.config_scroll.verticalScrollBar().setValue(0)
 app.processEvents()
 window.grab().save(str(root/f'protocol-{width}.png'))
 editor.timeline_card.grab().save(str(root/f'timeline-{width}.png'))
 editor.settings_card.grab().save(str(root/f'settings-{width}.png'))
 window.protocol.config_scroll.ensureWidgetVisible(editor.subgroup.composer.duration)
 app.processEvents()
 window.grab().save(str(root/f'editor-{width}.png'))
 left=editor.subgroup.composer.rows['Left']
 left.advanced.trigger()
 for _ in range(4): app.processEvents()
 left.parameters.advanced_card.grab().save(str(root/f'advanced-{width}.png'))
 left.advanced.trigger()
appearance.select('standard')
window.close()
window.deleteLater()
app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
app.processEvents()
