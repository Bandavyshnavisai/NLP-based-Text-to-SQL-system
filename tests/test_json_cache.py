import json
import sqlite3
from pathlib import Path

from database_retrieval.cache_manager import get_or_create_database_cache, get_cache_info


def make_db(path: Path):
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT, marks INTEGER)"
    )
    con.executemany(
        "INSERT INTO students VALUES (?, ?, ?)",
        [(1, "Arun", 92), (2, "Priya", 88)],
    )
    con.commit()
    con.close()


def test_json_cache_first_and_second_use(tmp_path):
    db = tmp_path / "demo.sqlite"
    make_db(db)

    first = get_or_create_database_cache(db)
    assert first["cache_hit"] is False
    assert first["schema"]["total_tables"] == 1

    cache_dir = Path(first["cache_dir"])
    assert (cache_dir / "metadata.json").exists()
    assert (cache_dir / "schema.json").exists()
    assert (cache_dir / "schema_text.json").exists()
    assert (cache_dir / "retrieval.json").exists()

    second = get_or_create_database_cache(db)
    assert second["cache_hit"] is True
    assert second["metadata"]["sha256"] == first["metadata"]["sha256"]

    info = get_cache_info(db)
    assert info["cache_exists"] is True
    assert all(item["exists"] for item in info["files"].values())


def test_changed_database_gets_new_cache(tmp_path):
    db = tmp_path / "demo.sqlite"
    make_db(db)

    first = get_or_create_database_cache(db)
    first_hash = first["metadata"]["sha256"]

    con = sqlite3.connect(db)
    con.execute("ALTER TABLE students ADD COLUMN cgpa REAL")
    con.commit()
    con.close()

    second = get_or_create_database_cache(db)
    assert second["cache_hit"] is False
    assert second["metadata"]["sha256"] != first_hash
    assert any(c["name"] == "cgpa" for c in second["schema"]["tables"][0]["columns"])
