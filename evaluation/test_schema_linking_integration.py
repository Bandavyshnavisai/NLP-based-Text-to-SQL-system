"""End-to-End Integration Tests: Member 1 (Database Retrieval) -> Member 2 (Schema Linking).

Validates the full pipeline:
1. Natural language question is queried against DatabaseRetriever.
2. The retrieved top database and its catalog schema are passed to SchemaLinker.
3. Relevant tables (primary and bridge), relevant columns, and relationships are produced.
4. Output contract is verified for downstream consumption by Member 3.
"""

import unittest
from pathlib import Path

from database_retrieval.retriever import DatabaseRetriever
from schema_linking import SchemaLinker, SchemaLinkingResult


class TestMember1Member2Integration(unittest.TestCase):
    """Integration test suite connecting Member 1 Retriever to Member 2 SchemaLinker."""

    @classmethod
    def setUpClass(cls):
        workspace = Path(__file__).parent.parent.resolve()
        catalog_path = workspace / "database_retrieval" / "spider_catalog.json"
        index_path = workspace / "database_retrieval" / "spider_tfidf_index.pkl"

        cls.retriever = DatabaseRetriever(
            catalog_path=catalog_path,
            index_path=index_path,
        )
        cls.retriever.load_index()
        cls.linker = SchemaLinker(retriever=cls.retriever)

    def test_full_pipeline_concert_singer(self):
        """Pipeline test: 'Which stadium has hosted the most concerts?'"""
        question = "Which stadium has hosted the most concerts?"
        result = self.linker.link(question, top_k=5)

        self.assertIsInstance(result, SchemaLinkingResult)
        self.assertEqual(result.database, "concert_singer")
        self.assertGreater(result.retrieval_score, 0.0)

        # Tables: stadium and concert should be linked
        table_names = [t.name for t in result.tables]
        self.assertIn("stadium", table_names)
        self.assertIn("concert", table_names)

        # Check relationships
        rels = [(r.from_table, r.to_table) for r in result.relationships]
        self.assertIn(("concert", "stadium"), rels)

        # Check columns
        col_names = [f"{c.table}.{c.column}" for c in result.columns]
        self.assertIn("concert.Stadium_ID", col_names)
        self.assertIn("stadium.Stadium_ID", col_names)

        # Prompt formatting for Member 3
        prompt = result.to_member3_prompt()
        self.assertIn("TABLE stadium", prompt)
        self.assertIn("TABLE concert", prompt)
        self.assertIn("RELATIONSHIPS:", prompt)

    def test_full_pipeline_singers(self):
        """Pipeline test: 'What are the names of singers?'"""
        question = "What are the names of singers?"
        result = self.linker.link(question, top_k=5)

        self.assertIsInstance(result, SchemaLinkingResult)
        self.assertIn("singer", [t.name for t in result.tables])
        col_names = [f"{c.table}.{c.column}" for c in result.columns]
        self.assertIn("singer.Name", col_names)

    def test_full_pipeline_pets(self):
        """Pipeline test: 'Find all dogs and their owners.'"""
        question = "Find all dogs and their owners."
        result = self.linker.link(question, top_k=5)

        self.assertIsInstance(result, SchemaLinkingResult)
        self.assertTrue(len(result.tables) >= 1)
        self.assertTrue(len(result.columns) >= 1)

    def test_member3_prompt_generation(self):
        """Verify that generated text schema is valid for Member 3 prompt injection."""
        question = "Find the capacity of each stadium."
        result = self.linker.link(question, top_k=5)

        prompt_schema = result.to_member3_prompt()
        self.assertIsInstance(prompt_schema, str)
        self.assertGreater(len(prompt_schema), 20)
        self.assertIn("TABLE", prompt_schema)


if __name__ == "__main__":
    unittest.main()
