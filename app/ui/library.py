"""Queue, searchable local history and real-time log views."""
import csv
import json
from datetime import datetime, timezone
from collections import deque
from dataclasses import asdict
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QTimer, QSignalBlocker, QItemSelectionModel
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QCheckBox, QMenu, QApplication, QFileDialog, QMessageBox, QProgressBar)
from app.core.models import Status, TERMINAL
from app.core.utils import size, duration, private_url
from app.ui.widgets import button, combo, table, fill_table, details, open_path


class QueueView(QWidget):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.ids = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 5, 16, 8)
        header = QHBoxLayout()
        self.label = QLabel("Download queue • 0 items")
        self.label.setStyleSheet("font-weight: 600;")
        header.addWidget(self.label)
        header.addStretch()
        layout.addLayout(header)
        header = QHBoxLayout()
        self.pause_button = button("Pause Selected", self.pause_selected)
        self.resume_button = button("Resume Selected", self.resume_selected)
        self.pause_button.setToolTip("Pause at the next download checkpoint. Network requests or FFmpeg may finish first. Active paused jobs retain their queue slot.")
        self.resume_button.setToolTip("Continue selected paused jobs, or withdraw pending pause requests.")
        header.addWidget(self.pause_button)
        header.addWidget(self.resume_button)
        header.addWidget(button("Cancel Selected", self.cancel_selected))
        header.addWidget(button("Retry Failed", self.retry_failed))
        header.addWidget(button("Remove Selected", self.remove_selected))
        header.addWidget(button("Clear Completed", self.clear_completed))
        layout.addLayout(header)
        self.table = table(["#", "Title / URL", "Status", "Progress", "Speed", "ETA", "Size", "Item"])
        self.table.setColumnWidth(0, 35)
        self.table.setColumnWidth(1, 290)
        self.table.setColumnWidth(2, 190)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 95)
        self.table.setColumnWidth(5, 80)
        layout.addWidget(self.table)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context)
        self.table.cellDoubleClicked.connect(self.show_details)
        self.manager.changed.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.retry_clock = QTimer(self)
        self.retry_clock.setInterval(1000)
        self.retry_clock.timeout.connect(self.refresh_retry_countdowns)
        self.retry_clock.start()
        self.update_actions()

    def refresh_retry_countdowns(self):
        if any(task.status == Status.RETRYING for task in self.manager.tasks.values()):
            self.refresh()

    def selected_ids(self):
        return [self.ids[index.row()] for index in self.table.selectionModel().selectedRows() if index.row() < len(self.ids)]

    def refresh(self):
        selected = self.selected_ids()
        blocker = QSignalBlocker(self.table)
        self.ids = list(self.manager.tasks)
        self.table.setRowCount(len(self.ids))
        from PySide6.QtWidgets import QTableWidgetItem
        for row, identifier in enumerate(self.ids):
            task = self.manager.tasks[identifier]
            status = task.status
            if task.status == Status.RETRYING and task.next_retry_at:
                remaining = max(0, int((datetime.fromisoformat(task.next_retry_at) - datetime.now(timezone.utc)).total_seconds() + .999))
                status = f"Retrying in {remaining}s ({task.retry_attempt}/{task.retry_limit})"
            values = [row + 1, task.title if task.title != "Waiting for metadata" else private_url(task.url), status, f"{task.progress:.1f}%", size(task.speed) + "/s" if task.speed else "—", duration(task.eta), f"{size(task.downloaded)} / {size(task.file_size) if task.file_size else '?'}", task.item or "—"]
            for column, value in enumerate(values):
                item = self.table.item(row, column)
                if item is None:
                    item = QTableWidgetItem()
                    self.table.setItem(row, column, item)
                if item.text() != str(value):
                    item.setText(str(value))
                item.setToolTip(task.error or task.file_path or private_url(task.url))
            bar = self.table.cellWidget(row, 3)
            if bar is None:
                bar = QProgressBar()
                self.table.setCellWidget(row, 3, bar)
            indeterminate = task.status in {Status.ANALYZING, Status.PROCESSING} or task.status == Status.DOWNLOADING and not task.file_size
            bar.setRange(0, 0 if indeterminate else 100)
            if not indeterminate:
                bar.setValue(int(task.progress))
        self.table.clearSelection()
        for row, identifier in enumerate(self.ids):
            if identifier in selected:
                self.table.selectionModel().select(self.table.model().index(row, 0),
                    QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        blocker.unblock()
        waiting = sum(t.status == Status.WAITING for t in self.manager.tasks.values())
        paused = sum(t.status in {Status.PAUSING, Status.PAUSED} for t in self.manager.tasks.values())
        self.label.setText(f"Download queue | {len(self.ids)} items | {len(self.manager.workers)} workers | {waiting} waiting | {paused} paused / pausing")
        self.update_actions()

    def update_actions(self):
        selected = self.selected_ids()
        self.pause_button.setEnabled(any(self.manager.can_pause(i) for i in selected))
        self.resume_button.setEnabled(any(self.manager.can_resume(i) for i in selected))

    def pause_selected(self):
        for identifier in self.selected_ids():
            self.manager.pause(identifier)

    def resume_selected(self):
        for identifier in self.selected_ids():
            self.manager.resume(identifier)

    def cancel_selected(self):
        for identifier in self.selected_ids():
            self.manager.cancel(identifier)

    def retry_failed(self):
        for identifier, task in list(self.manager.tasks.items()):
            if task.status == Status.FAILED:
                self.manager.retry(identifier)

    def remove_selected(self):
        self.manager.remove(self.selected_ids())

    def clear_completed(self):
        self.manager.remove([i for i, task in self.manager.tasks.items() if task.status == Status.COMPLETED])

    def show_details(self, row, column=0):
        if row >= len(self.ids):
            return
        task = self.manager.tasks[self.ids[row]]
        data = {k: v for k, v in asdict(task).items() if k not in {"options", "url"}}
        data.update(URL=private_url(task.url), format=task.options.get("format"), destination=task.options.get("output"))
        details(self, "Download details", data)

    def context(self, point):
        row = self.table.rowAt(point.y())
        if row < 0:
            return
        task = self.manager.tasks[self.ids[row]]
        menu = QMenu(self)
        callbacks = [("Pause", lambda: self.manager.pause(task.id), self.manager.can_pause(task.id)),
                     ("Resume", lambda: self.manager.resume(task.id), self.manager.can_resume(task.id)),
                     ("Retry Now", lambda: self.manager.retry_now(task.id), task.status == Status.RETRYING),
                     ("Cancel", lambda: self.manager.cancel(task.id), task.status not in TERMINAL),
                     ("Retry", lambda: self.manager.retry(task.id), task.status in TERMINAL),
                     ("Open File", lambda: open_path(task.file_path), bool(task.file_path) and Path(task.file_path).is_file()),
                     ("Open Folder", lambda: open_path(task.options["output"], True), True),
                     ("Copy URL", lambda: QApplication.clipboard().setText(task.url), True),
                     ("Copy Title", lambda: QApplication.clipboard().setText(task.title), True),
                     ("Remove Completed", self.clear_completed, True),
                     ("Details", lambda: self.show_details(row), True)]
        for label, callback, enabled in callbacks:
            action = menu.addAction(label)
            action.setEnabled(enabled)
            action.triggered.connect(callback)
        menu.exec(self.table.viewport().mapToGlobal(point))


class HistoryTab(QWidget):
    retry_requested = Signal(object)

    def __init__(self, repository, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search history by title or source URL…")
        self.filter = combo(["All", "Completed", "Failed", "Cancelled", "Video", "360° / VR", "Live Stream", "Audio", "Playlist", "Channel", "Batch URL", "Subtitle", "Metadata"])
        bar.addWidget(self.search, 1)
        bar.addWidget(self.filter)
        layout.addLayout(bar)
        self.empty = QLabel("No download history yet.")
        self.empty.setObjectName("notice")
        layout.addWidget(self.empty)
        self.table = table(["Date (UTC)", "Title", "Type", "Website", "Format", "Quality", "Status", "File Size"])
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(1, 300)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        for label, callback in [("Refresh", self.refresh), ("Delete Selected", self.delete_selected), ("Clear History", self.clear), ("Export History…", self.export)]:
            actions.addWidget(button(label, callback))
        actions.addStretch()
        layout.addLayout(actions)
        self.search.textChanged.connect(self.refresh)
        self.filter.currentTextChanged.connect(self.refresh)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context)
        self.table.cellDoubleClicked.connect(lambda row, col: details(self, "History details", self.rows[row]))
        self.refresh()

    def refresh(self):
        self.rows = self.repository.list(self.search.text(), self.filter.currentText())
        fill_table(self.table, [[r["completed_at"] or r["started_at"], r["title"], r["media_type"], r["extractor"], r["format"], r["quality"], r["status"], size(r["file_size"])] for r in self.rows])
        self.empty.setVisible(not self.rows)

    def delete_selected(self):
        ids = [self.rows[index.row()]["id"] for index in self.table.selectionModel().selectedRows()]
        self.repository.delete(ids)
        self.refresh()

    def clear(self):
        if QMessageBox.question(self, "Clear history", "Remove all local history records? Downloaded files will be kept.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.repository.clear()
            self.refresh()

    def export(self):
        path, kind = QFileDialog.getSaveFileName(self, "Export filtered history", "history.json", "JSON (*.json);;CSV (*.csv)")
        if not path:
            return
        try:
            if "CSV" in kind:
                with Path(path).open("w", newline="", encoding="utf-8-sig") as stream:
                    fields = list(self.rows[0]) if self.rows else ["id", "title", "status"]
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    # Neutralize spreadsheet formula injection in exported external titles.
                    writer.writerows({k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v for k, v in row.items()} for row in self.rows)
            else:
                Path(path).write_text(json.dumps(self.rows, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as error:
            QMessageBox.warning(self, "Export failed", str(error))

    def context(self, point):
        row = self.table.rowAt(point.y())
        if row < 0:
            return
        record = self.rows[row]
        menu = QMenu(self)
        for label, callback in [("Open File", lambda: open_path(record["file_path"]) if record["file_path"] else QMessageBox.information(self, "No media file", "This record has no final media file. Open its output folder to view sidecar files.")),
                                ("Open Folder", lambda: open_path(record["output_path"], True)),
                                ("Copy URL", lambda: QApplication.clipboard().setText(record["source_url"])),
                                ("Retry Download", lambda: self.retry_requested.emit(record)),
                                ("Remove from History", lambda: self.remove(record["id"])),
                                ("View Details", lambda: details(self, "History details", record))]:
            menu.addAction(label).triggered.connect(callback)
        menu.exec(self.table.viewport().mapToGlobal(point))

    def remove(self, identifier):
        self.repository.delete([identifier])
        self.refresh()


class LogTab(QWidget):
    def __init__(self, bus, parent=None):
        super().__init__(parent)
        self.lines = deque(maxlen=5000)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        filters = QHBoxLayout()
        self.level = combo(["All", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search log…")
        self.auto_scroll = QCheckBox("Auto Scroll")
        self.auto_scroll.setChecked(True)
        filters.addWidget(self.level)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.auto_scroll)
        layout.addLayout(filters)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.document().setMaximumBlockCount(5000)
        self.text.setPlaceholderText("Application logs will appear here.")
        layout.addWidget(self.text)
        actions = QHBoxLayout()
        for label, callback in [("Clear Log", self.clear), ("Copy Selected", self.text.copy), ("Save Log…", self.save)]:
            actions.addWidget(button(label, callback))
        actions.addStretch()
        layout.addLayout(actions)
        bus.message.connect(self.add)
        self.level.currentTextChanged.connect(self.filter)
        self.search.textChanged.connect(self.filter)

    def matches(self, level, line):
        return (self.level.currentText() == "All" or level == self.level.currentText()) and self.search.text().casefold() in line.casefold()

    def add(self, level, line):
        self.lines.append((level, line))
        if self.matches(level, line):
            scroll = self.text.verticalScrollBar()
            previous = scroll.value()
            self.text.appendPlainText(line)
            scroll.setValue(scroll.maximum() if self.auto_scroll.isChecked() else previous)

    def filter(self):
        self.text.setPlainText("\n".join(line for level, line in self.lines if self.matches(level, line)))

    def clear(self):
        self.lines.clear()
        self.text.clear()

    def save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save filtered log", "app.log", "Log (*.log);;Text (*.txt)")
        if path:
            try:
                Path(path).write_text(self.text.toPlainText(), encoding="utf-8")
            except OSError as error:
                QMessageBox.warning(self, "Save failed", str(error))
