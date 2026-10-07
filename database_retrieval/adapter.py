"""Database Adapter abstraction layer.

Provides a thin, extensible abstraction over database connections so that
future adapters (PostgreSQL, MySQL, SQL Server) can be added without touching
the schema-linking or text-to-SQL layers.

Currently only SQLite is implemented.

Design
------
``DatabaseAdapter`` is an abstract base class that defines the contract:
  - ``validate()``  — ensure the source is a readable, valid database.
  - ``get_schema()`` — return the standard schema dict (Member-1 format).

``SQLiteAdapter`` implements the contract for ``.db / .sqlite / .sqlite3``
files using :class:`database_retrieval.schema_extractor.SchemaExtractor`.

The adapter is intentionally lightweight — it does NOT manage persistent
connections (SQLite files are opened/closed per operation).  Future adapters
for server-based engines may hold a connection pool.

Usage
-----
::

    from database_retrieval.adapter import SQLiteAdapter

    adapter = SQLiteAdapter("/path/to/mydb.db")
    adapter.validate()          # raises on invalid input
    schema = adapter.get_schema()

    # Or use the factory:
    from database_retrieval.adapter import get_adapter
    adapter = get_adapter("/path/to/mydb.sqlite3")
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict

from .schema_extractor import SchemaExtractor

# Supported SQLite file extensions
_SQLITE_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}


class DatabaseAdapter(ABC):
    """Abstract base class for database source adapters.

    Subclass this to add support for additional database engines
    (e.g. PostgreSQL, MySQL, SQL Server) without touching schema-linking
    or text-to-SQL code.
    """

    @property
    @abstractmethod
    def database_type(self) -> str:
        """Return a short string identifying the database engine, e.g. ``"sqlite"``."""

    @property
    @abstractmethod
    def database_name(self) -> str:
        """Return the logical database name."""

    @abstractmethod
    def validate(self) -> None:
        """Validate that the database source is accessible and well-formed.

        Raises:
            FileNotFoundError: If the source file / connection target does not exist.
            ValueError: If the source is not a valid or supported database.
        """

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Extract and return the full schema in the standard Member-1 format.

        Returns:
            Schema dict with keys ``database_name``, ``total_tables``, ``tables``,
            ``relationships``.  Compatible with ``SchemaLinker.link(target_schema=...)``.
        """


class SQLiteAdapter(DatabaseAdapter):
    """Adapter for local SQLite database files.

    Supports extensions: ``.db``, ``.sqlite``, ``.sqlite3``.

    The underlying database is always opened in **read-only** mode (using
    ``file:path?mode=ro&uri=true``).  The user's file is never modified.

    Args:
        path: Path to the SQLite file.  May be a ``str`` or :class:`pathlib.Path`.
    """

    def __init__(self, path: "str | Path") -> None:
        self._path = Path(path).resolve()
        self._extractor = SchemaExtractor()
        self._schema: Dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # DatabaseAdapter contract
    # ------------------------------------------------------------------

    @property
    def database_type(self) -> str:
        return "sqlite"

    @property
    def database_name(self) -> str:
        return self._path.stem

    def validate(self) -> None:
        """Validate the SQLite file.

        Checks (in order):
        1. File exists.
        2. Extension is ``.db``, ``.sqlite``, or ``.sqlite3``.
        3. File is a valid, readable SQLite database (magic bytes + connection).
        4. Database contains at least one user table.

        Raises:
            FileNotFoundError: File does not exist.
            ValueError: Extension unsupported, file is not a valid SQLite database,
                        or the database contains no user tables.
        """
        # 1. File existence
        if not self._path.exists():
            raise FileNotFoundError(
                f"Database file not found: {self._path}"
            )

        # 2. Extension check
        if self._path.suffix.lower() not in _SQLITE_EXTENSIONS:
            raise ValueError(
                f"Unsupported file extension '{self._path.suffix}'. "
                f"Supported extensions: {sorted(_SQLITE_EXTENSIONS)}"
            )

        # 3. SQLite magic-byte check (first 16 bytes must start with b"SQLite format 3\x00")
        try:
            with open(self._path, "rb") as fh:
                header = fh.read(16)
            if not header.startswith(b"SQLite format 3\x00"):
                raise ValueError(
                    f"File is not a valid SQLite database: {self._path}"
                )
        except (OSError, PermissionError) as exc:
            raise ValueError(
                f"Cannot read database file {self._path}: {exc}"
            ) from exc

        # 4. Open read-only and check for user tables
        try:
            uri = f"file:{self._path.as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name;"
                )
                tables = cur.fetchall()
            finally:
                conn.close()
        except sqlite3.DatabaseError as exc:
            raise ValueError(
                f"Cannot open SQLite database {self._path}: {exc}"
            ) from exc

        if not tables:
            raise ValueError(
                f"Database '{self._path.name}' contains no user tables. "
                "At least one table is required."
            )

    def get_schema(self) -> Dict[str, Any]:
        """Extract and return the full schema for this SQLite database.

        Caches the result after the first call; subsequent calls are free.

        Returns:
            Schema dict compatible with ``SchemaLinker.link(target_schema=...)``.
        """
        if self._schema is None:
            self._schema = self._extractor.extract_from_database(self._path)
        return self._schema

    # ------------------------------------------------------------------
    # Extra helpers
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        """Absolute path to the SQLite file."""
        return self._path


def get_adapter(path: "str | Path") -> DatabaseAdapter:
    """Factory function: return the correct adapter for the given database path.

    Currently always returns a :class:`SQLiteAdapter` for SQLite files.
    In the future this will dispatch on the path scheme (``postgresql://``, etc.).

    Args:
        path: Path (or URI) to the database.

    Returns:
        A :class:`DatabaseAdapter` subclass instance.

    Raises:
        ValueError: If the path extension is not supported.
    """
    p = Path(path)
    if p.suffix.lower() in _SQLITE_EXTENSIONS:
        return SQLiteAdapter(p)
    raise ValueError(
        f"No adapter available for extension '{p.suffix}'. "
        f"Supported SQLite extensions: {sorted(_SQLITE_EXTENSIONS)}"
    )
