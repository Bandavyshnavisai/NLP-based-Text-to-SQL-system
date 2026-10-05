# NLP-based Text-to-SQL System

An end-to-end Natural Language Processing system that translates user questions in plain English into executable SQL queries.

---

## 📁 Project Structure

```text
NLP-based-Text-to-SQL-system/
│
├── databases/                       # 166 Spider SQLite databases + schema files
├── database_retrieval/
│   ├── __init__.py                  # Exports SchemaExtractor, CatalogBuilder, DatabaseRetriever
│   ├── schema_extractor.py          # Extracts structured schema from SQLite databases
│   ├── catalog_builder.py           # Builds + persists the searchable Spider schema catalog
│   ├── retriever.py                 # TF-IDF retriever: ranks databases given a NL question
│   ├── retrieve.py                  # CLI entry point  (python -m database_retrieval.retrieve)
│   ├── spider_catalog.json          # [generated – not in git] schema catalog for all 166 DBs
│   └── spider_tfidf_index.pkl       # [generated – not in git] fitted TF-IDF + vocabulary
├── evaluation/
│   ├── __init__.py
│   ├── test_schema_extractor.py     # 8 unit tests for SchemaExtractor
│   └── eval_retrieval.py            # Retrieval accuracy evaluation using Spider splits
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
This scans all 166 databases, extracts schemas, writes `spider_catalog.json`, and fits + saves the TF-IDF index.  To force a catalog rebuild from scratch (e.g. after adding new databases):
```bash
python -m database_retrieval.retrieve --build-index --rebuild-catalog
```

---

## 📌 Modules Overview

### `database_retrieval/schema_extractor.py` — Schema Extraction
Extracts structured relational metadata from each SQLite database using `sqlite3` PRAGMAs:
- Database name, all non-system tables
- Columns, data types, NOT NULL constraints, default values
- Single and composite primary keys (ordered correctly)
- Single and composite foreign keys (reconstructed from `PRAGMA foreign_key_list`)
- Full table relationship map

**Python API:**
```python
from database_retrieval import SchemaExtractor

extractor = SchemaExtractor()
schema = extractor.extract_by_name("concert_singer")
print(schema["tables"])        # table list with columns, PKs, FKs
print(schema["relationships"]) # cross-table FK relationships
```

**CLI:**
```bash
python -m database_retrieval.schema_extractor --db-name concert_singer
python -m database_retrieval.schema_extractor --test   # tests on 4 sample databases
```

---

### `database_retrieval/catalog_builder.py` — Schema Catalog
Iterates over all 166 Spider databases, calls `SchemaExtractor`, and builds a JSON catalog where each entry contains:
- `database_name`, `total_tables`
- Full `tables` metadata (columns, PKs, FKs)
- `relationships`
- `all_tables`, `all_columns` (flat lists for fast matching)
- `schema_text` — a structured flat text representation used by the TF-IDF retriever

**Python API:**
```python
from database_retrieval import CatalogBuilder

builder = CatalogBuilder()
catalog = builder.build_and_save()   # writes spider_catalog.json
catalog = builder.load_catalog()     # fast load from disk
```

---

### `database_retrieval/retriever.py` — Database Retrieval

Given a natural-language question, retrieves and ranks the most relevant Spider database(s).

**How it works:**
1. **Catalog**: All 166 database schemas are represented as structured `schema_text` strings containing the database name (boosted), table names, column names, types, and relationship phrases.
2. **Stemming**: Both the schema texts and query are stemmed using NLTK's `SnowballStemmer(english)`, so inflected words like "singers" → "singer", "flights" → "flight" correctly match schema tokens.
3. **TF-IDF**: A `TfidfVectorizer` with `ngram_range=(1,2)` and `sublinear_tf=True` is fitted over all stemmed schema texts.
4. **Cosine Similarity**: At retrieval time, the stemmed question is vectorized and cosine similarity is computed against all 166 database vectors. Results are ranked by descending similarity.
5. **Match Attribution**: Matched table names and column names are identified via token overlap between the question and schema entries, returned alongside each result.

**Python API:**
```python
from database_retrieval import DatabaseRetriever

retriever = DatabaseRetriever()
retriever.load_index()   # loads pre-built index from disk

results = retriever.retrieve("What are the names of students enrolled in CS?", top_k=5)
for r in results:
    print(r["rank"], r["database"], r["score"])
    print("  Tables:", r["matched_tables"])
    print("  Columns:", r["matched_columns"])
```

**CLI:**
```bash
python -m database_retrieval.retrieve "What are the names of students enrolled in CS?" --top-k 5
```

**Example output:**
```
Question: What are the names of students enrolled in the computer science department?

1. database: college_3
   score: 0.1857
   matched_tables: ['Department', 'Enrolled_in', 'Member_of', 'Minor_in']

2. database: department_management
   score: 0.0701
   matched_tables: ['department']
   matched_columns: ['department.Department_ID', 'department.department_name']

3. database: student_transcripts_tracking
   score: 0.0625
   matched_tables: ['Students']
   matched_columns: ['Departments.department_id', 'Departments.department_name']
```

---

## 📊 Evaluation

### Run retrieval accuracy evaluation
Uses the official Spider question-to-database mappings (`dev.json`, `train_spider.json`).

```bash
# Evaluate on the Spider dev split (1034 questions)
python -m evaluation.eval_retrieval --split dev

# Evaluate on a random sample of 500 train questions
python -m evaluation.eval_retrieval --split train --sample 500
```

### Retrieval accuracy results (TF-IDF + stemming, Spider dev set)

| Metric       | Accuracy  |
|-------------|-----------|
| Top-1        | **67.99%** (703/1034) |
| Top-3        | **84.14%** (870/1034) |
| Top-5        | **89.56%** (926/1034) |

> These metrics are computed on the full Spider dev set (1034 questions across 20 databases).

---

## 🧪 Running Tests

```bash
# All tests (schema extraction + retrieval)
python -m pytest evaluation/test_schema_extractor.py database_retrieval/test_retriever.py -v

# Schema extraction tests only
python -m pytest evaluation/test_schema_extractor.py -v

# Retrieval tests only
python -m pytest database_retrieval/test_retriever.py -v
```

**Current test results:** 10 passed ✅

---

## 🔧 Member Responsibilities

- **Member 1 (Database Management & Retrieval)**: `databases/`, `database_retrieval/`, `evaluation/`
- **Member 2 (Schema Linking)**: Consumes `DatabaseRetriever.retrieve()` output to link schema elements to the SQL query
- **Member 3+ (Text-to-SQL Model & Validation)**: Downstream pipeline components
