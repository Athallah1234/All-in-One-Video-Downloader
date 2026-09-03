import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication
from ui.log_highlighter import LogSyntaxHighlighter

def test_log_level_color_mapping():
    app=QApplication.instance() or QApplication([])
    document=QTextDocument()
    highlighter=LogSyntaxHighlighter(document)
    expected={"ERROR":"#ff5c5c","WARNING":"#f2c94c","INFO":"#35c77a","DEBUG":"#8b95a7"}
    for level,color in expected.items():
        assert highlighter.format_for_level(level).foreground().color().name()==color
        assert highlighter.level_for_text(f"[2026-09-02 10:00:00] [{level}] message")==level
    document.setPlainText("[2026-09-02 10:00:00] [ERROR] failed")
    highlighter.rehighlight(); app.processEvents()
    ranges=document.firstBlock().layout().formats()
    assert ranges and ranges[0].format.foreground().color().name()=="#ff5c5c"

def test_search_highlight_does_not_change_plain_text():
    app=QApplication.instance() or QApplication([])
    document=QTextDocument("[INFO] Download completed")
    highlighter=LogSyntaxHighlighter(document); highlighter.set_search_term("completed"); app.processEvents()
    assert document.toPlainText()=="[INFO] Download completed"

