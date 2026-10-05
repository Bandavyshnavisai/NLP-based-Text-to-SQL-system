"""Schema Extractor for SQLite Databases.

Extracts structured relational schema metadata from SQLite database files,
including database names, tables, columns, data types, single and composite
primary keys, single and composite foreign keys, and inter-table relationships.
"""

import argparse
import json
import os
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class SchemaExtractor:
    """Extracts relational schema metadata from SQLite databases."""

    def __init__(self, databases_dir: Optional[Union[str, Path]] = None):
        """Initialize the SchemaExtractor.

        Args:
            databases_dir: Optional base directory containing database folders.
        """
        if databases_dir is not None:
            self.databases_dir = Path(databases_dir).resolve()
        else:
            # Default to ../databases relative to this module
            self.databases_dir = (Path(__file__).parent.parent / "databases").resolve()

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        """Escape and double-quote SQLite identifiers to handle spaces/keywords."""
        escaped = identifier.replace('"', '""')
        return f'"{escaped}"'

    def extract_from_database(self, db_path: Union[str, Path]) -> Dict[str, Any]:
        """Extract complete structured schema metadata from a SQLite database file.

        Args:
            db_path: Path to the SQLite database file (.sqlite or .db).

        Returns:
            Dict containing database name, tables, column details, primary keys,
            foreign keys, and table relationships.
        """
        db_path = Path(db_path).resolve()
        if not db_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")

        db_name = db_path.stem

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        try:
            # Retrieve all non-system user tables (strictly exclude sqlite_% internal tables)
            cursor.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name;"
            )
            table_names = [row[0] for row in cursor.fetchall()]

            tables_metadata: List[Dict[str, Any]] = []
            all_relationships: List[Dict[str, Any]] = []

            for table_name in table_names:
                quoted_table = self._quote_identifier(table_name)

                # Column information: cid, name, type, notnull, dflt_value, pk
                cursor.execute(f"PRAGMA table_info({quoted_table});")
                columns_info = cursor.fetchall()

                columns: List[Dict[str, Any]] = []
                pk_candidates: List[tuple[str, int]] = []

                for col in columns_info:
                    col_cid, col_name, col_type, notnull, dflt_value, pk = col
                    is_pk = bool(pk > 0)
                    if is_pk:
                        pk_candidates.append((col_name, pk))

                    columns.append({
                        "name": col_name,
                        "type": (col_type.upper().strip() if col_type else "TEXT"),
                        "primary_key": is_pk,
                        "not_null": bool(notnull == 1),
                        "default_value": dflt_value
                    })

                # Sort composite primary keys by their key sequence index
                pk_candidates.sort(key=lambda x: x[1])
                primary_keys = [col_name for col_name, _ in pk_candidates]

                # Foreign key information: id, seq, table, from, to, on_update, on_delete, match
                cursor.execute(f"PRAGMA foreign_key_list({quoted_table});")
                fks_info = cursor.fetchall()

                # Group by constraint id to correctly handle composite foreign keys
                fk_groups: Dict[int, List[Any]] = defaultdict(list)
                for fk in fks_info:
                    fk_id = fk[0]
                    fk_groups[fk_id].append(fk)

                foreign_keys: List[Dict[str, Any]] = []
                for fk_id, rows in sorted(fk_groups.items(), key=lambda x: x[0]):
                    # Sort by seq to guarantee column ordering in composite foreign keys
                    rows.sort(key=lambda r: r[1])
                    
                    target_table = rows[0][2]
                    from_cols = [r[3] for r in rows]
                    to_cols = [r[4] for r in rows]
                    on_upd = rows[0][5]
                    on_del = rows[0][6]
                    is_composite = len(rows) > 1

                    fk_dict: Dict[str, Any] = {
                        "constraint_id": fk_id,
                        "from_column": ", ".join(from_cols) if is_composite else from_cols[0],
                        "to_table": target_table,
                        "to_column": ", ".join(to_cols) if is_composite else to_cols[0],
                        "from_columns": from_cols,
                        "to_columns": to_cols,
                        "is_composite": is_composite,
                        "on_update": on_upd,
                        "on_delete": on_del
                    }
                    foreign_keys.append(fk_dict)

                    rel_dict: Dict[str, Any] = {
                        "source_table": table_name,
                        "source_column": ", ".join(from_cols) if is_composite else from_cols[0],
                        "target_table": target_table,
                        "target_column": ", ".join(to_cols) if is_composite else to_cols[0],
                        "source_columns": from_cols,
                        "target_columns": to_cols,
                        "is_composite": is_composite
                    }
                    all_relationships.append(rel_dict)

                tables_metadata.append({
                    "table_name": table_name,
                    "columns": columns,
                    "primary_keys": primary_keys,
                    "is_composite_pk": len(primary_keys) > 1,
                    "foreign_keys": foreign_keys
                })

            schema_metadata: Dict[str, Any] = {
                "database_name": db_name,
                "database_path": str(db_path),
                "total_tables": len(tables_metadata),
                "tables": tables_metadata,
                "relationships": all_relationships
            }

            return schema_metadata

        finally:
            conn.close()

    def extract_by_name(self, db_name: str) -> Dict[str, Any]:
        """Extract schema for a database by its folder/name within the databases directory.

        Args:
            db_name: Name of the database folder / SQLite database.

        Returns:
            Dict containing the extracted schema metadata.
        """
        candidates = [
            self.databases_dir / db_name / f"{db_name}.sqlite",
            self.databases_dir / db_name / f"{db_name}.db",
            self.databases_dir / f"{db_name}.sqlite",
            self.databases_dir / f"{db_name}.db"
        ]

        for cand in candidates:
            if cand.exists():
                return self.extract_from_database(cand)

        raise FileNotFoundError(
            f"Could not find SQLite file for database '{db_name}' in {self.databases_dir}."
        )

    def extract_and_save(
        self,
        db_source: Union[str, Path],
        output_json_path: Union[str, Path]
    ) -> Dict[str, Any]:
        """Extract schema and save it directly to a JSON file.

        Args:
            db_source: Database file path or database name.
            output_json_path: Destination JSON file path.

        Returns:
            Dict containing the extracted schema metadata.
        """
        output_path = Path(output_json_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if Path(db_source).exists():
            metadata = self.extract_from_database(db_source)
        else:
            metadata = self.extract_by_name(str(db_source))

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        return metadata

    def to_json(self, schema_dict: Dict[str, Any], indent: int = 2) -> str:
        """Serialize schema metadata dictionary to a JSON formatted string."""
        return json.dumps(schema_dict, indent=indent, ensure_ascii=False)


def run_tests_on_sample_databases(
    sample_names: Optional[List[str]] = None,
    output_dir: Optional[Union[str, Path]] = None
) -> None:
    """Test schema extraction on sample Spider databases."""
    if sample_names is None:
        sample_names = ["musical", "academic", "activity_1", "college_2"]

    extractor = SchemaExtractor()
    print("=" * 70)
    print(f"Testing SchemaExtractor on {len(sample_names)} Spider databases: {sample_names}")
    print("=" * 70)

    for db_name in sample_names:
        print(f"\n[+] Extracting schema for database: '{db_name}'...")
        try:
            metadata = extractor.extract_by_name(db_name)
            print(f"    - Database Name : {metadata['database_name']}")
            print(f"    - Database Path : {metadata['database_path']}")
            print(f"    - Total Tables  : {metadata['total_tables']}")
            print("    - Tables Summary:")
            for tbl in metadata["tables"]:
                pk_type = "Composite PK" if tbl["is_composite_pk"] else "PK"
                pk_str = ", ".join(tbl["primary_keys"]) if tbl["primary_keys"] else "None"
                print(f"      * {tbl['table_name']}: {len(tbl['columns'])} columns ({pk_type}: [{pk_str}])")
                for col in tbl["columns"]:
                    pk_marker = " [PK]" if col["primary_key"] else ""
                    print(f"          - {col['name']} ({col['type']}){pk_marker}")
                if tbl["foreign_keys"]:
                    for fk in tbl["foreign_keys"]:
                        comp_marker = " [Composite FK]" if fk["is_composite"] else ""
                        print(f"          -> FK{comp_marker}: {tbl['table_name']}.({fk['from_column']}) -> {fk['to_table']}.({fk['to_column']})")

            print(f"    - Relationships count: {len(metadata['relationships'])}")
            for rel in metadata["relationships"]:
                comp_marker = " [Composite]" if rel["is_composite"] else ""
                print(f"      * {rel['source_table']}.({rel['source_column']}) -> {rel['target_table']}.({rel['target_column']}){comp_marker}")

            if output_dir is not None:
                out_path = Path(output_dir) / f"{db_name}_schema.json"
                extractor.extract_and_save(db_name, out_path)
                print(f"    - Saved schema JSON to: {out_path}")

        except Exception as e:
            print(f"    [!] Error extracting '{db_name}': {e}")
            raise

    print("\n" + "=" * 70)
    print("Schema extraction tests completed successfully!")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Extract schema metadata from SQLite databases.")
    parser.add_argument("--db-name", type=str, help="Name of database folder/file in databases directory.")
    parser.add_argument("--db-path", type=str, help="Direct path to SQLite database file.")
    parser.add_argument("--output", "-o", type=str, help="Path to save output JSON schema.")
    parser.add_argument("--test", action="store_true", help="Run extraction test on sample Spider databases.")
    parser.add_argument("--databases-dir", type=str, default=None, help="Base directory containing databases.")

    args = parser.parse_args()

    extractor = SchemaExtractor(databases_dir=args.databases_dir)

    if args.test or (not args.db_name and not args.db_path):
        run_tests_on_sample_databases()
        return

    if args.db_path:
        metadata = extractor.extract_from_database(args.db_path)
    elif args.db_name:
        metadata = extractor.extract_by_name(args.db_name)
    else:
        parser.print_help()
        return

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(extractor.to_json(metadata))
        print(f"Schema metadata saved to {out_path}")
    else:
        print(extractor.to_json(metadata))


if __name__ == "__main__":
    main()
