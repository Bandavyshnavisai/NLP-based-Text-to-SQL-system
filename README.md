# NLP-based Text-to-SQL System

An end-to-end Natural Language Processing system that translates user questions in plain English into executable SQL queries.

---

## 📁 Project Structure

```text
NLP-based-Text-to-SQL-system/
│
├── databases/                       # 166 Spider SQLite databases + schema files
├── database_retrieval/              # MEMBER 1: Database Management & Retrieval
│   ├── __init__.py                  # Exports SchemaExtractor, CatalogBuilder, DatabaseRetriever
│   ├── schema_extractor.py          # Extracts structured schema from SQLite databases
│   ├── catalog_builder.py           # Builds + persists the searchable Spider schema catalog
│   ├── retriever.py                 # TF-IDF retriever: ranks databases given a NL question
│   ├── retrieve.py                  # CLI entry point  (python -m database_retrieval.retrieve)
│   ├── MEMBER1_HANDOFF.md           # Handoff document for Member 2 (schema linking)
│   ├── spider_catalog.json          # [generated – not in git] schema catalog for all 166 DBs
│   └── spider_tfidf_index.pkl       # [generated – not in git] fitted TF-IDF + vocabulary
├── schema_linking/                  # MEMBER 2: Query Understanding & Schema Linking
│   ├── __init__.py                  # Exports SchemaLinker, QueryUnderstanding, Models, Normalizers
│   ├── normalizer.py                # Tokenization, singularization, query keyword preservation
│   ├── query_understanding.py       # Intent classification, entity, operation & condition extraction
│   ├── models.py                    # Structured dataclasses and serialization models
│   ├── linker.py                    # Table/column matching, bridge-table detection, relationship graph
│   ├── link.py                      # CLI entry point  (python -m schema_linking.link)
│   └── test_schema_linking.py       # 20 unit tests covering Member 2 functionality
├── evaluation/
│   ├── __init__.py
│   ├── test_schema_extractor.py     # 8 unit tests for SchemaExtractor (Member 1)
│   ├── test_retriever.py            # 17 unit tests for CatalogBuilder & Retriever (Member 1)
│   ├── test_integration.py          # 7 Member 1 → Member 2 contract tests
│   ├── test_schema_linking_integration.py # 4 end-to-end integration tests (Member 1 + Member 2)
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
- The 166 Spider SQLite databases placed under `databases/`  
  (Official source: [Yale-Lily Spider](https://yale-lily.github.io/spider))

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

### 3. Build the retrieval index (one-time setup)
```bash
python -m database_retrieval.retrieve --build-index
```
This scans all 166 databases, extracts schemas, writes `spider_catalog.json`, and fits + saves the TF-IDF index. To force a catalog rebuild from scratch (e.g. after adding new databases):
```bash
python -m database_retrieval.retrieve --build-index --rebuild-catalog
```

---

## 📌 Modules Overview

### `database_retrieval/` — Database Management & Retrieval (Member 1)

Extracts structured relational metadata from SQLite databases and ranks database schemas given a natural language query using TF-IDF and cosine similarity.

- **`schema_extractor.py`**: Extracts tables, columns, data types, single/composite primary keys, single/composite foreign keys, and inter-table relationships.
- **`catalog_builder.py`**: Builds `spider_catalog.json` containing rich metadata and token-friendly textual representations.
- **`retriever.py`**: Provides Top-K database retrieval with match hints (`matched_tables`, `matched_columns`).

**Python API:**
```python
from database_retrieval import DatabaseRetriever

retriever = DatabaseRetriever()
retriever.load_index()

results = retriever.retrieve("What are the names of students enrolled in CS?", top_k=5)
```

**CLI:**
```bash
python -m database_retrieval.retrieve "What are the names of students enrolled in CS?" --top-k 5
```

---

### `schema_linking/` — Query Understanding & Schema Linking (Member 2)

Performs deterministic, explainable query understanding and maps question concepts directly to database tables, columns, and foreign key relationships.

#### 1. Query Normalization (`normalizer.py`)
- Lowercasing, whitespace collapsing, punctuation stripping.
- Deterministic morphological singularization (`"singers"` → `"singer"`, `"stadiums"` → `"stadium"`, `"cities"` → `"city"`).
- Query keyword preservation: preserves operational words (`most`, `highest`, `lowest`, `maximum`, `average`, `count`, `between`, `before`, `after`, etc.).
- Multi-token n-gram extraction for compound schema identifiers.

#### 2. Query Understanding (`query_understanding.py`)
- **Intent classification**: `count`, `ranking`, `aggregation`, `filtering`, `retrieval`.
- **Entity extraction**: domain concept candidates (`["stadium", "concert"]`, `["singer", "name"]`).
- **Operation extraction**: aggregations (`count`, `max`, `min`, `avg`, `sum`), orderings (`ascending`, `descending`), comparisons (`greater_than`, `less_than`, `equal`, `between`).
- **Condition extraction**: string literals, numeric constants, and prepositional filter phrases (e.g., `'computer science'`).

#### 3. Table Linking (`linker.py`)
Calculates explainable relevance scores for every table in the retrieved database using:
- Exact schema-name match ($1.00$)
- Normalized singular/plural match ($0.95$)
- Entity & compound multi-word match ($0.92$)
- Synonym matching ($0.85$)
- Junction entity overlap ($0.88$)
- Member 1 hint boost ($0.70$)
- Column evidence boost ($0.65$)
- Assigns roles: `primary` (directly asked/relevant) vs. `bridge` (junction path).

#### 4. Bridge / Junction Table Detection & Relationship Graph
- Constructs an undirected graph of foreign key relationships.
- Uses Breadth-First Search (BFS) shortest-path traversal between all primary tables.
- Identifies intermediate junction/bridge tables (e.g., `singer_in_concert` between `singer` and `concert`, or `enrolled_in` between `student` and `department`).
- Preserves single and composite foreign keys (`source_columns`, `target_columns`).

#### 5. Column Linking
- Matches query tokens/synonyms to table columns.
- Automatically includes primary key columns of active tables.
- Automatically includes foreign key join columns needed for connecting relationships.
- Maps condition values to candidate filter columns.

#### 6. Structured Hand-Off for Member 3
Produces structured machine-readable objects and clean textual schema prompts for Member 3 (Text-to-SQL generation).

**Python API:**
```python
from schema_linking import SchemaLinker

linker = SchemaLinker()

# 1. Full pipeline (Retriever -> Schema Linking)
result = linker.link("Which stadium has hosted the most concerts?")

# 2. Known database linking
result = linker.link("What are the names of singers?", target_db="concert_singer")

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
print(prompt_schema)
```

**Member 2 CLI:**
```bash
# Human-readable summary
python -m schema_linking.link "Which stadium has hosted the most concerts?"

# JSON output
python -m schema_linking.link "What are the names of singers?" --json

# Target database override
python -m schema_linking.link "Find students in CS." --database college_2

# Member 3 prompt format
python -m schema_linking.link "Which stadium has hosted the most concerts?" --prompt
```

---

## 📊 Evaluation

### Member 1: Database Retrieval Evaluation
```bash
python -m evaluation.eval_retrieval --split dev
```

| Metric | Accuracy (Spider Dev Set - 1,034 questions) |
|--------|---------------------------------------------|
| Top-1  | **67.99%** (703 / 1034)                     |
| Top-3  | **84.14%** (870 / 1034)                     |
| Top-5  | **89.56%** (926 / 1034)                     |

---

### Member 2: Schema Linking Evaluation
Evaluated against ground truth schema elements extracted from Spider gold SQL queries:

```bash
# Evaluate Schema Linking given target database (isolates Member 2)
python -m evaluation.eval_schema_linking --split dev --use-gold-db

# Evaluate end-to-end pipeline (Retriever + Schema Linker)
python -m evaluation.eval_schema_linking --split dev
```

#### Results on Full Spider Dev Set (1,034 examples):

| Metric Component | Gold DB Provided | Full Pipeline (Retriever + Linker) |
|------------------|------------------|------------------------------------|
| **Table Linking Recall** | **91.88%** | **68.09%** |
| **Table Linking Precision** | **78.88%** | **57.18%** |
| **Table Linking F1** | **81.53%** | **59.71%** |
| **Table Coverage Accuracy** | **86.56%** | **64.02%** |
| **Column Linking Recall** | **91.04%** | **73.89%** |
| **Column Coverage Accuracy** | **86.46%** | **71.28%** |
| **Relationship Recall** | **90.10%** | **85.41%** |
| **Relationship Coverage** | **89.65%** | **85.11%** |
| **Overall Schema Coverage** | **76.98%** | **57.06%** |

---

## 🧪 Running Tests

Run the complete test suite (56 tests across Member 1 and Member 2):

```bash
# Run all tests
python -m pytest -v

# Run Member 1 tests
python -m pytest evaluation/test_schema_extractor.py database_retrieval/test_retriever.py evaluation/test_integration.py -v

# Run Member 2 unit tests
python -m pytest schema_linking/test_schema_linking.py -v

# Run Member 1 -> Member 2 end-to-end integration tests
python -m pytest evaluation/test_schema_linking_integration.py -v
```

**Test suite summary:** 56 passed, 0 failed ✅

---

## 🔧 Team Responsibilities

- **Member 1 (Database Management & Retrieval)**: `databases/`, `database_retrieval/`, `evaluation/eval_retrieval.py`
- **Member 2 (Query Understanding & Schema Linking)**: `schema_linking/`, `evaluation/eval_schema_linking.py`, `evaluation/test_schema_linking_integration.py`
- **Member 3 (Text-to-SQL Model & Fine-Tuning)**: Consumes Member 2 `SchemaLinkingResult` and `member3_prompt_schema` to generate SQL
- **Member 4 (SQL Validation, Self-Debugging & Execution)**: Validates, debugs, and executes generated SQL against SQLite databases
