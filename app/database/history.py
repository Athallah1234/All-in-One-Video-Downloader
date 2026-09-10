"""Main-thread SQLite repository; parameterized values only."""
import json
import sqlite3
from pathlib import Path
from app.core.utils import private_url, redact
from app.services.settings import ROOT


class HistoryRepository:
    def __init__(self, path: Path | None = None):
        path = path or ROOT / "data/history.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("""CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY, title TEXT, source_url TEXT, extractor TEXT,
            media_type TEXT, format TEXT, quality TEXT, output_path TEXT, file_path TEXT,
            status TEXT, file_size INTEGER, started_at TEXT, completed_at TEXT,
            error_message TEXT, preferences TEXT)""")
        self.connection.execute("UPDATE history SET status='Failed', error_message='Application stopped before this task finished' WHERE status IN ('Downloading','Analyzing','Processing','Waiting','Pausing','Paused','Retrying')")
        self.connection.commit()

    def save(self, task) -> int:
        preferences = {k: v for k, v in task.options.items() if k not in {"proxy", "proxy_type", "socks_host", "socks_port", "socks_username", "socks_password", "cookie_file", "extra", "cookies", "browser", "username", "password", "site_login", "use_netrc", "netrc_location"}}
        values = (task.title, private_url(task.url), task.extractor, task.media_type,
                  task.options.get("format", ""), task.options.get("quality", ""),
                  task.options.get("output", ""), task.file_path, str(task.status), task.file_size,
                  task.started_at, task.completed_at, redact(task.error, (task.options.get("username"), task.options.get("password"), task.options.get("socks_username"), task.options.get("socks_password"))), json.dumps(preferences))
        if task.history_id:
            self.connection.execute("""UPDATE history SET title=?,source_url=?,extractor=?,media_type=?,format=?,quality=?,output_path=?,file_path=?,status=?,file_size=?,started_at=?,completed_at=?,error_message=?,preferences=? WHERE id=?""", (*values, task.history_id))
            identifier = task.history_id
        else:
            cursor = self.connection.execute("INSERT INTO history(title,source_url,extractor,media_type,format,quality,output_path,file_path,status,file_size,started_at,completed_at,error_message,preferences) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
            identifier = cursor.lastrowid
        self.connection.commit()
        return identifier

    def list(self, query: str = "", category: str = "All") -> list[dict]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM history WHERE (title LIKE ? OR source_url LIKE ?) AND (?='All' OR status=? OR media_type=?) ORDER BY id DESC", (f"%{query}%", f"%{query}%", category, category, category))]

    def delete(self, identifiers: list[int]) -> None:
        self.connection.executemany("DELETE FROM history WHERE id=?", [(i,) for i in identifiers])
        self.connection.commit()

    def clear(self) -> None:
        self.connection.execute("DELETE FROM history")
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
