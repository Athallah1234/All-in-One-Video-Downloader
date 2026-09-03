from repositories.history_repository import HistoryRepository

def test_history_roundtrip(tmp_path):
    repo=HistoryRepository(tmp_path/"history.db")
    row_id=repo.add(title="Example",original_url="https://example.com",status="Completed")
    rows=repo.get_all("Exam")
    assert rows[0]["id"]==row_id
    repo.delete(row_id)
    assert repo.get_all()==[]

