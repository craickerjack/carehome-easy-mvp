import os
import sqlite3
import tempfile

import pytest

from app import app, init_db


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "carehome.db"

    def connect(path, *args, **kwargs):
        if path == "carehome.db":
            path = db_path
        return sqlite3.connect(path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    init_db()
    app.testing = True
    with app.test_client() as client:
        yield client


def test_post_and_get_care_plan(client):
    resident = "alice"
    item_data = {"index": 1, "text": "Check vitals"}

    resp = client.post(f"/api/care-plans/{resident}", json=item_data)
    assert resp.status_code == 200
    assert resp.get_json().get("success") is True

    resp = client.get(f"/api/care-plans/{resident}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert item_data["text"] in data["items"]
