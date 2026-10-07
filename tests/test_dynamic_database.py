"""Tests for Dynamic User Database Mode (Phase 2 generalization).

Covers all 17 new test requirements:
 1.  Valid SQLite database (.db)
 2.  Valid SQLite database (.sqlite)
 3.  Valid SQLite database (.sqlite3)
 4.  Invalid / missing file
 5.  Corrupted / non-SQLite file
 6.  Empty database (no tables)
 7.  Database with no user tables (only sqlite_* internal)
 8.  Multiple tables
 9.  Primary keys
10.  Foreign keys
11.  Composite primary keys
12.  Composite foreign keys
13.  Relationship extraction
14.  Arbitrary database name
15.  Arbitrary table names
16.  Member 2 receiving a dynamically extracted schema
17.  Member 2 functioning without Spider metadata

All test databases are created in-memory or as temporary files — none are
Spider databases, and no Spider metadata is used anywhere in this file.

The test DB uses generic names (dept / emp / project) to verify there are
no hardcoded Spider assumptions in the implementation.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from database_retrieval.active_database import ActiveDatabase
from database_retrieval.adapter import DatabaseAdapter, SQLiteAdapter, get_adapter
from database_retrieval.loader import load_database
from schema_linking import SchemaLinker, SchemaLinkingResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sqlite(path: Path, ddl_statements: list) -> None:
    """Create a SQLite file at *path* and execute each DDL statement."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        for stmt in ddl_statements:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test 1-3: Extension acceptance
# ---------------------------------------------------------------------------

class TestValidExtensions(unittest.TestCase):
    """Tests 1, 2, 3 — load_database accepts .db, .sqlite, .sqlite3."""

    DDL = [
        "CREATE TABLE items (item_id INTEGER PRIMARY KEY, label TEXT NOT NULL);"
    ]

    def _assert_loads(self, suffix: str) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / f"testdb{suffix}"
            _make_sqlite(db_path, self.DDL)
            db = load_database(db_path)
            self.assertIsInstance(db, ActiveDatabase)
            self.assertEqual(db.database_type, "sqlite")
            self.assertEqual(db.database_name, "testdb")
            self.assertIn("items", db.table_names)

    def test_dot_db_extension(self):
        """Test 1: .db extension is accepted."""
        self._assert_loads(".db")

    def test_dot_sqlite_extension(self):
        """Test 2: .sqlite extension is accepted."""
        self._assert_loads(".sqlite")

    def test_dot_sqlite3_extension(self):
        """Test 3: .sqlite3 extension is accepted."""
        self._assert_loads(".sqlite3")


# ---------------------------------------------------------------------------
# Test 4: Invalid / missing file
# ---------------------------------------------------------------------------

class TestInvalidFile(unittest.TestCase):
    """Test 4 — FileNotFoundError for missing file."""

    def test_missing_file_raises(self):
        """load_database() on a non-existent path must raise FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            load_database("/tmp/this_file_definitely_does_not_exist_xyz.db")

    def test_unsupported_extension_raises(self):
        """load_database() on an unsupported extension raises ValueError."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            tmp = Path(f.name)
        try:
            with self.assertRaises(ValueError):
                load_database(tmp)
        finally:
            tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Test 5: Corrupted file
# ---------------------------------------------------------------------------

class TestCorruptedFile(unittest.TestCase):
    """Test 5 — ValueError for a file that is not a valid SQLite database."""

    def test_corrupted_sqlite_raises(self):
        """A file with invalid SQLite magic bytes raises ValueError."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp = Path(f.name)
            f.write(b"THIS IS NOT A SQLITE DATABASE FILE\x00\x01\x02")
        try:
            with self.assertRaises(ValueError):
                load_database(tmp)
        finally:
            tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Test 6-7: Empty / no-user-table databases
# ---------------------------------------------------------------------------

class TestEmptyDatabase(unittest.TestCase):
    """Tests 6, 7 — databases with no user tables are rejected."""

    def test_empty_database_raises(self):
        """Test 6: A freshly created SQLite file with zero tables raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "empty.db"
            # Create an empty SQLite file (valid format, no tables)
            conn = sqlite3.connect(str(db_path))
            conn.close()
            with self.assertRaises(ValueError):
                load_database(db_path)

    def test_only_system_tables_raises(self):
        """Test 7: A database with only sqlite_* internal tables raises ValueError.

        SQLite's internal tables (sqlite_master, sqlite_sequence) are never
        listed by our query — we need at least one user table.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "sysonly.db"
            conn = sqlite3.connect(str(db_path))
            try:
                # sqlite_sequence is only created implicitly by AUTOINCREMENT;
                # creating and immediately dropping a table leaves behind no
                # user tables, so the database is effectively empty.
                conn.execute(
                    "CREATE TABLE _tmp (id INTEGER PRIMARY KEY AUTOINCREMENT);"
                )
                conn.commit()
                conn.execute("DROP TABLE _tmp;")
                conn.commit()
            finally:
                conn.close()
            with self.assertRaises(ValueError):
                load_database(db_path)


# ---------------------------------------------------------------------------
# Tests 8-15: Schema extraction correctness
# ---------------------------------------------------------------------------

class TestSchemaExtraction(unittest.TestCase):
    """Tests 8-15 — dynamic schema extraction on a non-Spider database."""

    # Generic domain names: no "employees", "departments", "salary" hardcoded
    DDL = [
        """
        CREATE TABLE dept (
            dept_id   INTEGER PRIMARY KEY,
            dept_name TEXT    NOT NULL
        );
        """,
        """
        CREATE TABLE emp (
            emp_id    INTEGER PRIMARY KEY,
            full_name TEXT    NOT NULL,
            dept_id   INTEGER NOT NULL,
            wage      REAL,
            FOREIGN KEY (dept_id) REFERENCES dept(dept_id)
        );
        """,
        """
        CREATE TABLE project (
            proj_id   INTEGER NOT NULL,
            phase_id  INTEGER NOT NULL,
            proj_name TEXT,
            PRIMARY KEY (proj_id, phase_id)
        );
        """,
        """
        CREATE TABLE assignment (
            emp_id    INTEGER NOT NULL,
            proj_id   INTEGER NOT NULL,
            phase_id  INTEGER NOT NULL,
            hours     REAL,
            PRIMARY KEY (emp_id, proj_id, phase_id),
            FOREIGN KEY (emp_id)              REFERENCES emp(emp_id),
            FOREIGN KEY (proj_id, phase_id)   REFERENCES project(proj_id, phase_id)
        );
        """,
    ]

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls._tmpdir.name) / "generic_test.db"
        _make_sqlite(cls.db_path, cls.DDL)
        cls.active_db = load_database(cls.db_path)
        cls.schema = cls.active_db.get_schema()

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    # --- Test 8: multiple tables ----------------------------------------

    def test_multiple_tables_discovered(self):
        """Test 8: All four user tables are discovered."""
        self.assertEqual(len(self.schema["tables"]), 4)
        table_names = {t["table_name"] for t in self.schema["tables"]}
        self.assertSetEqual(table_names, {"dept", "emp", "project", "assignment"})

    # --- Test 9: primary keys -------------------------------------------

    def test_primary_keys_extracted(self):
        """Test 9: Simple primary keys are correctly identified."""
        table_by_name = {t["table_name"]: t for t in self.schema["tables"]}

        dept = table_by_name["dept"]
        self.assertEqual(dept["primary_keys"], ["dept_id"])
        self.assertFalse(dept["is_composite_pk"])
        # Verify column-level flag
        pk_cols = [c["name"] for c in dept["columns"] if c["primary_key"]]
        self.assertIn("dept_id", pk_cols)

        emp = table_by_name["emp"]
        self.assertEqual(emp["primary_keys"], ["emp_id"])
        self.assertFalse(emp["is_composite_pk"])

    # --- Test 10: foreign keys ------------------------------------------

    def test_foreign_keys_extracted(self):
        """Test 10: Simple foreign key (emp→dept) is captured."""
        table_by_name = {t["table_name"]: t for t in self.schema["tables"]}
        emp = table_by_name["emp"]
        fk_targets = [fk["to_table"] for fk in emp["foreign_keys"]]
        self.assertIn("dept", fk_targets)

    # --- Test 11: composite primary keys --------------------------------

    def test_composite_primary_key(self):
        """Test 11: Composite PK on (proj_id, phase_id) is detected."""
        table_by_name = {t["table_name"]: t for t in self.schema["tables"]}
        project = table_by_name["project"]
        self.assertTrue(project["is_composite_pk"])
        self.assertIn("proj_id", project["primary_keys"])
        self.assertIn("phase_id", project["primary_keys"])

    # --- Test 12: composite foreign keys --------------------------------

    def test_composite_foreign_key(self):
        """Test 12: Composite FK (assignment.(proj_id, phase_id) → project) is captured."""
        table_by_name = {t["table_name"]: t for t in self.schema["tables"]}
        assignment = table_by_name["assignment"]
        composite_fks = [fk for fk in assignment["foreign_keys"] if fk["is_composite"]]
        self.assertGreater(len(composite_fks), 0, "No composite FK found on 'assignment'")
        fk = composite_fks[0]
        self.assertEqual(fk["to_table"], "project")
        self.assertIn("proj_id", fk["from_columns"])
        self.assertIn("phase_id", fk["from_columns"])

    # --- Test 13: relationship extraction --------------------------------

    def test_relationships_extracted(self):
        """Test 13: FK relationships appear in schema['relationships']."""
        rels = self.schema.get("relationships", [])
        self.assertGreater(len(rels), 0)
        rel_pairs = {(r["source_table"], r["target_table"]) for r in rels}
        # emp → dept
        self.assertIn(("emp", "dept"), rel_pairs)
        # assignment → emp
        self.assertIn(("assignment", "emp"), rel_pairs)
        # assignment → project (composite)
        self.assertIn(("assignment", "project"), rel_pairs)

    # --- Test 14: arbitrary database name --------------------------------

    def test_arbitrary_database_name(self):
        """Test 14: Database name is derived from file stem, not Spider metadata."""
        self.assertEqual(self.active_db.database_name, "generic_test")
        self.assertEqual(self.schema["database_name"], "generic_test")

    # --- Test 15: arbitrary table names ----------------------------------

    def test_arbitrary_table_names(self):
        """Test 15: Table names are discovered from the actual SQLite schema."""
        table_names = self.active_db.table_names
        # None of these are Spider-specific names
        self.assertIn("dept", table_names)
        self.assertIn("emp", table_names)
        self.assertIn("project", table_names)
        self.assertIn("assignment", table_names)


# ---------------------------------------------------------------------------
# Tests 16-17: Member 2 integration without Spider
# ---------------------------------------------------------------------------

class TestMember2DynamicIntegration(unittest.TestCase):
    """Tests 16, 17 — SchemaLinker works on dynamically extracted non-Spider schemas."""

    DDL = [
        """
        CREATE TABLE dept (
            dept_id   INTEGER PRIMARY KEY,
            dept_name TEXT NOT NULL
        );
        """,
        """
        CREATE TABLE emp (
            emp_id    INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            dept_id   INTEGER NOT NULL,
            wage      REAL,
            FOREIGN KEY (dept_id) REFERENCES dept(dept_id)
        );
        """,
    ]

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls._tmpdir.name) / "company.db"
        _make_sqlite(cls.db_path, cls.DDL)
        cls.active_db = load_database(cls.db_path)
        cls.linker = SchemaLinker()   # No Spider retriever — purely dynamic

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def test_schema_is_passed_to_linker(self):
        """Test 16: Dynamically extracted schema is accepted by SchemaLinker."""
        schema = self.active_db.get_schema()
        result = self.linker.link(
            question="What is the average wage?",
            target_schema=schema,
        )
        self.assertIsInstance(result, SchemaLinkingResult)

    def test_linker_without_spider_metadata(self):
        """Test 17: SchemaLinker produces results without any Spider retriever or catalog."""
        schema = self.active_db.get_schema()

        # Salary / wage question
        result = self.linker.link(
            "What is the average wage of employees?",
            target_schema=schema,
        )
        self.assertIsInstance(result, SchemaLinkingResult)
        self.assertEqual(result.database, "company")
        self.assertGreater(len(result.tables), 0)
        # 'emp' table should be primary (has 'wage' and 'emp' tokens)
        table_names = [t.name for t in result.tables]
        self.assertIn("emp", table_names)

    def test_aggregation_question_on_dynamic_db(self):
        """Average wage query resolves emp table and wage column."""
        schema = self.active_db.get_schema()
        result = self.linker.link(
            "What is the average wage of employees?",
            target_schema=schema,
        )
        col_refs = [f"{c.table}.{c.column}" for c in result.columns]
        self.assertIn("emp.wage", col_refs)

    def test_department_count_question(self):
        """Which dept has the most emp? → dept table is linked."""
        schema = self.active_db.get_schema()
        result = self.linker.link(
            "Which dept has the highest number of emp records?",
            target_schema=schema,
        )
        table_names = [t.name for t in result.tables]
        # 'dept' appears in question → matched; 'emp' appears in question → matched
        self.assertIn("dept", table_names)
        self.assertIn("emp", table_names)

    def test_filter_question_on_dynamic_db(self):
        """List emp with wage > 50000 → emp table identified via 'wage' column."""
        schema = self.active_db.get_schema()
        result = self.linker.link(
            "List emp with wage greater than 50000.",
            target_schema=schema,
        )
        table_names = [t.name for t in result.tables]
        # 'emp' appears in the question → normalized match
        self.assertIn("emp", table_names)

    def test_output_structure_for_dynamic_db(self):
        """SchemaLinkingResult from a dynamic DB has the correct output structure."""
        schema = self.active_db.get_schema()
        result = self.linker.link(
            "Show all employees and their departments.",
            target_schema=schema,
        )
        res_dict = result.to_dict()
        for key in ("question", "intent", "database", "tables",
                    "columns", "relationships", "linked_schema",
                    "member3_prompt_schema"):
            self.assertIn(key, res_dict, f"Missing key: {key}")
        # No Spider dependency in the output
        self.assertNotIn("retrieval", result.database)

    def test_member3_prompt_generated_for_dynamic_db(self):
        """Member-3 textual prompt is generated correctly from a dynamic DB schema."""
        schema = self.active_db.get_schema()
        result = self.linker.link(
            "Find all employees and their department names.",
            target_schema=schema,
        )
        prompt = result.to_member3_prompt()
        self.assertIsInstance(prompt, str)
        self.assertIn("TABLE", prompt)
        self.assertGreater(len(prompt), 10)

    def test_relationship_linking_for_dynamic_db(self):
        """FK relationship emp→dept is discovered when both tables are linked."""
        schema = self.active_db.get_schema()
        # Use abbreviations present in the schema so the linker can match them
        result = self.linker.link(
            "Show emp full_name and their dept dept_name.",
            target_schema=schema,
        )
        # When both emp and dept are active, the FK relationship must appear
        table_names = [t.name for t in result.tables]
        if "emp" in table_names and "dept" in table_names:
            rel_pairs = {(r.from_table, r.to_table) for r in result.relationships}
            self.assertIn(("emp", "dept"), rel_pairs)
        else:
            # At minimum both tables must exist in the schema
            rels = schema.get("relationships", [])
            rel_pairs_raw = {(r["source_table"], r["target_table"]) for r in rels}
            self.assertIn(("emp", "dept"), rel_pairs_raw)


# ---------------------------------------------------------------------------
# Section 8, 11, 13 Dynamic Database & Bridge Verification Suite
# ---------------------------------------------------------------------------

class TestCompanyDemoAndBridgeLinking(unittest.TestCase):
    """Verifies schema linking against non-Spider databases specified in prompt."""

    COMPANY_DDL = [
        """
        CREATE TABLE departments (
            department_id INTEGER PRIMARY KEY,
            department_name TEXT
        );
        """,
        """
        CREATE TABLE employees (
            employee_id INTEGER PRIMARY KEY,
            name TEXT,
            department_id INTEGER,
            salary REAL,
            FOREIGN KEY (department_id) REFERENCES departments(department_id)
        );
        """,
        "INSERT INTO departments VALUES (1, 'Engineering');",
        "INSERT INTO departments VALUES (2, 'Sales');",
        "INSERT INTO employees VALUES (101, 'Alice', 1, 95000);",
        "INSERT INTO employees VALUES (102, 'Bob', 2, 80000);",
    ]

    UNIVERSITY_DDL = [
        """
        CREATE TABLE students (
            student_id INTEGER PRIMARY KEY,
            name TEXT
        );
        """,
        """
        CREATE TABLE departments (
            department_id INTEGER PRIMARY KEY,
            department_name TEXT
        );
        """,
        """
        CREATE TABLE enrolled_in (
            enrollment_id INTEGER PRIMARY KEY,
            student_id INTEGER,
            department_id INTEGER,
            semester TEXT,
            FOREIGN KEY (student_id) REFERENCES students(student_id),
            FOREIGN KEY (department_id) REFERENCES departments(department_id)
        );
        """,
        "INSERT INTO students VALUES (1, 'John');",
        "INSERT INTO departments VALUES (10, 'Computer Science');",
        "INSERT INTO enrolled_in VALUES (1001, 1, 10, 'Fall 2026');",
    ]

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.company_db_path = Path(self.tmpdir.name) / "company_demo.db"
        _make_sqlite(self.company_db_path, self.COMPANY_DDL)
        self.company_db = load_database(self.company_db_path)

        self.univ_db_path = Path(self.tmpdir.name) / "university_demo.db"
        _make_sqlite(self.univ_db_path, self.UNIVERSITY_DDL)
        self.univ_db = load_database(self.univ_db_path)

        self.linker = SchemaLinker()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_section8_and_13_question1_engineering(self):
        """'Find all employees in Engineering.' -> employees + departments + FK."""
        schema = self.company_db.get_schema()
        result = self.linker.link(
            "Find all employees in Engineering.",
            target_schema=schema,
        )
        table_names = [t.name for t in result.tables]
        self.assertIn("employees", table_names)
        self.assertIn("departments", table_names)

        col_refs = [f"{c.table}.{c.column}" for c in result.columns]
        self.assertIn("employees.name", col_refs)
        self.assertIn("employees.department_id", col_refs)
        self.assertIn("departments.department_name", col_refs)
        self.assertIn("departments.department_id", col_refs)

        rel_pairs = {(r.from_table, r.to_table) for r in result.relationships}
        self.assertIn(("employees", "departments"), rel_pairs)

        prompt = result.to_member3_prompt()
        self.assertIn("TABLE employees", prompt)
        self.assertIn("TABLE departments", prompt)
        self.assertIn("employees.department_id -> departments.department_id", prompt)

    def test_section13_question2_highest_employees(self):
        """'Which department has the highest number of employees?' -> count + ranking."""
        schema = self.company_db.get_schema()
        result = self.linker.link(
            "Which department has the highest number of employees?",
            target_schema=schema,
        )
        table_names = [t.name for t in result.tables]
        self.assertIn("departments", table_names)
        self.assertIn("employees", table_names)

        self.assertIn(result.intent.type, ("count", "ranking"))
        self.assertIn("maximum", result.intent.operations)

        rel_pairs = {(r.from_table, r.to_table) for r in result.relationships}
        self.assertIn(("employees", "departments"), rel_pairs)

    def test_section13_question3_average_salary_per_department(self):
        """'What is the average salary of employees in each department?' -> aggregation + grouping."""
        schema = self.company_db.get_schema()
        result = self.linker.link(
            "What is the average salary of employees in each department?",
            target_schema=schema,
        )
        table_names = [t.name for t in result.tables]
        self.assertIn("departments", table_names)
        self.assertIn("employees", table_names)

        col_refs = [f"{c.table}.{c.column}" for c in result.columns]
        self.assertIn("employees.salary", col_refs)

        self.assertIn("average", result.intent.operations)
        self.assertIn("group_by", result.intent.operations)

        rel_pairs = {(r.from_table, r.to_table) for r in result.relationships}
        self.assertIn(("employees", "departments"), rel_pairs)

    def test_section11_bridge_table_detection(self):
        """Intermediate junction table enrolled_in is identified as a bridge."""
        schema = self.univ_db.get_schema()
        result = self.linker.link(
            "Find all students and their departments.",
            target_schema=schema,
        )
        roles = {t.name: t.role for t in result.tables}
        self.assertEqual(roles.get("students"), "primary")
        self.assertEqual(roles.get("departments"), "primary")
        self.assertEqual(roles.get("enrolled_in"), "bridge")

        # Junction relationships connect to both active primary tables
        rel_pairs = {(r.from_table, r.to_table) for r in result.relationships}
        self.assertIn(("enrolled_in", "students"), rel_pairs)
        self.assertIn(("enrolled_in", "departments"), rel_pairs)

    def test_cli_dynamic_and_spider_mode(self):
        """Verify CLI --db-path and mutual exclusivity with --database."""
        import subprocess
        import sys

        # 1. Valid dynamic query with --db-path
        cmd_valid = [
            sys.executable,
            "-m",
            "schema_linking.link",
            "Find all employees in Engineering",
            "--db-path",
            str(self.company_db_path),
            "--json",
        ]
        proc = subprocess.run(cmd_valid, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"CLI failed: {proc.stderr}")
        self.assertIn('"database": "company_demo"', proc.stdout)

        # 2. Mutually exclusive flag error
        cmd_invalid = [
            sys.executable,
            "-m",
            "schema_linking.link",
            "Test question",
            "--db-path",
            str(self.company_db_path),
            "--database",
            "college_2",
        ]
        proc_err = subprocess.run(cmd_invalid, capture_output=True, text=True)
        self.assertNotEqual(proc_err.returncode, 0)
        self.assertIn("mutually exclusive", proc_err.stderr)



# ---------------------------------------------------------------------------
# Adapter tests
# ---------------------------------------------------------------------------

class TestSQLiteAdapter(unittest.TestCase):
    """Direct tests on SQLiteAdapter and get_adapter factory."""

    DDL = [
        "CREATE TABLE widgets (id INTEGER PRIMARY KEY, color TEXT);"
    ]

    def test_adapter_validate_and_get_schema(self):
        """SQLiteAdapter.validate() and get_schema() work on a valid SQLite file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "widgets.sqlite"
            _make_sqlite(db_path, self.DDL)
            adapter = SQLiteAdapter(db_path)
            adapter.validate()
            schema = adapter.get_schema()
            self.assertEqual(schema["database_name"], "widgets")
            table_names = [t["table_name"] for t in schema["tables"]]
            self.assertIn("widgets", table_names)

    def test_adapter_is_database_adapter_subclass(self):
        """SQLiteAdapter is a DatabaseAdapter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "x.db"
            _make_sqlite(db_path, self.DDL)
            adapter = SQLiteAdapter(db_path)
            self.assertIsInstance(adapter, DatabaseAdapter)

    def test_get_adapter_factory(self):
        """get_adapter() returns an SQLiteAdapter for .db / .sqlite / .sqlite3."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for suffix in (".db", ".sqlite", ".sqlite3"):
                db_path = Path(tmpdir) / f"x{suffix}"
                _make_sqlite(db_path, self.DDL)
                adapter = get_adapter(db_path)
                self.assertIsInstance(adapter, SQLiteAdapter)

    def test_get_adapter_unsupported_raises(self):
        """get_adapter() raises ValueError for unsupported extensions."""
        from database_retrieval.adapter import get_adapter
        with self.assertRaises(ValueError):
            get_adapter("/path/to/some.csv")

    def test_schema_caching(self):
        """SQLiteAdapter.get_schema() caches result — two calls return same object."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cache.db"
            _make_sqlite(db_path, self.DDL)
            adapter = SQLiteAdapter(db_path)
            s1 = adapter.get_schema()
            s2 = adapter.get_schema()
            self.assertIs(s1, s2, "get_schema() should return the same cached object")


# ---------------------------------------------------------------------------
# ActiveDatabase tests
# ---------------------------------------------------------------------------

class TestActiveDatabase(unittest.TestCase):
    """Tests for ActiveDatabase dataclass."""

    DDL = [
        "CREATE TABLE cats (id INTEGER PRIMARY KEY, name TEXT);"
    ]

    def test_active_database_properties(self):
        """ActiveDatabase exposes correct name, type, and table list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "petstore.db"
            _make_sqlite(db_path, self.DDL)
            db = load_database(db_path)
            self.assertEqual(db.database_name, "petstore")
            self.assertEqual(db.database_type, "sqlite")
            self.assertIn("cats", db.table_names)
            self.assertEqual(db.total_tables, 1)

    def test_active_database_to_dict(self):
        """ActiveDatabase.to_dict() includes expected keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "petstore.db"
            _make_sqlite(db_path, self.DDL)
            db = load_database(db_path)
            d = db.to_dict()
            for key in ("path", "database_name", "database_type", "schema"):
                self.assertIn(key, d)
            self.assertEqual(d["database_type"], "sqlite")

    def test_get_schema_returns_standard_format(self):
        """ActiveDatabase.get_schema() produces the standard Member-1 schema dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "petstore.db"
            _make_sqlite(db_path, self.DDL)
            db = load_database(db_path)
            schema = db.get_schema()
            for key in ("database_name", "total_tables", "tables", "relationships"):
                self.assertIn(key, schema)


if __name__ == "__main__":
    unittest.main()
