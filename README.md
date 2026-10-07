# NLP-based Text-to-SQL System

An end-to-end Natural Language Processing system that translates user questions in plain English into executable SQL queries.

The system supports **two distinct operational modes**:

| Mode | Input | Use case |
|------|-------|----------|
| **Spider Benchmark Mode** | One of 166 Spider SQLite databases | Research, evaluation, benchmarking |
| **Dynamic User Database Mode** | Any user-supplied SQLite file | Production use with custom databases |

> **Note:** Dynamic user databases currently support **SQLite only** (`.db`, `.sqlite`, `.sqlite3`). PostgreSQL, MySQL, and other engines are not yet supported, but the adapter architecture makes future integration straightforward.

---

## 📁 Project Structure

```text
NLP-based-Text-to-SQL-system/
│
├── databases/                       # 166 Spider SQLite databases + schema files
├── database_retrieval/              # MEMBER 1: Database Management & Retrieval
│   ├── __init__.py                  # Exports all Mode 1 + Mode 2 classes
│   ├── schema_extractor.py          # Extracts structured schema from any SQLite database
│   ├── catalog_builder.py           # Builds + persists the searchable Spider schema catalog
│   ├── retriever.py                 # TF-IDF retriever: ranks 166 Spider databases
│   ├── retrieve.py                  # CLI (python -m database_retrieval.retrieve)
│   ├── loader.py                    # [NEW] load_database() — Dynamic Mode entry point
│   ├── active_database.py           # [NEW] ActiveDatabase dataclass
│   ├── adapter.py                   # [NEW] DatabaseAdapter ABC + SQLiteAdapter
│   ├── inspect_db.py                # [NEW] CLI (python -m database_retrieval.inspect_db)
│   ├── MEMBER1_HANDOFF.md           # Handoff document for Member 2
│   ├── spider_catalog.json          # [generated – not in git] schema catalog for all 166 DBs
│   └── spider_tfidf_index.pkl       # [generated – not in git] fitted TF-IDF + vocabulary
├── schema_linking/                  # MEMBER 2: Query Understanding & Schema Linking
│   ├── __init__.py                  # Exports SchemaLinker, QueryUnderstanding, Models, Normalizers
│   ├── normalizer.py                # Tokenization, singularization, query keyword preservation
│   ├── query_understanding.py       # Intent classification, entity, operation & condition extraction
│   ├── models.py                    # Structured dataclasses and serialization models
│   ├── linker.py                    # Table/column matching, bridge-table detection, relationship graph
│   ├── link.py                      # CLI (python -m schema_linking.link) — supports both modes
│   └── test_schema_linking.py       # 20 unit tests covering Member 2 functionality
├── tests/
│   └── test_dynamic_database.py    # [NEW] 32 tests for Dynamic User Database Mode
├── evaluation/
│   ├── __init__.py
│   ├── test_schema_extractor.py     # 8 unit tests for SchemaExtractor (Member 1)
│   ├── test_retriever.py            # 17 unit tests for CatalogBuilder & Retriever (Member 1)
│   ├── test_integration.py          # 7 Member 1 → Member 2 contract tests
│   ├── test_schema_linking_integration.py # 4 end-to-end integration tests
│   ├── eval_retrieval.py            # Member 1 retrieval evaluation on Spider
│   └── eval_schema_linking.py       # Member 2 schema linking evaluation on Spider
├── README.md
├── requirements.txt
└── .gitignore
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.9+

**For Spider Benchmark Mode only:**
- The 166 Spider SQLite databases placed under `databases/`
  (Official source: [Yale-Lily Spider](https://yale-lily.github.io/spider))

**For Dynamic User Database Mode:**
- Any valid SQLite file (`.db`, `.sqlite`, or `.sqlite3`)

### 2. Installation
```bash
git clone https://github.com/Bandavyshnavisai/NLP-based-Text-to-SQL-system.git
cd NLP-based-Text-to-SQL-system
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Build the retrieval index (Spider Mode only — one-time setup)
```bash
python -m database_retrieval.retrieve --build-index
```
This scans all 166 databases, extracts schemas, writes `spider_catalog.json`, and fits + saves the TF-IDF index. To force a catalog rebuild from scratch:
```bash
python -m database_retrieval.retrieve --build-index --rebuild-catalog
```

---

## 🗂️ Two Operational Modes

### Mode 1 — Spider Benchmark Mode

```
Spider Question (dev.json / train_spider.json)
        ↓
DatabaseRetriever.retrieve(question, top_k=5)   ← TF-IDF over 166 Spider DBs
        ↓
Ranked list of Spider databases + matched tables/columns
        ↓
SchemaLinker.link(question, target_db="concert_singer")
        ↓
SchemaLinkingResult → Member 3 prompt
```

**Use this mode for:** research, reproducibility, evaluation on Spider benchmark.

### Mode 2 — Dynamic User Database Mode

```
User uploads any .db / .sqlite / .sqlite3 file
        ↓
load_database(path)                             ← validate + extract schema
        ↓
ActiveDatabase  (path, name, type, schema)
        ↓
SchemaLinker.link(question, target_schema=db.get_schema())
        ↓
SchemaLinkingResult → Member 3 prompt
```

**Use this mode for:** real-world deployments with custom databases.

No Spider metadata required. No database catalog. No TF-IDF index.

---

## 📌 Modules Overview

### `database_retrieval/` — Database Management & Retrieval (Member 1)

#### Mode 1 (Spider Benchmark) components

- **`schema_extractor.py`**: Extracts tables, columns, data types, single/composite primary keys, single/composite foreign keys, and inter-table relationships from **any** SQLite file.
- **`catalog_builder.py`**: Builds `spider_catalog.json` containing rich metadata for all 166 Spider databases.
- **`retriever.py`**: Top-K database retrieval with match hints (`matched_tables`, `matched_columns`).

```python
from database_retrieval import DatabaseRetriever

retriever = DatabaseRetriever()
retriever.load_index()
results = retriever.retrieve("What are the names of students enrolled in CS?", top_k=5)
```

```bash
python -m database_retrieval.retrieve "What are the names of students enrolled in CS?" --top-k 5
```

#### Mode 2 (Dynamic Database) components — NEW

- **`loader.py`** — `load_database(path)` validates and loads any SQLite file.
- **`active_database.py`** — `ActiveDatabase` wraps the path, name, type, and extracted schema.
- **`adapter.py`** — `DatabaseAdapter` ABC + `SQLiteAdapter` (foundation for future engine adapters).
- **`inspect_db.py`** — CLI for inspecting any SQLite database and optionally running schema linking.

```python
from database_retrieval import load_database

# Load and validate any SQLite database
db = load_database("C:/path/to/company.db")

print(db.database_name)   # "company"
print(db.table_names)     # ["departments", "employees"]
print(db.total_tables)    # 2

# Pass schema directly to SchemaLinker
from schema_linking import SchemaLinker
linker = SchemaLinker()
result = linker.link(
    "What is the average salary of employees?",
    target_schema=db.get_schema(),
)
```

```bash
# Inspect schema only
python -m database_retrieval.inspect_db "C:\path\company.db"

# Inspect schema + run schema linking on a question
python -m database_retrieval.inspect_db "C:\path\company.db" \
    --question "What is the average salary of employees?"

# JSON output
python -m database_retrieval.inspect_db "C:\path\company.db" \
    --question "List all departments" --json
```

**Validation rules enforced by `load_database()`:**
1. File must exist.
2. Extension must be `.db`, `.sqlite`, or `.sqlite3`.
3. File must be a valid SQLite database (checked via header magic bytes).
4. Database must contain at least one user table (non-`sqlite_*`).
5. Access is **always read-only** — the user's database is never modified.

---

### `schema_linking/` — Query Understanding & Schema Linking (Member 2)

Performs deterministic, explainable query understanding and maps question concepts to database tables, columns, and foreign key relationships. **Works with both Spider and user-supplied schemas.**

#### Query Normalization (`normalizer.py`)
- Lowercasing, whitespace collapsing, punctuation stripping.
- Deterministic morphological singularization (`"singers"` → `"singer"`, `"stadiums"` → `"stadium"`).
- Query keyword preservation: preserves `most`, `highest`, `average`, `count`, etc.
- Multi-token n-gram extraction for compound schema identifiers.

#### Query Understanding (`query_understanding.py`)
- **Intent classification**: `count`, `ranking`, `aggregation`, `filtering`, `retrieval`.
- **Entity extraction**: domain concept candidates.
- **Operation extraction**: aggregations, orderings, comparisons.
- **Condition extraction**: string literals, numeric constants, filter phrases.

#### Schema Linking (`linker.py`)
- Explainable table relevance scores (exact match 1.0 → synonym match 0.85 → token overlap 0.50–0.80).
- Bridge/junction table detection via BFS on the FK graph.
- Column linking (exact, synonym, condition, FK/PK inclusion).
- **Works with any schema dict** — Spider or user-provided.

**Python API:**
```python
from schema_linking import SchemaLinker

linker = SchemaLinker()

# Mode 1: Spider pipeline (retrieval → linking)
result = linker.link("Which stadium has hosted the most concerts?")

# Mode 1: Spider known-DB shortcut
result = linker.link("What are the names of singers?", target_db="concert_singer")

# Mode 2: Dynamic DB (no Spider required)
from database_retrieval import load_database
db = load_database("company.db")
result = linker.link("What is the average salary?", target_schema=db.get_schema())

# Access structured fields
print("Database:", result.database)
print("Intent:", result.intent.type, result.intent.operations)
print("Tables:", [(t.name, t.role, t.score) for t in result.tables])
print("Columns:", [(c.table, c.column, c.reason) for c in result.columns])
print("Relationships:", [(r.from_table, r.to_table) for r in result.relationships])

# JSON serialization
json_output = result.to_json(indent=2)

# Textual prompt for Member 3
prompt_schema = result.to_member3_prompt()
```

**CLI:**
```bash
# Mode 1: Spider pipeline
python -m schema_linking.link "Which stadium has hosted the most concerts?"

# Mode 1: Target Spider database
python -m schema_linking.link "Find students in CS." --database college_2

# Mode 2: Dynamic user database (no Spider metadata needed)
python -m schema_linking.link "What is the average salary?" --db-path company.db

# JSON output (either mode)
python -m schema_linking.link "What are the names of singers?" --json

# Member 3 prompt format (either mode)
python -m schema_linking.link "Which stadium has hosted the most concerts?" --prompt
```

---

## 📊 Evaluation

### Member 1: Database Retrieval (Spider Benchmark)
```bash
python -m evaluation.eval_retrieval --split dev
```

| Metric | Accuracy (Spider Dev Set — 1,034 questions) |
|--------|---------------------------------------------|
| Top-1  | **67.99%** (703 / 1034)                     |
| Top-3  | **84.14%** (870 / 1034)                     |
| Top-5  | **89.56%** (926 / 1034)                     |

### Member 2: Schema Linking (Spider Benchmark)
```bash
# Known-DB evaluation (isolates Member 2)
python -m evaluation.eval_schema_linking --split dev --use-gold-db

# Full pipeline evaluation (Retriever + Schema Linker)
python -m evaluation.eval_schema_linking --split dev
```

| Metric Component | Gold DB Provided | Full Pipeline |
|------------------|------------------|---------------|
| **Table Linking Recall** | **91.88%** | **68.09%** |
| **Table Linking Precision** | **78.88%** | **57.18%** |
| **Table Linking F1** | **81.53%** | **59.71%** |
| **Table Coverage Accuracy** | **86.56%** | **64.02%** |
| **Column Linking Recall** | **91.04%** | **73.89%** |
| **Column Coverage Accuracy** | **86.46%** | **71.28%** |
| **Relationship Recall** | **90.10%** | **85.41%** |
| **Overall Schema Coverage** | **76.98%** | **57.06%** |

---

## 🧪 Running Tests

```bash
# Run all tests (88 tests)
python -m pytest -v

# Member 1 tests (Spider)
python -m pytest evaluation/test_schema_extractor.py database_retrieval/test_retriever.py evaluation/test_integration.py -v

# Member 2 unit tests
python -m pytest schema_linking/test_schema_linking.py -v

# Member 1 → Member 2 end-to-end integration tests (Spider)
python -m pytest evaluation/test_schema_linking_integration.py -v

# Dynamic User Database Mode tests (no Spider required)
python -m pytest tests/test_dynamic_database.py -v
```

**Test suite summary:** 88 passed, 0 failed ✅

| Test module | Tests | Covers |
|-------------|-------|--------|
| `evaluation/test_schema_extractor.py` | 8 | Schema extraction correctness |
| `database_retrieval/test_retriever.py` | 17 | Catalog builder + retriever |
| `evaluation/test_integration.py` | 7 | Member 1 → Member 2 contract |
| `schema_linking/test_schema_linking.py` | 20 | Member 2 unit tests |
| `evaluation/test_schema_linking_integration.py` | 4 | End-to-end Spider pipeline |
| `tests/test_dynamic_database.py` | 32 | Dynamic User Database Mode |

---

## 🔧 Team Responsibilities

- **Member 1 (Database Management & Retrieval)**: `databases/`, `database_retrieval/`, `evaluation/eval_retrieval.py`
- **Member 2 (Query Understanding & Schema Linking)**: `schema_linking/`, `evaluation/eval_schema_linking.py`, `evaluation/test_schema_linking_integration.py`
- **Member 3 (Text-to-SQL Model & Fine-Tuning)**: Consumes `SchemaLinkingResult` and `member3_prompt_schema` to generate SQL
- **Member 4 (SQL Validation, Self-Debugging & Execution)**: Validates, debugs, and executes generated SQL against SQLite databases

---

## 🗺️ Database Support

| Engine | Status | How to use |
|--------|--------|------------|
| **SQLite** | ✅ Full support | `load_database("file.db")` |
| PostgreSQL | 🚧 Planned | Future `PostgreSQLAdapter` |
| MySQL | 🚧 Planned | Future `MySQLAdapter` |
| SQL Server | 🚧 Planned | Future `SQLServerAdapter` |

The `DatabaseAdapter` abstract base class in `database_retrieval/adapter.py` defines the extension contract. New adapters implement `validate()` and `get_schema()` — schema linking and text-to-SQL stages remain unchanged.

---

## 🔧 Team Responsibilities

- **Member 1 (Database Management & Retrieval)**: `databases/`, `database_retrieval/`, `evaluation/eval_retrieval.py`
- **Member 2 (Query Understanding & Schema Linking)**: `schema_linking/`, `evaluation/eval_schema_linking.py`, `evaluation/test_schema_linking_integration.py`
- **Member 3 (Text-to-SQL Model & Fine-Tuning)**: Consumes `SchemaLinkingResult` and `member3_prompt_schema` to generate SQL
- **Member 4 (SQL Validation, Self-Debugging & Execution)**: Validates, debugs, and executes generated SQL against SQLite databases
