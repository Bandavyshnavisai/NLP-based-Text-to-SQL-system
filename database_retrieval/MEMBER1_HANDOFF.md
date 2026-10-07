# Member 1 Handoff — Database Management & Retrieval

**For:** Member 2 (Schema Linking)  
**From:** Member 1 (Database Management & Retrieval)  
**Status:** Complete ✅ — all 32 tests passing, pushed to `main`

---

## 1. What Member 1 Provides

Member 1 delivers three production-ready components:

| Component | File | What it does |
|-----------|------|--------------|
| `SchemaExtractor` | `database_retrieval/schema_extractor.py` | Extracts full relational schema from any SQLite database |
| `CatalogBuilder` | `database_retrieval/catalog_builder.py` | Builds + persists a JSON catalog of all 166 Spider schemas |
| `DatabaseRetriever` | `database_retrieval/retriever.py` | Given a NL question, ranks all 166 databases by schema relevance |

### Generated artifacts (local only, not in Git)

| File | Description |
|------|-------------|
| `database_retrieval/spider_catalog.json` | Full schema catalog (2 MB) |
| `database_retrieval/spider_tfidf_index.pkl` | Fitted TF-IDF index (binary) |

> Rebuild both at any time with:
> ```bash
> python -m database_retrieval.retrieve --build-index
> ```

---

## 2. Responsibility Boundary

```
┌─────────────────────────────────────────────────────────────────┐
│  MEMBER 1: Database Management & Retrieval                      │
│                                                                 │
│  • Spider SQLite databases (166 databases in databases/)        │
│  • Schema extraction (tables, columns, PKs, FKs, types)        │
│  • Composite key handling                                       │
│  • Database catalog (spider_catalog.json)                       │
│  • TF-IDF + cosine similarity retrieval                         │
│  • Top-K ranked database retrieval                              │
│  • Retrieval evaluation (Top-1/3/5 accuracy)                    │
└────────────────────────┬────────────────────────────────────────┘
                         │  retrieve(question, top_k=5)
                         │  returns: ranked databases + schemas
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  MEMBER 2: Schema Linking  ← handoff point                      │
│                                                                 │
│  • Question understanding                                       │
│  • Relevant table identification                                │
│  • Relevant column identification                               │
│  • Schema linking (question tokens ↔ schema elements)           │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ▼
                  Text-to-SQL Model
```

**Member 1 does NOT do:**
- Question parsing / NLU
- Table selection (schema linking)
- Column selection (schema linking)
- SQL generation

**Member 2 does NOT need to:**
- Touch SQLite files directly
- Run schema extraction
- Know about TF-IDF internals

---

## 3. End-to-End Pipeline

```
User Question
    │
    ▼
DatabaseRetriever.retrieve(question, top_k=5)
    │
    ▼  List[Dict] — ranked candidates with scores, matched tables/columns
    │
    ▼
Select top-1 (or top-K for reranking / fallback)
    │
    ▼
catalog_by_name[top_result["database"]]  ← full schema dict
    │
    ▼
Member 2: Schema Linking
  - Use matched_tables as seed candidates
  - Use matched_columns as seed candidates
  - Refine using schema["tables"], schema["relationships"]
    │
    ▼
Relevant tables + columns
    │
    ▼
Text-to-SQL model
```

---

## 4. Python API for Member 2

### 4a. One-time setup (already done — index is on disk)

```python
from database_retrieval import DatabaseRetriever

retriever = DatabaseRetriever()
retriever.load_index()   # loads spider_tfidf_index.pkl + spider_catalog.json

# Build catalog lookup for schema access
catalog = retriever._catalog
catalog_by_name = {e["database_name"]: e for e in catalog}
```

### 4b. Retrieve for a question

```python
question = "Find the name and capacity of the stadium with the most concerts."

results = retriever.retrieve(question, top_k=5)
```

### 4c. Access the top result

```python
top = results[0]

db_name        = top["database"]         # str  e.g. "concert_singer"
score          = top["score"]            # float e.g. 0.1699
matched_tables = top["matched_tables"]   # List[str] e.g. ["stadium"]
matched_columns= top["matched_columns"]  # List[str] e.g. ["stadium.Capacity", ...]
```

### 4d. Get the full schema for the top database

```python
schema = catalog_by_name[db_name]

# Available keys:
schema["database_name"]   # str
schema["total_tables"]    # int
schema["tables"]          # List[TableDict]  — see §5 for exact structure
schema["relationships"]   # List[RelDict]    — see §5 for exact structure
schema["all_tables"]      # List[str]        — flat list of table names
schema["all_columns"]     # List[str]        — flat list "TableName.ColumnName"
```

---

## 5. Exact Output Format

### 5a. `retrieve()` return — `List[Dict]`

```json
[
  {
    "rank": 1,
    "database": "concert_singer",
    "score": 0.1699,
    "matched_tables": ["stadium"],
    "matched_columns": [
      "concert.concert_Name",
      "concert.Stadium_ID",
      "singer.Name",
      "singer.Song_Name",
      "stadium.Stadium_ID",
      "stadium.Name",
      "stadium.Capacity"
    ]
  },
  {
    "rank": 2,
    "database": "game_injury",
    "score": 0.0818,
    "matched_tables": ["stadium"],
    "matched_columns": ["game.stadium_id", "stadium.name", "stadium.Capacity_Percentage"]
  }
]
```

**Field reference:**

| Field | Type | Description |
|-------|------|-------------|
| `rank` | `int` | 1-indexed rank (1 = most relevant) |
| `database` | `str` | Spider database name / folder name |
| `score` | `float` | Cosine similarity score (0–1) |
| `matched_tables` | `List[str]` | Table names whose tokens overlap with the question |
| `matched_columns` | `List[str]` | `"TableName.ColumnName"` where column tokens overlap with the question |

### 5b. `catalog_by_name[db]["tables"]` — `List[TableDict]`

```json
[
  {
    "table_name": "stadium",
    "columns": [
      {"name": "Stadium_ID", "type": "INT",  "primary_key": true,  "not_null": false, "default_value": null},
      {"name": "Location",   "type": "TEXT", "primary_key": false, "not_null": false, "default_value": null},
      {"name": "Name",       "type": "TEXT", "primary_key": false, "not_null": false, "default_value": null},
      {"name": "Capacity",   "type": "INT",  "primary_key": false, "not_null": false, "default_value": null},
      {"name": "Highest",    "type": "INT",  "primary_key": false, "not_null": false, "default_value": null},
      {"name": "Lowest",     "type": "INT",  "primary_key": false, "not_null": false, "default_value": null},
      {"name": "Average",    "type": "INT",  "primary_key": false, "not_null": false, "default_value": null}
    ],
    "primary_keys": ["Stadium_ID"],
    "is_composite_pk": false,
    "foreign_keys": []
  }
]
```

**Column field reference:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Column name as declared in schema |
| `type` | `str` | SQLite declared type (`TEXT`, `INT`, `REAL`, `INTEGER`, etc.) |
| `primary_key` | `bool` | True if this column is part of the PK |
| `not_null` | `bool` | True if column has NOT NULL constraint |
| `default_value` | `str\|null` | Default value or `null` |

### 5c. `catalog_by_name[db]["relationships"]` — `List[RelDict]`

```json
[
  {
    "source_table": "concert",
    "source_column": "Stadium_ID",
    "target_table": "stadium",
    "target_column": "Stadium_ID",
    "source_columns": ["Stadium_ID"],
    "target_columns": ["Stadium_ID"],
    "is_composite": false
  }
]
```

**Relationship field reference:**

| Field | Type | Description |
|-------|------|-------------|
| `source_table` | `str` | Table containing the FK |
| `source_column` | `str` | FK column name (comma-separated if composite) |
| `target_table` | `str` | Referenced table |
| `target_column` | `str` | Referenced column name |
| `source_columns` | `List[str]` | Individual FK column names (use for composite FK traversal) |
| `target_columns` | `List[str]` | Individual referenced column names |
| `is_composite` | `bool` | True if FK spans multiple columns |

---

## 6. Real CLI Example

```
$ python -m database_retrieval.retrieve \
    "Find the name and capacity of the stadium with the most concerts." \
    --top-k 3

Question: Find the name and capacity of the stadium with the most concerts.

1. database: concert_singer
   score: 0.1699
   matched_tables: ['stadium']
   matched_columns: ['concert.concert_Name', 'concert.Stadium_ID',
                     'singer.Name', 'singer.Song_Name',
                     'stadium.Stadium_ID', 'stadium.Name', 'stadium.Capacity']

2. database: game_injury
   score: 0.0818
   matched_tables: ['stadium']
   matched_columns: ['game.stadium_id', 'stadium.name', 'stadium.Capacity_Percentage']

3. database: gas_company
   score: 0.0792
   matched_tables: []
   matched_columns: ['gas_station.Manager_Name', ...]
```

**Interpretation for Member 2:**
- Use `concert_singer` (rank 1, score 0.1699) as the target database.
- `matched_tables: ["stadium"]` is a strong hint — start schema linking with the `stadium` table.
- `matched_columns` includes `stadium.Name` and `stadium.Capacity`, exactly the columns the question is asking about.

---

## 7. Recommended Member 2 Integration Pattern

```python
from database_retrieval import DatabaseRetriever

# ── One-time setup ───────────────────────────────────────────────
retriever = DatabaseRetriever()
retriever.load_index()
catalog_by_name = {e["database_name"]: e for e in retriever._catalog}

# ── Per-question retrieval ───────────────────────────────────────
def get_schema_for_question(question: str, top_k: int = 5):
    """Member 1 → Member 2 handoff function."""
    results = retriever.retrieve(question, top_k=top_k)

    if not results or results[0]["score"] == 0.0:
        # No confident match — Member 2 may want to handle fallback
        return None, [], []

    top = results[0]
    db_name        = top["database"]
    matched_tables = top["matched_tables"]   # seed candidates for schema linking
    matched_columns= top["matched_columns"]  # seed candidates for column selection

    schema = catalog_by_name[db_name]        # full schema for Member 2

    return schema, matched_tables, matched_columns

# ── Usage ────────────────────────────────────────────────────────
schema, hint_tables, hint_columns = get_schema_for_question(
    "Find the name and capacity of the stadium with the most concerts."
)

# Member 2 now has:
#   schema["tables"]        — all table definitions
#   schema["relationships"] — FK graph for JOIN inference
#   hint_tables             — likely relevant tables
#   hint_columns            — likely relevant columns
```

---

## 8. Evaluation Metrics (for reference)

Evaluated on the official Spider dev set (1,034 questions, 20 databases):

| Metric | Accuracy |
|--------|----------|
| Top-1  | **67.99%** (703/1034) |
| Top-3  | **84.14%** (870/1034) |
| Top-5  | **89.56%** (926/1034) |

> **Note for Member 2:** When Top-1 accuracy is insufficient (e.g. for difficult questions), Member 2 can iterate over `results[1]`, `results[2]`, etc. and score each schema against the question using schema-linking signals.

Re-run evaluation at any time:
```bash
python -m evaluation.eval_retrieval --split dev
python -m evaluation.eval_retrieval --split train --sample 500
```

---

## 9. Test Suite Reference

All tests are run with:
```bash
python -m pytest evaluation/test_schema_extractor.py \
                 database_retrieval/test_retriever.py \
                 evaluation/test_integration.py -v
```

| Test file | Tests | What it covers |
|-----------|-------|----------------|
| `evaluation/test_schema_extractor.py` | 8 | Schema extraction correctness |
| `database_retrieval/test_retriever.py` | 17 | Catalog builder + retriever |
| `evaluation/test_integration.py` | 7 | Member 1 → Member 2 contract |
| **Total** | **32** | All passing ✅ |

---

## 10. Files Member 2 Should Import

```python
# Primary import (Spider Benchmark mode)
from database_retrieval import DatabaseRetriever

# Dynamic User Database Mode (New)
from database_retrieval import load_database, ActiveDatabase

# Optional — direct schema extraction or catalog rebuilding
from database_retrieval import SchemaExtractor, CatalogBuilder
```

Member 2 **does not** need to import `catalog_builder`, `retrieve`, or anything from `evaluation/`.

---

## 11. Dynamic User Database Mode (Generalized Mode)

Member 1 now provides direct ingestion of user-supplied SQLite databases, bypassing Spider-specific catalogs:

```python
from database_retrieval import load_database
from schema_linking.linker import SchemaLinker

# 1. Load any user-provided SQLite database
active_db = load_database("path/to/custom_data.db")

# 2. Extract schema directly
schema = active_db.get_schema()

# 3. Member 2 Schema Linker consumes it directly
linker = SchemaLinker()
result = linker.link("What is the highest salary?", target_schema=schema)
```

### CLI Support
```bash
# Inspect dynamic database schema
python -m database_retrieval.inspect_db path/to/my_database.db

# Schema linking against dynamic database
python -m schema_linking.link "Show all active users" --db-path path/to/my_database.db
```

