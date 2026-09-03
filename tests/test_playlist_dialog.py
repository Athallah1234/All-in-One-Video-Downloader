import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from ui.dialogs import PlaylistDialog

def test_playlist_selection_and_filter():
    app=QApplication.instance() or QApplication([])
    playlist={"title":"Test", "entries":[
        {"id":"a", "title":"Alpha", "playlist_index":1, "duration":10},
        {"id":"b", "title":"Beta", "playlist_index":2, "duration":20},
        {"title":"Private", "playlist_index":3, "availability":"private"},
    ]}
    dialog=PlaylistDialog(playlist)
    while dialog._next_entry < len(dialog.entries): app.processEvents()
    assert dialog.selected_indices()==[1,2]
    dialog.search.setText("Beta"); app.processEvents()
    assert sum(not dialog.table.isRowHidden(row) for row in range(3))==1
    dialog.set_visible_checks(Qt.Unchecked)
    assert dialog.selected_indices()==[1]
    dialog.close()
