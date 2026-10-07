# NLP-Based Text-to-SQL System

Full-stack natural-language-to-SQL application combining the team's Spider schema retrieval/schema-linking code with the FastAPI + Qwen + LoRA backend and React frontend.

## Main features

- Natural-language question → SQLite SQL
- Qwen/Qwen2.5-1.5B-Instruct + `D3v1k4/qwen-nlp-text-to-sql`
- Dynamic upload of `.db`, `.sqlite`, `.sqlite3`
- SQLite read-only validation and execution
- Spider database catalog / TF-IDF retrieval
- Schema linking and query understanding
- **JSON cache for database metadata, schema, schema text, and static retrieval context**
- SHA-256 cache keys so changed database files automatically receive a new cache
- Cache status API and frontend cache status
- Colab + ngrok workflow
- Secrets and local database files excluded from Git

## JSON caching

The cache is created the first time a SQLite database is processed.

For a database whose SHA-256 is:

```text
abc123...
```

the files are stored under:

```text
cache/database_cache/abc123.../
├── metadata.json
├── schema.json
├── schema_text.json
└── retrieval.json
```

### What each file contains

`metadata.json`
- SHA-256
- source filename/path
- file size
- modification timestamp
- database name/type
- cache version
- confirmation that rows are not cached

`schema.json`
- tables
- columns
- data types
- primary keys
- foreign keys
- relationships

`schema_text.json`
- the tokenisation-friendly schema text used by the model/retrieval layer

`retrieval.json`
- database name
- table/column lists
- relationships
- cached schema text

**No table rows are stored in the JSON cache.**

The cache is ignored by Git because it is runtime data and can contain information derived from a user's private database.

## How caching works

### First upload

```text
Upload SQLite
     ↓
Validate SQLite
     ↓
SHA-256
     ↓
Cache exists?
     ↓
NO
     ↓
Extract metadata/schema
     ↓
Create schema text
     ↓
Create retrieval context
     ↓
Write 4 JSON files
```

### Subsequent query

```text
User question
     ↓
Database SHA-256
     ↓
Load existing JSON cache
     ↓
Use cached schema/schema text
     ↓
Qwen generates SQL
     ↓
Validate SQL
     ↓
Execute read-only SQL
```

The expensive database/schema preparation is therefore not repeated for every question.

### Changed database

If the database changes:

```text
old database → SHA-256 A → cache/A/
modified DB  → SHA-256 B → cache/B/
```

A stale cache is not reused.

## How to verify caching

### Method 1 — Check the filesystem

After uploading a database and processing it, look in:

```text
<project-root>/cache/database_cache/
```

You should see a directory whose name is a long SHA-256 hash.

Inside it:

```text
metadata.json
schema.json
schema_text.json
retrieval.json
```

Open `metadata.json` and confirm the `sha256` matches the database.

### Method 2 — Use the API

After selecting a database, open:

```text
GET /cache?database=<database-id>
```

For example:

```text
http://127.0.0.1:8000/cache?database=demo
```

The response reports:

```json
{
  "cache_exists": true,
  "cache_dir": ".../cache/database_cache/...",
  "files": {
    "metadata.json": {"exists": true, "path": "..."},
    "schema.json": {"exists": true, "path": "..."},
    "schema_text.json": {"exists": true, "path": "..."},
    "retrieval.json": {"exists": true, "path": "..."}
  }
}
```

### Method 3 — Check `/query`

A successful `/query` response contains:

```json
"cache": {
  "hit": true,
  "dir": ".../cache/database_cache/...",
  "sha256": "..."
}
```

On the first cache creation it reports:

```json
"hit": false
```

On later queries against the same unchanged database it should report:

```json
"hit": true
```

The frontend also displays the cache status in the result card.

### Method 4 — Run the cache tests

From the repository root:

```bash
pytest tests/test_json_cache.py -q
```

The tests verify:
1. first processing creates JSON cache files;
2. second processing reuses the cache;
3. modifying the database causes a new SHA-256 and new cache.

## Model setup

Base model:

```text
Qwen/Qwen2.5-1.5B-Instruct
```

LoRA adapter:

```text
D3v1k4/qwen-nlp-text-to-sql
```

The model is not included in Git. It is loaded at runtime.

In Colab:

```python
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

base_id = "Qwen/Qwen2.5-1.5B-Instruct"
adapter_id = "D3v1k4/qwen-nlp-text-to-sql"

tokenizer = AutoTokenizer.from_pretrained(base_id)
base_model = AutoModelForCausalLM.from_pretrained(base_id)
model = PeftModel.from_pretrained(base_model, adapter_id)

from backend.pipeline import pipeline
pipeline.model.attach(model, tokenizer)
```

Run FastAPI in the same Python process after attaching the model.

## Backend

From repository root:

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Install:

```bash
pip install -r requirements.txt
```

Run the API after attaching the model:

```python
import threading
import uvicorn
from backend.app import app

config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
server = uvicorn.Server(config)
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
```

## API endpoints

```text
GET  /health
GET  /databases
GET  /schema?database=<id>
GET  /cache?database=<id>
POST /upload-database
POST /query
```

Example query:

```json
{
  "database": "demo",
  "question": "Show all students who scored more than 80."
}
```

## Frontend

```bash
cd frontend
npm install
```

Create `.env` from `.env.example`.

Windows:

```bash
copy .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

Set:

```text
VITE_API_URL=http://127.0.0.1:8000
```

Then:

```bash
npm run dev
```

The frontend supports:
- database selection
- SQLite upload
- schema viewing
- natural-language query input
- generated SQL
- validation status
- query results
- cache status

The ngrok browser-warning header is automatically sent by the frontend.

## Spider retrieval cache

The Spider `CatalogBuilder` now uses the same JSON cache manager.

When a Spider SQLite database is available, catalog construction:

```text
SQLite DB
   ↓
SHA-256
   ↓
JSON cache
   ├── metadata
   ├── schema
   ├── schema text
   └── retrieval context
   ↓
spider_catalog.json
   ↓
TF-IDF index
```

If the database is unchanged, schema extraction and schema-text generation are reused from the per-database JSON cache.

The existing `spider_catalog.json` and `spider_tfidf_index.pkl` remain generated artifacts and are excluded from Git.

## Security / Git

Never commit:
- Hugging Face tokens
- ngrok authtokens
- `.env`
- private database files
- database cache files
- `node_modules`
- `.venv`
- private keys

Before pushing:

```bash
git status
git add .
git diff --cached --name-only
```

Make sure secrets and private databases are absent.

Do not force-push the team's `main` branch.
