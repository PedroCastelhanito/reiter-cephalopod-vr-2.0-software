from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
old = QTest.keyClick

def debug(widget,*args,**kwargs):
    w=widget.window(); e=w.protocol.editor
    focus=QApplication.focusWidget()
    print('KEY DEBUG',{'key':str(args),'active':w.isActiveWindow(),'widget_visible':widget.isVisible(),'widget_enabled':widget.isEnabled(),'focus':None if focus is None else (type(focus).__name__,focus.accessibleName()),'wanted_focus':widget.hasFocus(),'scope':e.scope,'selected_paths':e.selected_paths,'editor_enabled':e.isEnabled()},flush=True)
    old(widget,*args,**kwargs)
    print('KEY AFTER',{'feedback':e.feedback.text(),'notice':e.subgroup.notice.text(),'scope':e.scope,'count':len(e.program.sequence[0].body)},flush=True)

def pytest_runtest_call(item):
    QTest.keyClick = debug
