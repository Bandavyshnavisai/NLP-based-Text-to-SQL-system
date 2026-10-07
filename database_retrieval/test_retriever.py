"""Tests for Database Retrieval components.

Covers:
- CatalogBuilder: build_and_save creates a valid JSON file with 166 entries.
- CatalogBuilder: load_catalog reads back the exact same catalog.
- CatalogBuilder: each entry has required keys.
- CatalogBuilder: schema_text is non-empty.
- DatabaseRetriever: build_index / load_index work.
- DatabaseRetriever: retrieve returns non-empty results.
- DatabaseRetriever: results are ranked by descending score.
- DatabaseRetriever: top-k is respected.
- DatabaseRetriever: matched_tables and matched_columns are lists.
- DatabaseRetriever: empty / whitespace question returns empty list.
- DatabaseRetriever: unknown question still returns top_k items.
"""

import os
import json
import unittest
from pathlib import Path

from database_retrieval.catalog_builder import CatalogBuilder
from database_retrieval.retriever import DatabaseRetriever


class TestCatalogBuilder(unittest.TestCase):
    """Unit tests for CatalogBuilder."""

    @classmethod
    def setUpClass(cls):
        cls.workspace = Path(__file__).parent.parent.resolve()
        cls.databases_dir = cls.workspace / "databases"
        # Use a temporary catalog so we don't overwrite the real one
        cls.catalog_path = cls.workspace / "database_retrieval" / "_test_catalog.json"
        cls.builder = CatalogBuilder(
            databases_dir=cls.databases_dir,
            catalog_path=cls.catalog_path,
        )
        # Build once up-front; reused by all tests in this class.
        cls.catalog = cls.builder.build_and_save(verbose=False)

    def test_build_and_load_roundtrip(self):
        """build_and_save then load_catalog should return identical data."""
        loaded = self.builder.load_catalog()
        self.assertEqual(len(self.catalog), 166, "Expected 166 catalog entries.")
        self.assertEqual(self.catalog, loaded, "Loaded catalog differs from built catalog.")

    def test_catalog_entry_keys(self):
        """Each entry must contain the expected keys."""
        catalog = self.catalog
        required_keys = {
            "database_name", "total_tables", "tables",
            "relationships", "all_tables", "all_columns", "schema_text",
        }
        for entry in catalog:
            self.assertTrue(
                required_keys.issubset(entry.keys()),
                f"Missing keys in entry {entry.get('database_name')}: "
                f"{required_keys - entry.keys()}"
            )

    def test_schema_text_non_empty(self):
        """schema_text must be a non-empty string for all entries."""
        catalog = self.catalog
        for entry in catalog:
            self.assertIsInstance(entry["schema_text"], str)
            self.assertGreater(
                len(entry["schema_text"]), 10,
                f"schema_text too short for {entry['database_name']}"
            )

    def test_all_tables_list(self):
        """all_tables must be a non-empty list."""
        catalog = self.catalog
        for entry in catalog:
            self.assertIsInstance(entry["all_tables"], list)
            self.assertGreater(len(entry["all_tables"]), 0)

    @classmethod
    def tearDownClass(cls):
        if cls.catalog_path.exists():
            cls.catalog_path.unlink()


class TestDatabaseRetriever(unittest.TestCase):
    """Unit tests for DatabaseRetriever."""

    @classmethod
    def setUpClass(cls):
        cls.workspace = Path(__file__).parent.parent.resolve()
        cls.catalog_path = cls.workspace / "database_retrieval" / "spider_catalog.json"
        cls.index_path = cls.workspace / "database_retrieval" / "spider_tfidf_index.pkl"
        cls.retriever = DatabaseRetriever(
            catalog_path=cls.catalog_path,
            index_path=cls.index_path,
        )
        # Build index if not present (first-time setup)
        if not cls.index_path.exists():
            cls.retriever.build_index(verbose=False)
        else:
            cls.retriever.load_index()
        # Ensure catalog loaded
        if cls.retriever._catalog is None and cls.catalog_path.exists():
            cls.retriever._catalog = cls.retriever._catalog_builder.load_catalog()

    # --- Basic retrieval ---

    def test_retrieve_returns_list(self):
        """retrieve() must return a list."""
        results = self.retriever.retrieve("How many singers do we have?", top_k=3)
        self.assertIsInstance(results, list)

    def test_retrieve_top_k_respected(self):
        """retrieve() must return at most top_k results."""
        for k in (1, 3, 5):
            results = self.retriever.retrieve("Find all flights.", top_k=k)
            self.assertLessEqual(len(results), k, f"Expected at most {k} results, got {len(results)}")

    def test_retrieve_result_structure(self):
        """Each result must contain the required keys."""
        results = self.retriever.retrieve("Show all car models.", top_k=3)
        for r in results:
            self.assertIn("rank", r)
            self.assertIn("database", r)
            self.assertIn("score", r)
            self.assertIn("matched_tables", r)
            self.assertIn("matched_columns", r)
            self.assertIsInstance(r["matched_tables"], list)
            self.assertIsInstance(r["matched_columns"], list)

    def test_retrieve_ranks_in_descending_order(self):
        """Results must be ordered by descending score."""
        results = self.retriever.retrieve("List all car models and their manufacturers.", top_k=5)
        scores = [r["score"] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True), "Results not sorted by descending score.")

    def test_retrieve_rank_field_sequential(self):
        """rank field must be 1, 2, 3, ... in order."""
        results = self.retriever.retrieve("Which museums were visited?", top_k=5)
        for i, r in enumerate(results, 1):
            self.assertEqual(r["rank"], i, f"rank mismatch at position {i}")

    # --- Edge cases ---

    def test_retrieve_empty_string_returns_empty(self):
        """Empty question must return an empty list."""
        results = self.retriever.retrieve("", top_k=5)
        self.assertEqual(results, [], "Expected [] for empty question.")

    def test_retrieve_whitespace_only_returns_empty(self):
        """Whitespace-only question must return an empty list."""
        results = self.retriever.retrieve("   \t\n  ", top_k=5)
        self.assertEqual(results, [], "Expected [] for whitespace-only question.")

    def test_retrieve_unknown_words_returns_results(self):
        """A question with no matching terms should still return top_k items (even at score 0)."""
        results = self.retriever.retrieve(
            "xyzzy quux frobnicate blarg 12345", top_k=5
        )
        self.assertEqual(len(results), 5, "Should still return 5 results for unknown words.")

    # --- Known-good questions ---

    def test_retrieve_concert_singer_in_top5(self):
        """'How many singers do we have?' -> concert_singer should appear in top-5."""
        results = self.retriever.retrieve("How many singers do we have?", top_k=5)
        dbs = [r["database"] for r in results]
        self.assertIn("concert_singer", dbs, f"concert_singer not in top-5: {dbs}")

    def test_retrieve_museum_top1(self):
        """'Which museums have been visited more than 100 times?' -> museum_visit top-1."""
        results = self.retriever.retrieve("Which museums have been visited?", top_k=5)
        dbs = [r["database"] for r in results]
        self.assertIn("museum_visit", dbs[:3], f"museum_visit not in top-3: {dbs}")

    def test_retrieve_car_models(self):
        """'List all car models and their manufacturers.' -> car_1 in top-3."""
        results = self.retriever.retrieve("List all car models and their manufacturers.", top_k=3)
        dbs = [r["database"] for r in results]
        self.assertIn("car_1", dbs, f"car_1 not in top-3: {dbs}")

    def test_format_results_non_empty(self):
        """format_results should return a non-empty string for valid results."""
        results = self.retriever.retrieve("Find all dog breeds.", top_k=3)
        formatted = self.retriever.format_results(results)
        self.assertIsInstance(formatted, str)
        self.assertGreater(len(formatted), 0)

    def test_format_results_empty(self):
        """format_results for empty list should return the no-results message."""
        formatted = self.retriever.format_results([])
        self.assertIn("No results", formatted)


if __name__ == "__main__":
    unittest.main()
