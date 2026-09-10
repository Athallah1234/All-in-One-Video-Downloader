"""Consistent dark/light palettes and restrained Qt styling."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor


def apply_theme(app, theme):
    dark = theme == "Dark" or theme == "System" and app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    bg, card, field = ("#10131d", "#191e2b", "#202737") if dark else ("#f3f5fb", "#ffffff", "#edf0f8")
    fg, muted, border = ("#edf0fa", "#a9b3ca", "#303a50") if dark else ("#20283e", "#62708a", "#d9dfed")
    palette = QPalette()
    for role, color in [(QPalette.ColorRole.Window, bg), (QPalette.ColorRole.WindowText, fg),
                        (QPalette.ColorRole.Base, card), (QPalette.ColorRole.AlternateBase, field),
                        (QPalette.ColorRole.Text, fg), (QPalette.ColorRole.Button, field),
                        (QPalette.ColorRole.ButtonText, fg), (QPalette.ColorRole.Highlight, "#7467ef"),
                        (QPalette.ColorRole.HighlightedText, "#ffffff"), (QPalette.ColorRole.ToolTipBase, card),
                        (QPalette.ColorRole.ToolTipText, fg)]:
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(f"""
        QWidget {{ font-family: 'Segoe UI', sans-serif; font-size: 12px; color: {fg}; }}
        QMainWindow, QDialog {{ background: {bg}; }}
        QLabel#heading {{ font-size: 25px; font-weight: 700; }}
        QLabel#muted {{ color: {muted}; }}
        QLabel#notice {{ background: {field}; padding: 10px; border-radius: 7px; color: {muted}; }}
        QGroupBox {{ background: {card}; border: 1px solid {border}; border-radius: 10px; margin-top: 18px; padding: 14px 10px 8px; font-weight: 600; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 5px; }}
        QLineEdit, QPlainTextEdit, QSpinBox, QComboBox, QDateEdit {{ background: {field}; border: 1px solid {border}; border-radius: 6px; padding: 7px; selection-background-color: #7467ef; }}
        QLineEdit:focus, QPlainTextEdit:focus {{ border-color: #8b7bff; }}
        QPushButton {{ background: {field}; border: 1px solid {border}; border-radius: 7px; padding: 8px 13px; font-weight: 600; }}
        QPushButton:hover {{ border-color: #8b7bff; }}
        QPushButton#primary {{ background: #7467ef; color: white; border-color: #7467ef; }}
        QPushButton:disabled {{ color: {muted}; background: {bg}; }}
        QPushButton#primary:disabled {{ color: {muted}; background: {field}; border-color: {border}; }}
        QTabWidget::pane {{ border: 1px solid {border}; border-radius: 8px; background: {card}; }}
        QTabBar::tab {{ padding: 10px 16px; margin-right: 3px; color: {muted}; border: none; background: transparent; }}
        QTabBar::tab:selected {{ color: {fg}; border-bottom: 3px solid #8b7bff; }}
        QTableWidget {{ background: {card}; alternate-background-color: {field}; border: 1px solid {border}; border-radius: 7px; gridline-color: {border}; }}
        QHeaderView::section {{ background: {field}; padding: 9px; border: none; color: {muted}; }}
        QProgressBar {{ border: none; border-radius: 5px; background: {field}; text-align: center; min-height: 18px; }}
        QProgressBar::chunk {{ background: #7467ef; border-radius: 5px; }}
        QMenu {{ background: {card}; border: 1px solid {border}; }}
        QMenu::item:selected {{ background: #7467ef; color: white; }}
        QScrollArea {{ border: none; }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
    """)
