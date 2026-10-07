from pathlib import Path
import sqlite3
import re
import uuid

from database_retrieval.cache_manager import (
    get_cache_info,
    get_or_create_database_cache,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASES_DIR = BASE_DIR / "databases"
UPLOADS_DIR = DATABASES_DIR / "uploads"
DATABASES_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise ValueError("Invalid database identifier")
    return value


def resolve_database(database: str) -> Path:
    database = safe_id(database)
    candidates = [
        DATABASES_DIR / database,
        DATABASES_DIR / f"{database}.sqlite",
        DATABASES_DIR / f"{database}.db",
        DATABASES_DIR / f"{database}.sqlite3",
        UPLOADS_DIR / database,
    ]
    for p in candidates:
        if p.is_file() and p.resolve().parent in {
            DATABASES_DIR.resolve(),
            UPLOADS_DIR.resolve(),
        }:
            return p.resolve()
    raise FileNotFoundError(f"Database '{database}' was not found")


def validate_sqlite_file(path: Path) -> None:
    if path.stat().st_size < 100:
        raise ValueError("File is too small to be a valid SQLite database")
    with path.open("rb") as f:
        header = f.read(16)
    if header != b"SQLite format 3\x00":
        raise ValueError("Uploaded file is not a valid SQLite database")

    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        tables = con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
        if not tables:
            raise ValueError(
                "Database contains no user tables. At least one table is required."
            )
    finally:
        con.close()


def save_uploaded_database(filename: str, data: bytes) -> dict:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Database exceeds the 100 MB upload limit")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Only .db, .sqlite, and .sqlite3 files are supported")

    stem = (
        re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(filename).stem).strip("._")
        or "database"
    )
    db_id = f"{stem}_{uuid.uuid4().hex[:8]}"
    dest = UPLOADS_DIR / f"{db_id}{ext}"
    dest.write_bytes(data)

    try:
        validate_sqlite_file(dest)

        # First-time processing happens at upload time. This creates the JSON
        # cache once, so normal /query calls only read the cached context.
        cache = get_or_create_database_cache(
            dest,
            database_name=db_id,
        )
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    return {
        "id": db_id,
        "name": stem,
        "filename": dest.name,
        "uploaded": True,
        "size_bytes": len(data),
        "cache": {
            "created": not cache["cache_hit"],
            "cache_hit": cache["cache_hit"],
            "cache_dir": cache["cache_dir"],
            "sha256": cache["metadata"]["sha256"],
        },
    }


def list_databases() -> list[dict]:
    items = []

    for p in sorted(DATABASES_DIR.iterdir()):
        if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS:
            items.append(
                {
                    "id": p.stem,
                    "name": p.stem,
                    "filename": p.name,
                    "uploaded": False,
                    "size_bytes": p.stat().st_size,
                }
            )

    if UPLOADS_DIR.exists():
        for p in sorted(UPLOADS_DIR.iterdir()):
            if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS:
                items.append(
                    {
                        "id": p.stem,
                        "name": p.stem,
                        "filename": p.name,
                        "uploaded": True,
                        "size_bytes": p.stat().st_size,
                    }
                )

    return items


def get_database_cache(database: str, force_refresh: bool = False) -> dict:
    """Return cached metadata/schema/schema-text/retrieval context."""
    path = resolve_database(database)
    return get_or_create_database_cache(
        path,
        force_refresh=force_refresh,
        database_name=Path(database).stem,
    )


def get_cache_status(database: str) -> dict:
    """Return cache paths/status without creating a cache."""
    path = resolve_database(database)
    return get_cache_info(path)


def get_schema(database: str) -> dict:
    """Return the schema from JSON cache, creating it only if necessary."""
    return get_database_cache(database)["schema"]


def execute_read_only(database: str, sql: str, max_rows: int = 500) -> dict:
    path = resolve_database(database)
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        SQLITE_DENY = 1
        SQLITE_OK = 0
        SQLITE_READ = 20
        SQLITE_SELECT = 21
        allowed = {SQLITE_READ, SQLITE_SELECT}

        def authorizer(action, arg1, arg2, dbname, source):
            return SQLITE_OK if action in allowed else SQLITE_DENY

        con.set_authorizer(authorizer)
        cur = con.execute(sql)
        rows = cur.fetchmany(max_rows)
        columns = [d[0] for d in cur.description] if cur.description else []
        return {
            "success": True,
            "columns": columns,
            "rows": [dict(r) for r in rows],
            "row_count": len(rows),
        }
    finally:
        con.close()
