"""Small reusable Qt widgets and dialog helpers."""
import json
from pathlib import Path
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDialog, QVBoxLayout, QPlainTextEdit, QDialogButtonBox, QMessageBox)


def button(text, callback, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def combo(items, current=None):
    widget = QComboBox()
    widget.addItems(items)
    if current in items:
        widget.setCurrentText(current)
    return widget


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setAlternatingRowColors(True)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.verticalHeader().hide()
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    widget.horizontalHeader().setStretchLastSection(True)
    widget.verticalHeader().setDefaultSectionSize(37)
    return widget


def fill_table(widget, rows):
    widget.setSortingEnabled(False)
    widget.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(str(value) if value is not None else "—")
            item.setToolTip(item.text())
            widget.setItem(r, c, item)


def open_path(path, folder=False):
    target = Path(path)
    if folder and target.is_file():
        target = target.parent
    if target.exists():
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve())))
    else:
        QMessageBox.warning(None, "File unavailable", "The file or folder does not exist yet.")


def details(parent, title, data):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(780, 560)
    layout = QVBoxLayout(dialog)
    text = QPlainTextEdit()
    text.setReadOnly(True)
    text.setPlainText(json.dumps(data, indent=2, ensure_ascii=False, default=str) if not isinstance(data, str) else data)
    layout.addWidget(text)
    close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    close.rejected.connect(dialog.reject)
    layout.addWidget(close)
    dialog.exec()
