"""Expose minimum widths after reproducing owning failing GUI scenarios."""
import runpy
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget
from cephvr.gui.theme import apply_theme
from cephvr.gui.window import DashboardWindow
from cephvr.gui.review import ReviewControls

app = QApplication([])
apply_theme(app)
tests = runpy.run_path("tests/gui/test_dashboard.py")
temp = Path(".tmp/gui-layout-cases")
temp.mkdir(parents=True, exist_ok=True)

def inspect(widget, depth=0, cutoff=200):
    if depth > 13 or widget.minimumSizeHint().width() < cutoff:
        return
    title = getattr(widget, "text", lambda: "")()
    print(" " * depth, type(widget).__name__, str(title)[:45], "width",widget.width(), "minhint",widget.minimumSizeHint().width())
    for child in widget.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
        inspect(child, depth+1, cutoff)

for name in ("test_responsive_navigation_preserves_widget_identity", "test_protocol_cards_reflow_and_keep_properties_reachable", "test_variation_controls_fit_narrow_protocol_without_horizontal_scroll", "test_random_batch_values_stay_fixed_across_preview_and_save"):
    window=DashboardWindow(sample=True)
    ReviewControls(window)
    window.show()
    app.processEvents()
    print("CASE",name)
    try:
        args={"window":window,"app":app,"tmp_path":temp}
        import inspect as introspection
        tests[name](**{k:v for k,v in args.items() if k in introspection.signature(tests[name]).parameters})
    except AssertionError:
        print("ASSERTION REPRODUCED")
    inspect(window.dashboard_scroll.widget() if "navigation" in name else window.protocol.config_scroll.widget())
    window.close()
    window.deleteLater()
    app.processEvents()
