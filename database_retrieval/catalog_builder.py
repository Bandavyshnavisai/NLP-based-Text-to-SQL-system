"""Database Catalog Builder.

Generates and persists a searchable catalog of all Spider database schemas
by combining schema metadata extracted from each SQLite database with a
human-readable textual schema representation suitable for TF-IDF indexing.

The catalog does NOT store raw database contents (rows, data values).
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .schema_extractor import SchemaExtractor
from .cache_manager import get_or_create_database_cache, build_schema_text, find_sqlite_database


_DEFAULT_CATALOG_PATH = Path(__file__).parent.parent / "database_retrieval" / "spider_catalog.json"


class CatalogBuilder:
    """Builds and saves the Spider schema catalog from local SQLite databases.

    The catalog is a JSON file containing one entry per database with:
    - database_name
    - tables (with columns, types, PKs, FKs)
    - relationships
    - schema_text: a flat, tokenisation-friendly textual representation
    """

    def __init__(
        self,
        databases_dir: Optional[Union[str, Path]] = None,
        catalog_path: Optional[Union[str, Path]] = None,
    ):
        if databases_dir is not None:
            self.databases_dir = Path(databases_dir).resolve()
        else:
            self.databases_dir = (Path(__file__).parent.parent / "databases").resolve()

        if catalog_path is not None:
            self.catalog_path = Path(catalog_path).resolve()
        else:
            self.catalog_path = (Path(__file__).parent / "spider_catalog.json").resolve()

        self.extractor = SchemaExtractor(databases_dir=self.databases_dir)

    @staticmethod
    def _build_schema_text(meta: Dict[str, Any]) -> str:
        """Backward-compatible wrapper around the shared cache implementation."""
        return build_schema_text(meta)

    def _build_entry(self, db_name: str) -> Optional[Dict[str, Any]]:
        """Build a catalog entry, reusing the per-database JSON cache."""
        try:
            # Resolve the file path without opening/extracting its schema.
            # This is important: a cache hit must not rerun schema extraction.
            db_path = find_sqlite_database(self.databases_dir, db_name)
            cached = get_or_create_database_cache(
                db_path,
                database_name=db_name,
            )
            schema = cached["schema"]
            retrieval = cached["retrieval"]
        except Exception:
            return None

        return {
            "database_name": schema["database_name"],
            "database_path": schema.get("database_path", str(db_path)),
            "total_tables": schema["total_tables"],
            "tables": schema["tables"],
            "relationships": schema["relationships"],
            "all_tables": retrieval["all_tables"],
            "all_columns": retrieval["all_columns"],
            "schema_text": retrieval["schema_text"],
            "cache_key": cached["metadata"]["sha256"],
            "cache_dir": cached["cache_dir"],
        }

    def build_catalog(self, verbose: bool = True) -> List[Dict[str, Any]]:
        """Build the full catalog by iterating over all database folders.

        Args:
            verbose: If True, print progress to stdout.

        Returns:
            List of catalog entry dicts.
        """
        db_dirs = sorted(
            [d.name for d in self.databases_dir.iterdir() if d.is_dir()]
        )

        catalog: List[Dict[str, Any]] = []
        failed: List[str] = []

        if verbose:
            print(f"Building catalog from {len(db_dirs)} databases in {self.databases_dir}...")

        for i, db_name in enumerate(db_dirs, 1):
            entry = self._build_entry(db_name)
            if entry is not None:
                catalog.append(entry)
                if verbose:
                    print(f"  [{i:3d}/{len(db_dirs)}] {db_name}: {entry['total_tables']} tables")
            else:
                failed.append(db_name)
                if verbose:
                    print(f"  [{i:3d}/{len(db_dirs)}] FAILED: {db_name}")

        if verbose:
            print(f"\nCatalog built: {len(catalog)} entries ({len(failed)} failed)")
            if failed:
                print(f"  Failed databases: {failed}")

        return catalog

    def build_and_save(self, verbose: bool = True) -> List[Dict[str, Any]]:
        """Build and persist the catalog to disk.

        Args:
            verbose: If True, print progress.

        Returns:
            List of catalog entry dicts.
        """
        catalog = self.build_catalog(verbose=verbose)

        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.catalog_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)

        if verbose:
            size_mb = self.catalog_path.stat().st_size / (1024 * 1024)
            print(f"Catalog saved to: {self.catalog_path} ({size_mb:.2f} MB)")

        return catalog

    def load_catalog(self) -> List[Dict[str, Any]]:
        """Load the catalog from disk.

        Returns:
            List of catalog entry dicts.

        Raises:
            FileNotFoundError: If the catalog file does not exist.
        """
        if not self.catalog_path.exists():
            raise FileNotFoundError(
                f"Catalog not found at {self.catalog_path}. "
                "Run build_and_save() first."
            )
        with open(self.catalog_path, "r", encoding="utf-8") as f:
            return json.load(f)
