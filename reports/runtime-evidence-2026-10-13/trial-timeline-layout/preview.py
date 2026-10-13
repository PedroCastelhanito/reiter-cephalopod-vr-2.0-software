from pathlib import Path
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout
from cephvr.gui.theme import apply_theme
from cephvr.gui.protocol_editor import ProtocolEditor
from cephvr.gui.protocol_document import review_program
from cephvr.gui.protocol_batches import grouped_program
app=QApplication([])
apply_theme(app)
window=QWidget()
window.setObjectName('preview')
window.setStyleSheet('QWidget#preview { background: #081018; }')
layout=QVBoxLayout(window)
layout.setContentsMargins(24,24,24,24)
editor=ProtocolEditor()
layout.addWidget(editor)
editor.set_program(grouped_program(review_program()))
editor.timeline.set_screens(('Left','Right'))
editor.select_epochs(((0,1),))
window.show()
root=Path('reports/runtime-evidence-2026-10-13/trial-timeline-layout')
for count,width in ((1,1200),(8,1200),(8,720)):
    while len(editor.program.sequence)<count:
        editor.add_group()
    window.resize(width,1000)
    app.processEvents()
    editor.timeline.scrollbar.setValue(editor.timeline.scrollbar.maximum())
    app.processEvents()
    timeline=editor.timeline
    right=min(timeline.width(),len(timeline.nodes)*timeline.block_width()-timeline.scrollbar.value()-7)
    assert abs(editor.group_editor.geometry().right()+1-timeline.x()-right)<=1
    assert editor.sequence_summary.geometry().bottom()<timeline.y()
    assert editor.group_editor.y()>timeline.geometry().bottom()
    assert editor.group_editor.width()<=420
    editor.timeline_card.grab().save(str(root/f'{count}-groups-{width}.png'))
    print(f'{count} groups/{width}px: summary above, controls below and right-aligned; block width {timeline.block_width():.1f}')
window.close()
