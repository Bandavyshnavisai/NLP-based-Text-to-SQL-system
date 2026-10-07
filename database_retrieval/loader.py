"""Database Loader — high-level entry point for the Dynamic User Database mode.

This module is the single public API for Phase 2 of the generalization work.
It replaces the need for Spider metadata when a user supplies their own
SQLite database.

Usage
-----
::

    from database_retrieval.loader import load_database

    active_db = load_database("/path/to/mydb.db")
    schema    = active_db.get_schema()          # ready for SchemaLinker

    # Full pipeline (Dynamic mode):
    from schema_linking import SchemaLinker
    linker = SchemaLinker()
    result = linker.link("What is the average salary?", target_schema=schema)

Pipeline contrast
-----------------
Spider Benchmark Mode (Mode 1 — unchanged):
    question → DatabaseRetriever → Spider DB → SchemaLinker → result

Dynamic User Database Mode (Mode 2 — this module):
    user SQLite file → load_database() → ActiveDatabase → SchemaLinker → result
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from .active_database import ActiveDatabase
from .adapter import SQLiteAdapter, _SQLITE_EXTENSIONS


def load_database(path: Union[str, Path]) -> ActiveDatabase:
    """Validate and load a user-supplied SQLite database.

    This is the primary entry point for **Dynamic User Database Mode**.
    It performs all necessary validation and returns an :class:`ActiveDatabase`
    whose schema can be passed directly to
    :meth:`schema_linking.SchemaLinker.link` via ``target_schema``.

    Steps performed:
      1. Check that the file exists.
      2. Check that the extension is ``.db``, ``.sqlite``, or ``.sqlite3``.
      3. Validate that the file is a well-formed SQLite database.
      4. Confirm the database contains at least one user table.
      5. Extract the full relational schema dynamically.
      6. Return an :class:`ActiveDatabase` wrapping all metadata.

    The source database is **never modified** — all access is read-only.

    Args:
        path: Absolute or relative path to the SQLite file.
              Accepted extensions: ``.db``, ``.sqlite``, ``.sqlite3``.

    Returns:
        An :class:`ActiveDatabase` instance containing the validated path,
        logical database name, database type, and extracted schema.

    Raises:
        FileNotFoundError: The file does not exist.
        ValueError: Unsupported extension, invalid SQLite format, or the
                    database contains no user tables.

    Example::

        db = load_database("company.db")
        print(db.database_name)   # "company"
        print(db.table_names)     # ["departments", "employees"]

        from schema_linking import SchemaLinker
        linker = SchemaLinker()
        result = linker.link(
            "What is the average salary?",
            target_schema=db.get_schema(),
        )
    """
    path = Path(path).resolve()

    # --- Step 1: file existence (give an early, clear error) -----------
    if not path.exists():
        raise FileNotFoundError(f"Database file not found: {path}")

    # --- Step 2: extension check (before opening the file) -------------
    if path.suffix.lower() not in _SQLITE_EXTENSIONS:
        raise ValueError(
            f"Unsupported file extension '{path.suffix}'. "
            f"load_database() currently supports SQLite files only. "
            f"Supported extensions: {sorted(_SQLITE_EXTENSIONS)}"
        )

    # --- Steps 3–4: delegate to SQLiteAdapter --------------------------
    adapter = SQLiteAdapter(path)
    adapter.validate()   # raises FileNotFoundError / ValueError on failure

    # --- Step 5: extract schema ----------------------------------------
    schema = adapter.get_schema()

    # --- Step 6: return ActiveDatabase ---------------------------------
    return ActiveDatabase(
        path=path,
        database_name=schema["database_name"],
        database_type="sqlite",
        schema=schema,
    )
