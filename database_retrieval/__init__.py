"""Database retrieval and schema extraction module.

Provides two operational modes:

**Mode 1 — Spider Benchmark Mode** (unchanged):
    - ``SchemaExtractor``: Extract structured schema from any SQLite database.
    - ``CatalogBuilder``: Build and persist the 166-database Spider catalog.
    - ``DatabaseRetriever``: TF-IDF retrieval over the Spider catalog.

**Mode 2 — Dynamic User Database Mode** (new):
    - ``load_database``: Validate and load any user-supplied SQLite file.
    - ``ActiveDatabase``: Wrapper around a validated DB + its schema.
    - ``DatabaseAdapter`` / ``SQLiteAdapter``: Extensible adapter layer.
    - ``get_adapter``: Factory returning the appropriate adapter for a path.
"""

from .schema_extractor import SchemaExtractor
from .catalog_builder import CatalogBuilder
from .retriever import DatabaseRetriever

# --- Dynamic User Database Mode (Mode 2) ---
from .active_database import ActiveDatabase
from .loader import load_database
from .adapter import DatabaseAdapter, SQLiteAdapter, get_adapter
from .cache_manager import get_or_create_database_cache, get_cache_info, clear_database_cache, find_sqlite_database

__all__ = [
    # Mode 1 — Spider Benchmark
    "SchemaExtractor",
    "CatalogBuilder",
    "DatabaseRetriever",
    # Mode 2 — Dynamic User Database
    "ActiveDatabase",
    "load_database",
    "DatabaseAdapter",
    "SQLiteAdapter",
    "get_adapter",
    "get_or_create_database_cache",
    "get_cache_info",
    "clear_database_cache",
    "find_sqlite_database",
]
