"""Integration test: validate that DatabaseRetriever output can be consumed
by a downstream component (Member 2 schema linking).

This test does NOT implement schema linking. It only verifies that the
retrieval output contract is fulfilled correctly:
- retrieve() returns a list of result dicts.
- The top result's database name is a valid key in the catalog.
- The full schema (tables, columns, PKs, FKs, relationships) can be
  obtained for the top-ranked database — ready for Member 2 to consume.

This test is the documented integration point between Member 1 and Member 2.
"""

import unittest
from pathlib import Path
from typing import Any, Dict, List


class TestMember1ToMember2Interface(unittest.TestCase):
    """
    Integration tests that validate the handoff contract from
    Member 1 (retrieval) to Member 2 (schema linking).
    """

    @classmethod
    def setUpClass(cls):
        from database_retrieval.retriever import DatabaseRetriever
        from database_retrieval.catalog_builder import CatalogBuilder

        workspace = Path(__file__).parent.parent.resolve()
        catalog_path = workspace / "database_retrieval" / "spider_catalog.json"
        index_path = workspace / "database_retrieval" / "spider_tfidf_index.pkl"

        cls.retriever = DatabaseRetriever(
            catalog_path=catalog_path,
            index_path=index_path,
        )
        # Load index (auto-loads catalog as well)
        cls.retriever.load_index()
        if cls.retriever._catalog is None and catalog_path.exists():
            cls.retriever._catalog = cls.retriever._catalog_builder.load_catalog()

        # Build catalog lookup for downstream access (Member 2 pattern)
        cls.catalog_by_name: Dict[str, Any] = {
            e["database_name"]: e for e in cls.retriever._catalog
        }

    def _get_top_schema(self, question: str) -> Dict[str, Any]:
        """Simulate the Member 2 pattern: retrieve → pick top-1 → get schema."""
        results = self.retriever.retrieve(question, top_k=5)
        self.assertGreater(len(results), 0, "retrieve() returned no results")
        top_db_name = results[0]["database"]
        # Member 2 fetches full schema from the catalog
        schema = self.catalog_by_name[top_db_name]
        return results, schema

    # -----------------------------------------------------------------
    # Contract tests
    # -----------------------------------------------------------------

    def test_retrieve_output_contract(self):
        """Each result must expose all fields Member 2 depends on."""
        results = self.retriever.retrieve(
            "Find the name and capacity of the stadium with the most concerts.",
            top_k=5,
        )
        required_fields = {"rank", "database", "score", "matched_tables", "matched_columns"}
        for r in results:
            self.assertTrue(
                required_fields.issubset(r.keys()),
                f"Missing fields in result: {required_fields - r.keys()}"
            )
            self.assertIsInstance(r["rank"], int)
            self.assertIsInstance(r["database"], str)
            self.assertIsInstance(r["score"], float)
            self.assertIsInstance(r["matched_tables"], list)
            self.assertIsInstance(r["matched_columns"], list)

    def test_top1_schema_fully_accessible(self):
        """Member 2 must be able to get the full schema for the top-1 result."""
        results, schema = self._get_top_schema(
            "Find the name and capacity of the stadium with the most concerts."
        )
        # Schema must contain all keys Member 2 needs
        required_schema_keys = {
            "database_name", "total_tables", "tables",
            "relationships", "all_tables", "all_columns",
        }
        self.assertTrue(
            required_schema_keys.issubset(schema.keys()),
            f"Missing schema keys: {required_schema_keys - schema.keys()}"
        )

    def test_table_metadata_structure(self):
        """Each table in the schema must have columns, PKs and FKs accessible."""
        _, schema = self._get_top_schema("List all car models and their manufacturers.")
        for table in schema["tables"]:
            self.assertIn("table_name", table)
            self.assertIn("columns", table)
            self.assertIn("primary_keys", table)
            self.assertIn("foreign_keys", table)
            self.assertIn("is_composite_pk", table)
            for col in table["columns"]:
                self.assertIn("name", col)
                self.assertIn("type", col)
                self.assertIn("primary_key", col)
                self.assertIn("not_null", col)

    def test_relationships_accessible(self):
        """Relationships (FK graph) must be accessible for schema linking."""
        _, schema = self._get_top_schema("Which museums have been visited?")
        self.assertIn("relationships", schema)
        self.assertIsInstance(schema["relationships"], list)
        for rel in schema["relationships"]:
            self.assertIn("source_table", rel)
            self.assertIn("source_column", rel)
            self.assertIn("target_table", rel)
            self.assertIn("target_column", rel)

    def test_matched_tables_are_real_table_names(self):
        """matched_tables from retrieve() must correspond to actual table names in the schema."""
        results, schema = self._get_top_schema(
            "Find the name and capacity of the stadium with the most concerts."
        )
        all_tables_set = set(schema["all_tables"])
        for tbl in results[0]["matched_tables"]:
            self.assertIn(
                tbl, all_tables_set,
                f"matched_table '{tbl}' not in schema tables: {all_tables_set}"
            )

    def test_matched_columns_format(self):
        """matched_columns must follow 'TableName.ColumnName' format."""
        results = self.retriever.retrieve(
            "Find the name and capacity of the stadium with the most concerts.",
            top_k=1,
        )
        for col_ref in results[0]["matched_columns"]:
            self.assertIn(
                ".", col_ref,
                f"matched_column '{col_ref}' is not in 'Table.Column' format"
            )

    def test_schema_linking_entrypoint_pattern(self):
        """
        Demonstrate the full Member 1 → Member 2 handoff pattern in code.

        This is the integration point. Member 2 receives:
          - question (str)
          - top-ranked database name (str)
          - full schema dict (tables, columns, PKs, FKs, relationships)
          - matched_tables hint (List[str])
          - matched_columns hint (List[str])
        """
        question = "Find the name and capacity of the stadium with the most concerts."

        # --- Member 1 work ---
        results = self.retriever.retrieve(question, top_k=5)
        top_result = results[0]
        top_db_name: str = top_result["database"]
        similarity_score: float = top_result["score"]
        matched_tables: List[str] = top_result["matched_tables"]
        matched_columns: List[str] = top_result["matched_columns"]

        # Member 2 fetches full schema from catalog
        schema: Dict[str, Any] = self.catalog_by_name[top_db_name]

        # --- Verify Member 2 has everything it needs ---
        self.assertEqual(top_db_name, "concert_singer")
        self.assertGreater(similarity_score, 0)
        self.assertIn("stadium", matched_tables)
        self.assertIn("stadium.Capacity", matched_columns)

        # Member 2 can now iterate tables for schema linking
        tables_for_linking = {
            t["table_name"]: {
                "columns": [c["name"] for c in t["columns"]],
                "primary_keys": t["primary_keys"],
                "foreign_keys": t["foreign_keys"],
            }
            for t in schema["tables"]
        }
        self.assertIn("stadium", tables_for_linking)
        self.assertIn("concert", tables_for_linking)
        self.assertIn("singer", tables_for_linking)
        self.assertIn("Capacity", tables_for_linking["stadium"]["columns"])
        self.assertIn("Name", tables_for_linking["stadium"]["columns"])


if __name__ == "__main__":
    unittest.main()
