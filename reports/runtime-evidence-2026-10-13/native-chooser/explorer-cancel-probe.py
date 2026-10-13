from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QWidget
from cephvr.gui.file_dialogs import file_dialog, open_file_dialog
app=QApplication([])
from cephvr.gui.theme import apply_theme
apply_theme(app)
for cycle in range(10):
    print(cycle,'create',flush=True)
    parent=QWidget();parent.show();app.processEvents()
    dialog=file_dialog(parent,'Native cancellation probe')
    dialog.finished.connect(lambda result: print('finished',result,flush=True))
    def cancel(selected=dialog):
        print('native',selected.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen),flush=True)
        selected.reject()
        print('reject returned',flush=True)
    timer=QTimer(dialog);timer.setSingleShot(True);timer.timeout.connect(cancel);timer.start(50)
    open_file_dialog(dialog)
    print('process',flush=True)
    app.processEvents()
    print('process returned',flush=True)
    dialog.deleteLater();parent.deleteLater();app.processEvents()
    print('cleanup returned',flush=True)


