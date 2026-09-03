import sqlite3
from pathlib import Path
from typing import Any

class HistoryRepository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._initialize()
    def _connect(self):
        connection = sqlite3.connect(self.path); connection.row_factory = sqlite3.Row; return connection
    def _initialize(self):
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, title TEXT NOT NULL, original_url TEXT, webpage_url TEXT, extractor TEXT, uploader TEXT, duration REAL, format TEXT, resolution TEXT, output_format TEXT, filesize INTEGER, download_folder TEXT, final_filepath TEXT, started_at TEXT, completed_at TEXT, status TEXT NOT NULL, error TEXT)""")
    def add(self, **values: Any) -> int:
        fields = ["task_id","title","original_url","webpage_url","extractor","uploader","duration","format","resolution","output_format","filesize","download_folder","final_filepath","started_at","completed_at","status","error"]
        data = [values.get(f) for f in fields]
        with self._connect() as db:
            cur=db.execute(f"INSERT INTO history ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", data); return int(cur.lastrowid)
    def get_all(self, search: str="", status: str="All") -> list[dict]:
        sql="SELECT * FROM history WHERE (title LIKE ? OR original_url LIKE ? OR extractor LIKE ?)"; args=[f"%{search}%"]*3
        if status != "All": sql += " AND status=?"; args.append(status)
        sql += " ORDER BY id DESC"
        with self._connect() as db: return [dict(r) for r in db.execute(sql,args)]
    def delete(self, row_id: int):
        with self._connect() as db: db.execute("DELETE FROM history WHERE id=?", (row_id,))
    def clear(self):
        with self._connect() as db: db.execute("DELETE FROM history")

