"""JSON cache manager for SQLite database metadata, schema, and retrieval context.

The cache is keyed by the SHA-256 hash of the SQLite file. This means:
- the same database file reuses its cache;
- a changed database automatically gets a new cache;
- cached data never replaces or modifies the source SQLite file.

Cache layout:

    cache/
      database_cache/
        <sha256>/
          metadata.json
          schema.json
          schema_text.json
          retrieval.json

No table rows are cached.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

from .schema_extractor import SchemaExtractor


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = PROJECT_ROOT / "cache" / "database_cache"

CACHE_FILES = (
    "metadata.json",
    "schema.json",
    "schema_text.json",
    "retrieval.json",
)


def sha256_file(path: Union[str, Path], chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of a file."""
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def cache_dir_for(path: Union[str, Path], file_hash: Optional[str] = None) -> Path:
    """Return the cache directory for a SQLite file."""
    path = Path(path).resolve()
    digest = file_hash or sha256_file(path)
    return CACHE_ROOT / digest


def build_schema_text(meta: Dict[str, Any]) -> str:
    """Build the same tokenisation-friendly schema text used by Spider retrieval."""
    parts = []

    db_name_clean = meta["database_name"].replace("_", " ")
    parts.extend([db_name_clean, db_name_clean])

    table_names_clean = [
        t["table_name"].replace("_", " ") for t in meta.get("tables", [])
    ]
    parts.append(" ".join(table_names_clean))

    for table in meta.get("tables", []):
        table_name = table["table_name"].replace("_", " ")
        parts.append(table_name)

        for pk in table.get("primary_keys", []):
            parts.append(
                f"{table_name} {pk.replace('_', ' ')} primary key"
            )

        for column in table.get("columns", []):
            column_name = column["name"].replace("_", " ")
            column_type = column.get("type", "TEXT")
            parts.append(f"{table_name} {column_name} {column_type}")

        for fk in table.get("foreign_keys", []):
            from_col = fk["from_column"].replace("_", " ")
            to_table = fk["to_table"].replace("_", " ")
            to_col = fk["to_column"].replace("_", " ")
            parts.append(
                f"{table_name} {from_col} references {to_table} {to_col}"
            )

    for rel in meta.get("relationships", []):
        src_table = rel["source_table"].replace("_", " ")
        src_col = rel["source_column"].replace("_", " ")
        tgt_table = rel["target_table"].replace("_", " ")
        tgt_col = rel["target_column"].replace("_", " ")
        parts.append(f"{src_table} {src_col} {tgt_table} {tgt_col}")

    return " ".join(parts).lower()


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON atomically so interrupted writes do not leave broken cache files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _cache_is_valid(cache_dir: Path, file_hash: str) -> bool:
    """Check that all cache files exist and belong to the current DB hash."""
    if not all((cache_dir / name).is_file() for name in CACHE_FILES):
        return False
    try:
        metadata = _load_json(cache_dir / "metadata.json")
        return metadata.get("sha256") == file_hash
    except (OSError, ValueError, json.JSONDecodeError):
        return False



def find_sqlite_database(
    databases_dir: Union[str, Path],
    database_name: str,
) -> Path:
    """Resolve a Spider-style database name to its SQLite file without extracting schema."""
    base = Path(databases_dir).resolve()
    candidates = [
        base / database_name / f"{database_name}.sqlite",
        base / database_name / f"{database_name}.db",
        base / database_name / f"{database_name}.sqlite3",
        base / f"{database_name}.sqlite",
        base / f"{database_name}.db",
        base / f"{database_name}.sqlite3",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        f"Could not find SQLite file for database '{database_name}' in {base}."
    )

def get_or_create_database_cache(
    db_path: Union[str, Path],
    *,
    force_refresh: bool = False,
    database_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Load a database cache or create it on first use.

    Returns a dict containing:
        metadata, schema, schema_text, retrieval, cache_hit, cache_dir
    """
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Database file not found: {path}")

    file_hash = sha256_file(path)
    cache_dir = cache_dir_for(path, file_hash)

    if not force_refresh and _cache_is_valid(cache_dir, file_hash):
        return {
            "metadata": _load_json(cache_dir / "metadata.json"),
            "schema": _load_json(cache_dir / "schema.json"),
            "schema_text": _load_json(cache_dir / "schema_text.json")["schema_text"],
            "retrieval": _load_json(cache_dir / "retrieval.json"),
            "cache_hit": True,
            "cache_dir": str(cache_dir),
        }

    extractor = SchemaExtractor()
    schema = extractor.extract_from_database(path)
    schema_text = build_schema_text(schema)

    all_tables = [t["table_name"] for t in schema.get("tables", [])]
    all_columns = [
        f"{table['table_name']}.{column['name']}"
        for table in schema.get("tables", [])
        for column in table.get("columns", [])
    ]

    metadata = {
        "cache_version": 1,
        "cache_key": file_hash,
        "sha256": file_hash,
        "database_name": database_name or schema.get("database_name", path.stem),
        "database_type": "sqlite",
        "source_filename": path.name,
        "source_path": str(path),
        "size_bytes": path.stat().st_size,
        "modified_ns": path.stat().st_mtime_ns,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "contains_rows": False,
    }

    retrieval = {
        "database_name": schema.get("database_name", path.stem),
        "total_tables": schema.get("total_tables", 0),
        "all_tables": all_tables,
        "all_columns": all_columns,
        "relationships": schema.get("relationships", []),
        "schema_text": schema_text,
    }

    cache_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(cache_dir / "metadata.json", metadata)
    _atomic_write_json(cache_dir / "schema.json", schema)
    _atomic_write_json(
        cache_dir / "schema_text.json",
        {
            "database_name": schema.get("database_name", path.stem),
            "schema_text": schema_text,
        },
    )
    _atomic_write_json(cache_dir / "retrieval.json", retrieval)

    return {
        "metadata": metadata,
        "schema": schema,
        "schema_text": schema_text,
        "retrieval": retrieval,
        "cache_hit": False,
        "cache_dir": str(cache_dir),
    }


def get_cache_info(db_path: Union[str, Path]) -> Dict[str, Any]:
    """Return inspectable cache status without creating a cache."""
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Database file not found: {path}")

    file_hash = sha256_file(path)
    cache_dir = cache_dir_for(path, file_hash)
    files = {
        name: {
            "exists": (cache_dir / name).is_file(),
            "path": str(cache_dir / name),
        }
        for name in CACHE_FILES
    }

    return {
        "database": str(path),
        "sha256": file_hash,
        "cache_dir": str(cache_dir),
        "cache_exists": _cache_is_valid(cache_dir, file_hash),
        "files": files,
    }


def clear_database_cache(db_path: Union[str, Path]) -> bool:
    """Delete the cache for one database. The source DB is untouched."""
    import shutil

    path = Path(db_path).resolve()
    file_hash = sha256_file(path)
    cache_dir = cache_dir_for(path, file_hash)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        return True
    return False
