import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from ui.dialogs import SettingsDialog


def test_sensitive_settings_are_never_exported():
    assert SettingsDialog.safe_export_value("cookies/file","secret.txt") is None
    assert SettingsDialog.safe_export_value("cookies/browser","chrome") is None
    assert SettingsDialog.safe_export_value("network/proxy","http://user:pass@host") is None
    assert SettingsDialog.safe_export_value("appearance/theme","Dark")=="Dark"


def test_settings_search_filters_categories(tmp_path):
    app=QApplication.instance() or QApplication([])
    dialog=SettingsDialog(QSettings(str(tmp_path/"settings.ini"),QSettings.IniFormat))
    dialog.settings_search.setText("proxy")
    visible=[dialog.categories.item(index).text() for index in range(dialog.categories.count()) if not dialog.categories.item(index).isHidden()]
    assert visible==["Network"]
    dialog.settings_search.setText("cover")
    visible=[dialog.categories.item(index).text() for index in range(dialog.categories.count()) if not dialog.categories.item(index).isHidden()]
    assert "Audio" in visible
    dialog.close()


def test_changes_are_reported(tmp_path):
    app=QApplication.instance() or QApplication([])
    dialog=SettingsDialog(QSettings(str(tmp_path/"settings.ini"),QSettings.IniFormat))
    assert dialog.change_summary.text()=="No unsaved changes"
    dialog.notify_complete.setChecked(not dialog.notify_complete.isChecked())
    assert dialog.change_summary.text()=="Unsaved changes"
    dialog.close()


def test_apply_persists_without_closing_and_emits_signal(tmp_path):
    app=QApplication.instance() or QApplication([]);settings=QSettings(str(tmp_path/"settings.ini"),QSettings.IniFormat);dialog=SettingsDialog(settings);events=[];dialog.settings_applied.connect(lambda:events.append(True));dialog.theme.setCurrentText("Light");dialog.save(False)
    assert events==[True] and settings.value("appearance/theme")=="Light"
    assert dialog.change_summary.text()=="All changes applied" and dialog.isVisible() is False
    dialog.close()


def test_diagnostics_do_not_copy_sensitive_values(tmp_path):
    app=QApplication.instance() or QApplication([]);settings=QSettings(str(tmp_path/"settings.ini"),QSettings.IniFormat);settings.setValue("cookies/file","secret-cookie-path");settings.setValue("network/proxy","http://user:secret-password@host");dialog=SettingsDialog(settings);dialog.copy_diagnostics();text=app.clipboard().text()
    assert "secret-cookie-path" not in text and "secret-password" not in text
    assert "yt-dlp:" in text and "Cookie authentication enabled:" in text
    dialog.close()
