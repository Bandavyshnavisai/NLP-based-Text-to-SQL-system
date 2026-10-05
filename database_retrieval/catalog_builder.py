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
        """Build a flat, human-readable textual representation of a database schema.

        The representation is optimised for TF-IDF tokenisation:
        - database name is repeated for boost
        - table names listed
        - each column prefixed with its table name
        - PK/FK annotations included
        - relationship source→target mentioned explicitly

        Args:
            meta: Schema metadata dict from SchemaExtractor.

        Returns:
            A plain-text string representing the full schema.
        """
        parts: List[str] = []

        db_name_clean = meta["database_name"].replace("_", " ")
        # Repeat DB name to give it higher TF weight
        parts.append(db_name_clean)
        parts.append(db_name_clean)

        table_names_clean = [
            t["table_name"].replace("_", " ") for t in meta["tables"]
        ]
        parts.append(" ".join(table_names_clean))

        for tbl in meta["tables"]:
            tbl_name = tbl["table_name"].replace("_", " ")
            # Table name itself
            parts.append(tbl_name)

            # Primary key columns
            for pk in tbl.get("primary_keys", []):
                pk_clean = pk.replace("_", " ")
                parts.append(f"{tbl_name} {pk_clean} primary key")

            # Each column: table_name column_name column_type
            for col in tbl["columns"]:
                col_clean = col["name"].replace("_", " ")
                col_type = col["type"]
                parts.append(f"{tbl_name} {col_clean} {col_type}")

            # Foreign key relationships expressed as prose
            for fk in tbl.get("foreign_keys", []):
                from_col = fk["from_column"].replace("_", " ")
                to_tbl = fk["to_table"].replace("_", " ")
                to_col = fk["to_column"].replace("_", " ")
                parts.append(
                    f"{tbl_name} {from_col} references {to_tbl} {to_col}"
                )

        # Explicit relationship phrases
        for rel in meta.get("relationships", []):
            src_tbl = rel["source_table"].replace("_", " ")
            src_col = rel["source_column"].replace("_", " ")
            tgt_tbl = rel["target_table"].replace("_", " ")
            tgt_col = rel["target_column"].replace("_", " ")
            parts.append(f"{src_tbl} {src_col} {tgt_tbl} {tgt_col}")

        return " ".join(parts).lower()

    def _build_entry(self, db_name: str) -> Optional[Dict[str, Any]]:
        """Build a single catalog entry for a database.

        Args:
            db_name: Name of the database folder.

        Returns:
            Catalog entry dict, or None if extraction fails.
        """
        try:
            meta = self.extractor.extract_by_name(db_name)
        except Exception as e:
            return None

        schema_text = self._build_schema_text(meta)

        # Collect all unique table names and column names for easy matching
        all_tables = [t["table_name"] for t in meta["tables"]]
        all_columns = []
        for t in meta["tables"]:
            for col in t["columns"]:
                all_columns.append(f"{t['table_name']}.{col['name']}")

        return {
            "database_name": meta["database_name"],
            "total_tables": meta["total_tables"],
            "tables": meta["tables"],
            "relationships": meta["relationships"],
            "all_tables": all_tables,
            "all_columns": all_columns,
            "schema_text": schema_text,
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
