"""Unit tests for Member 2 (Schema Linking and Query Understanding).

Covers all 18 test requirements:
1. Question normalization
2. Lowercase normalization
3. Singular/plural matching
4. Table exact matching
5. Table normalized matching
6. Column matching
7. Synonym handling
8. Query intent extraction
9. Relationship detection
10. Bridge-table detection
11. Multi-hop relationship detection
12. Composite relationship handling
13. Empty question
14. Unknown terms
15. Multiple relevant tables
16. Relevant schema generation
17. Member 1 integration
18. Output structure
"""

import json
import unittest
from pathlib import Path
from typing import Any, Dict

from schema_linking import (
    ColumnMatch,
    IntentInfo,
    QueryUnderstanding,
    RelationshipMatch,
    SchemaLinker,
    SchemaLinkingResult,
    TableMatch,
    clean_text,
    normalize_question,
    normalize_tokens,
    singularize,
    tokenize,
)


class TestNormalizer(unittest.TestCase):
    """Tests for question and token normalization."""

    def test_lowercase_and_whitespace_normalization(self):
        """Test lowercase conversion and whitespace collapsing."""
        raw = "  Which   STADIUM  has   the MOST   concerts? \t\n"
        cleaned = clean_text(raw)
        self.assertEqual(cleaned, "which stadium has the most concerts?")

    def test_singular_plural_matching(self):
        """Test inflection and singular/plural conversions."""
        cases = {
            "singers": "singer",
            "students": "student",
            "departments": "department",
            "names": "name",
            "cities": "city",
            "countries": "country",
            "companies": "company",
            "categories": "category",
            "properties": "property",
            "activities": "activity",
            "people": "person",
            "men": "man",
            "women": "woman",
            "children": "child",
            "stadiums": "stadium",
            "concerts": "concert",
            "courses": "course",
            "classes": "class",
            "addresses": "address",
            "status": "status",
            "statuses": "status",
        }
        for plural, expected_singular in cases.items():
            self.assertEqual(
                singularize(plural),
                expected_singular,
                f"Failed on {plural} -> expected {expected_singular}",
            )

    def test_preserve_operational_words(self):
        """Test that operational keywords are preserved in normalization."""
        tokens = tokenize("Find the highest, lowest, average, and most recent salary")
        norm = normalize_tokens(tokens, remove_stopwords=True)
        self.assertIn("highest", norm)
        self.assertIn("lowest", norm)
        self.assertIn("average", norm)
        self.assertIn("most", norm)
        self.assertIn("salary", norm)

    def test_normalize_question_pipeline(self):
        """Test full question normalization pipeline."""
        q = "What are the names of singers in cities?"
        norm_q = normalize_question(q)
        self.assertIn("name", norm_q)
        self.assertIn("singer", norm_q)
        self.assertIn("city", norm_q)


class TestQueryUnderstanding(unittest.TestCase):
    """Tests for lightweight semantic intent and concept extraction."""

    def test_ranking_intent(self):
        """'Which stadium has hosted the most concerts?' -> ranking with max + count."""
        q = "Which stadium has hosted the most concerts?"
        analysis = QueryUnderstanding.analyze(q)
        self.assertEqual(analysis["intent_type"], "ranking")
        self.assertIn("maximum", analysis["operations"])
        self.assertIn("stadium", analysis["entities"])
        self.assertIn("concert", analysis["entities"])

    def test_count_intent(self):
        """'How many singers do we have?' -> count intent."""
        q = "How many singers do we have?"
        analysis = QueryUnderstanding.analyze(q)
        self.assertEqual(analysis["intent_type"], "count")
        self.assertIn("count", analysis["operations"])
        self.assertIn("singer", analysis["entities"])

    def test_condition_extraction(self):
        """'Find students enrolled in the computer science department' -> condition 'computer science'."""
        q = "Find students enrolled in the computer science department."
        analysis = QueryUnderstanding.analyze(q)
        self.assertIn("computer science", analysis["conditions"])
        self.assertIn("student", analysis["entities"])
        self.assertIn("department", analysis["entities"])

    def test_aggregation_average(self):
        """'What is the average age of singers?' -> average operation."""
        q = "What is the average age of singers?"
        analysis = QueryUnderstanding.analyze(q)
        self.assertEqual(analysis["intent_type"], "aggregation")
        self.assertIn("average", analysis["operations"])


class TestSchemaLinkerMocked(unittest.TestCase):
    """Deterministic tests for schema linking with controlled schemas."""

    def setUp(self):
        self.linker = SchemaLinker()

        # Synthetic multi-table schema for testing
        self.synthetic_schema = {
            "database_name": "university_test",
            "total_tables": 3,
            "tables": [
                {
                    "table_name": "student",
                    "columns": [
                        {"name": "student_id", "type": "INT", "primary_key": True, "not_null": True, "default_value": None},
                        {"name": "name", "type": "TEXT", "primary_key": False, "not_null": True, "default_value": None},
                        {"name": "age", "type": "INT", "primary_key": False, "not_null": False, "default_value": None},
                    ],
                    "primary_keys": ["student_id"],
                    "is_composite_pk": False,
                    "foreign_keys": [],
                },
                {
                    "table_name": "department",
                    "columns": [
                        {"name": "department_id", "type": "INT", "primary_key": True, "not_null": True, "default_value": None},
                        {"name": "department_name", "type": "TEXT", "primary_key": False, "not_null": True, "default_value": None},
                        {"name": "building", "type": "TEXT", "primary_key": False, "not_null": False, "default_value": None},
                    ],
                    "primary_keys": ["department_id"],
                    "is_composite_pk": False,
                    "foreign_keys": [],
                },
                {
                    "table_name": "enrolled_in",
                    "columns": [
                        {"name": "student_id", "type": "INT", "primary_key": True, "not_null": True, "default_value": None},
                        {"name": "department_id", "type": "INT", "primary_key": True, "not_null": True, "default_value": None},
                        {"name": "enrollment_date", "type": "TEXT", "primary_key": False, "not_null": False, "default_value": None},
                    ],
                    "primary_keys": ["student_id", "department_id"],
                    "is_composite_pk": True,
                    "foreign_keys": [
                        {"from_column": "student_id", "to_table": "student", "to_column": "student_id", "is_composite": False},
                        {"from_column": "department_id", "to_table": "department", "to_column": "department_id", "is_composite": False},
                    ],
                },
            ],
            "relationships": [
                {
                    "source_table": "enrolled_in",
                    "source_column": "student_id",
                    "target_table": "student",
                    "target_column": "student_id",
                    "source_columns": ["student_id"],
                    "target_columns": ["student_id"],
                    "is_composite": False,
                },
                {
                    "source_table": "enrolled_in",
                    "source_column": "department_id",
                    "target_table": "department",
                    "target_column": "department_id",
                    "source_columns": ["department_id"],
                    "target_columns": ["department_id"],
                    "is_composite": False,
                },
            ],
        }

    def test_table_exact_and_normalized_matching(self):
        """Test exact and normalized table matching."""
        result = self.linker.link(
            question="List all students",
            target_schema=self.synthetic_schema,
        )
        table_names = [t.name for t in result.tables if t.role == "primary"]
        self.assertIn("student", table_names)

    def test_column_matching(self):
        """Test column matching on student name and age."""
        result = self.linker.link(
            question="What is the age and name of each student?",
            target_schema=self.synthetic_schema,
        )
        matched_cols = [f"{c.table}.{c.column}" for c in result.columns]
        self.assertIn("student.name", matched_cols)
        self.assertIn("student.age", matched_cols)

    def test_synonym_handling(self):
        """Test synonym handling (e.g. 'venue' -> 'stadium', 'teacher' -> 'instructor')."""
        syn_schema = {
            "database_name": "venue_db",
            "total_tables": 1,
            "tables": [
                {
                    "table_name": "stadium",
                    "columns": [
                        {"name": "stadium_id", "type": "INT", "primary_key": True, "not_null": True, "default_value": None},
                        {"name": "capacity", "type": "INT", "primary_key": False, "not_null": False, "default_value": None},
                    ],
                    "primary_keys": ["stadium_id"],
                    "is_composite_pk": False,
                    "foreign_keys": [],
                }
            ],
            "relationships": [],
        }
        result = self.linker.link(
            question="Find the capacity of the arena venue",
            target_schema=syn_schema,
        )
        table_names = [t.name for t in result.tables if t.role == "primary"]
        self.assertIn("stadium", table_names)
        self.assertIn("stadium.capacity", [f"{c.table}.{c.column}" for c in result.columns])

    def test_bridge_table_detection(self):
        """Test detection of enrolled_in as bridge table between student and department."""
        result = self.linker.link(
            question="Find students in the computer science department",
            target_schema=self.synthetic_schema,
        )
        roles = {t.name: t.role for t in result.tables}
        self.assertEqual(roles.get("student"), "primary")
        self.assertEqual(roles.get("department"), "primary")
        self.assertEqual(roles.get("enrolled_in"), "bridge")

        # Check relationships contain both paths
        rel_pairs = {(r.from_table, r.to_table) for r in result.relationships}
        self.assertIn(("enrolled_in", "student"), rel_pairs)
        self.assertIn(("enrolled_in", "department"), rel_pairs)

    def test_composite_relationship_handling(self):
        """Test preserving composite foreign keys with multi-column mappings."""
        comp_schema = {
            "database_name": "composite_db",
            "total_tables": 2,
            "tables": [
                {
                    "table_name": "section",
                    "columns": [
                        {"name": "course_id", "type": "TEXT", "primary_key": True, "not_null": True, "default_value": None},
                        {"name": "sec_id", "type": "TEXT", "primary_key": True, "not_null": True, "default_value": None},
                        {"name": "semester", "type": "TEXT", "primary_key": True, "not_null": True, "default_value": None},
                        {"name": "year", "type": "INT", "primary_key": True, "not_null": True, "default_value": None},
                    ],
                    "primary_keys": ["course_id", "sec_id", "semester", "year"],
                    "is_composite_pk": True,
                    "foreign_keys": [],
                },
                {
                    "table_name": "teaches",
                    "columns": [
                        {"name": "id", "type": "TEXT", "primary_key": True, "not_null": True, "default_value": None},
                        {"name": "course_id", "type": "TEXT", "primary_key": True, "not_null": True, "default_value": None},
                        {"name": "sec_id", "type": "TEXT", "primary_key": True, "not_null": True, "default_value": None},
                        {"name": "semester", "type": "TEXT", "primary_key": True, "not_null": True, "default_value": None},
                        {"name": "year", "type": "INT", "primary_key": True, "not_null": True, "default_value": None},
                    ],
                    "primary_keys": ["id", "course_id", "sec_id", "semester", "year"],
                    "is_composite_pk": True,
                    "foreign_keys": [
                        {
                            "from_columns": ["course_id", "sec_id", "semester", "year"],
                            "to_table": "section",
                            "to_columns": ["course_id", "sec_id", "semester", "year"],
                            "is_composite": True,
                        }
                    ],
                },
            ],
            "relationships": [
                {
                    "source_table": "teaches",
                    "source_column": "course_id, sec_id, semester, year",
                    "target_table": "section",
                    "target_column": "course_id, sec_id, semester, year",
                    "source_columns": ["course_id", "sec_id", "semester", "year"],
                    "target_columns": ["course_id", "sec_id", "semester", "year"],
                    "is_composite": True,
                }
            ],
        }
        result = self.linker.link(
            question="Show all sections and who teaches them",
            target_schema=comp_schema,
        )
        self.assertGreater(len(result.relationships), 0)
        rel = result.relationships[0]
        self.assertTrue(rel.is_composite)
        self.assertEqual(rel.from_columns, ["course_id", "sec_id", "semester", "year"])
        self.assertEqual(rel.to_columns, ["course_id", "sec_id", "semester", "year"])

    def test_empty_question(self):
        """Test graceful handling of empty query string."""
        result = self.linker.link("", target_schema=self.synthetic_schema)
        self.assertEqual(result.question, "")
        self.assertEqual(result.tables, [])

    def test_unknown_terms(self):
        """Test query with unknown terms."""
        result = self.linker.link(
            "xyzzy foobar blarg",
            target_schema=self.synthetic_schema,
        )
        self.assertIsInstance(result, SchemaLinkingResult)

    def test_multiple_relevant_tables(self):
        """Test query mentioning multiple tables."""
        result = self.linker.link(
            "Show students and departments",
            target_schema=self.synthetic_schema,
        )
        tables = [t.name for t in result.tables if t.role == "primary"]
        self.assertIn("student", tables)
        self.assertIn("department", tables)

    def test_output_structure_and_serialization(self):
        """Test serialization to dict and JSON format."""
        result = self.linker.link(
            "Find students in department",
            target_schema=self.synthetic_schema,
        )
        res_dict = result.to_dict()
        self.assertIn("question", res_dict)
        self.assertIn("intent", res_dict)
        self.assertIn("database", res_dict)
        self.assertIn("tables", res_dict)
        self.assertIn("columns", res_dict)
        self.assertIn("relationships", res_dict)
        self.assertIn("linked_schema", res_dict)
        self.assertIn("member3_prompt_schema", res_dict)

        # JSON roundtrip
        json_str = result.to_json()
        parsed = json.loads(json_str)
        self.assertEqual(parsed["database"], "university_test")


class TestSchemaLinkerRealDatabases(unittest.TestCase):
    """Integration tests on actual Spider database schemas."""

    @classmethod
    def setUpClass(cls):
        cls.linker = SchemaLinker()

    def test_concert_singer_stadium_example(self):
        """Real Spider test: 'Which stadium has hosted the most concerts?'"""
        result = self.linker.link(
            "Which stadium has hosted the most concerts?",
            target_db="concert_singer",
        )
        table_names = [t.name for t in result.tables]
        self.assertIn("stadium", table_names)
        self.assertIn("concert", table_names)

        col_refs = [f"{c.table}.{c.column}" for c in result.columns]
        self.assertIn("concert.Stadium_ID", col_refs)
        self.assertIn("stadium.Stadium_ID", col_refs)

        # Check FK relationship
        rels = [(r.from_table, r.to_table) for r in result.relationships]
        self.assertIn(("concert", "stadium"), rels)

    def test_singers_name_example(self):
        """Real Spider test: 'What are the names of singers?'"""
        result = self.linker.link(
            "What are the names of singers?",
            target_db="concert_singer",
        )
        table_names = [t.name for t in result.tables if t.role == "primary"]
        self.assertIn("singer", table_names)
        col_refs = [f"{c.table}.{c.column}" for c in result.columns]
        self.assertIn("singer.Name", col_refs)

    def test_multi_hop_concert_singer(self):
        """Real Spider test: Multi-hop bridge table between singer and stadium."""
        result = self.linker.link(
            "Find singers and stadiums where they performed",
            target_db="concert_singer",
        )
        table_roles = {t.name: t.role for t in result.tables}
        self.assertEqual(table_roles.get("singer"), "primary")
        self.assertEqual(table_roles.get("stadium"), "primary")
        self.assertEqual(table_roles.get("singer_in_concert"), "bridge")
        self.assertEqual(table_roles.get("concert"), "bridge")


if __name__ == "__main__":
    unittest.main()
