"""Automated Tests for SchemaExtractor.

Validates schema extraction on actual Spider databases including:
- Table names and column types
- Single and composite primary keys
- Single and composite foreign keys
- Relational mapping
- Exclusion of SQLite internal tables
- JSON serialization
"""

import json
import os
import unittest
from pathlib import Path

from database_retrieval.schema_extractor import SchemaExtractor


class TestSchemaExtractor(unittest.TestCase):
    """Test suite for SchemaExtractor against actual Spider databases."""

    @classmethod
    def setUpClass(cls):
        # Resolve databases directory
        cls.workspace_root = Path(__file__).parent.parent.resolve()
        cls.databases_dir = cls.workspace_root / "databases"
        cls.extractor = SchemaExtractor(databases_dir=cls.databases_dir)

    def test_total_database_count(self):
        """Verify that all 166 Spider databases are present."""
        db_dirs = [d for d in self.databases_dir.iterdir() if d.is_dir()]
        self.assertEqual(len(db_dirs), 166, f"Expected 166 databases, found {len(db_dirs)}")

    def test_exclude_internal_tables(self):
        """Verify that internal SQLite tables (sqlite_%) are strictly excluded."""
        # Test on a database known to have sqlite_sequence or similar
        metadata = self.extractor.extract_by_name("academic")
        table_names = [t["table_name"] for t in metadata["tables"]]
        for name in table_names:
            self.assertFalse(name.startswith("sqlite_"), f"Internal table {name} was not excluded!")

    def test_musical_schema(self):
        """Verify schema extraction for 'musical' database."""
        metadata = self.extractor.extract_by_name("musical")
        self.assertEqual(metadata["database_name"], "musical")
        self.assertEqual(metadata["total_tables"], 2)

        tables_by_name = {t["table_name"]: t for t in metadata["tables"]}
        self.assertIn("musical", tables_by_name)
        self.assertIn("actor", tables_by_name)

        # Check musical table
        musical_tbl = tables_by_name["musical"]
        self.assertEqual(musical_tbl["primary_keys"], ["Musical_ID"])
        musical_cols = {c["name"]: c["type"] for c in musical_tbl["columns"]}
        self.assertIn("Musical_ID", musical_cols)
        self.assertIn("Name", musical_cols)
        self.assertIn("Year", musical_cols)

        # Check actor table
        actor_tbl = tables_by_name["actor"]
        self.assertEqual(actor_tbl["primary_keys"], ["Actor_ID"])
        self.assertEqual(len(actor_tbl["foreign_keys"]), 1)

        # Check foreign key defined in Spider DDL
        fk = actor_tbl["foreign_keys"][0]
        self.assertEqual(fk["from_column"], "Musical_ID")
        self.assertEqual(fk["to_table"], "actor")
        self.assertEqual(fk["to_column"], "Actor_ID")
        self.assertFalse(fk["is_composite"])

    def test_academic_schema(self):
        """Verify schema extraction for 'academic' database."""
        metadata = self.extractor.extract_by_name("academic")
        self.assertEqual(metadata["total_tables"], 15)

        tables_by_name = {t["table_name"]: t for t in metadata["tables"]}

        # Check composite primary keys
        self.assertTrue(tables_by_name["writes"]["is_composite_pk"])
        self.assertEqual(tables_by_name["writes"]["primary_keys"], ["aid", "pid"])

        self.assertTrue(tables_by_name["domain_author"]["is_composite_pk"])
        self.assertEqual(tables_by_name["domain_author"]["primary_keys"], ["did", "aid"])

        # Check relationships count
        self.assertEqual(len(metadata["relationships"]), 18)

        # Check specific relationship
        cite_rels = [
            r for r in metadata["relationships"]
            if r["source_table"] == "cite" and r["target_table"] == "publication"
        ]
        self.assertEqual(len(cite_rels), 2)

    def test_activity_1_schema(self):
        """Verify schema extraction for 'activity_1' database."""
        metadata = self.extractor.extract_by_name("activity_1")
        self.assertEqual(metadata["total_tables"], 5)

        tables_by_name = {t["table_name"]: t for t in metadata["tables"]}
        self.assertIn("Activity", tables_by_name)
        self.assertIn("Student", tables_by_name)
        self.assertIn("Faculty", tables_by_name)
        self.assertIn("Participates_in", tables_by_name)
        self.assertIn("Faculty_Participates_in", tables_by_name)

        # Primary keys
        self.assertEqual(tables_by_name["Activity"]["primary_keys"], ["actid"])
        self.assertEqual(tables_by_name["Student"]["primary_keys"], ["StuID"])
        self.assertEqual(tables_by_name["Faculty"]["primary_keys"], ["FacID"])

        # Foreign keys in Participates_in
        part_fks = tables_by_name["Participates_in"]["foreign_keys"]
        self.assertEqual(len(part_fks), 2)
        fk_targets = {fk["to_table"]: (fk["from_column"], fk["to_column"]) for fk in part_fks}
        self.assertEqual(fk_targets["Activity"], ("actid", "actid"))
        self.assertEqual(fk_targets["Student"], ("stuid", "StuID"))

    def test_composite_foreign_keys_college_2(self):
        """Verify composite foreign keys in 'college_2' database."""
        metadata = self.extractor.extract_by_name("college_2")
        tables_by_name = {t["table_name"]: t for t in metadata["tables"]}

        teaches_fks = tables_by_name["teaches"]["foreign_keys"]
        # teaches has 2 FK constraints: 1 single (ID -> instructor.ID) and 1 composite (4 columns -> section)
        composite_fks = [fk for fk in teaches_fks if fk["is_composite"]]
        self.assertEqual(len(composite_fks), 1)

        cfk = composite_fks[0]
        self.assertEqual(cfk["to_table"], "section")
        self.assertEqual(cfk["from_columns"], ["course_id", "sec_id", "semester", "year"])
        self.assertEqual(cfk["to_columns"], ["course_id", "sec_id", "semester", "year"])

    def test_all_166_databases_extraction(self):
        """Verify that every one of the 166 databases can be parsed without error."""
        db_dirs = sorted([d.name for d in self.databases_dir.iterdir() if d.is_dir()])
        self.assertEqual(len(db_dirs), 166)
        
        failed = []
        for db_name in db_dirs:
            try:
                meta = self.extractor.extract_by_name(db_name)
                self.assertGreater(meta["total_tables"], 0, f"Database {db_name} has 0 tables")
            except Exception as e:
                failed.append((db_name, str(e)))

        self.assertEqual(len(failed), 0, f"Failed on {len(failed)} databases: {failed}")

    def test_json_serialization(self):
        """Verify that extracted schema serializes and parses properly as JSON."""
        metadata = self.extractor.extract_by_name("musical")
        json_str = self.extractor.to_json(metadata)
        parsed = json.loads(json_str)

        self.assertEqual(parsed["database_name"], "musical")
        self.assertIn("tables", parsed)
        self.assertIn("relationships", parsed)
        self.assertIsInstance(parsed["tables"], list)
        self.assertIsInstance(parsed["relationships"], list)


if __name__ == "__main__":
    unittest.main()
