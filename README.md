# NLP-Based Text-to-SQL System

A full-stack natural-language-to-SQL application using **Qwen2.5-1.5B-Instruct + a LoRA adapter**, FastAPI, SQLite, and React/Vite.

## Features

- Natural-language question → SQL generation
- Qwen + LoRA model support
- Dynamic SQLite schema extraction
- Upload `.db`, `.sqlite`, or `.sqlite3` databases from the UI
- Select between multiple databases
- Read-only SQL validation
- SQLite `EXPLAIN` validation
- SQLite authorizer for read-only execution
- Results returned as JSON and rendered in React
- CORS support
- Colab + ngrok workflow

## Model

Base model: `Qwen/Qwen2.5-1.5B-Instruct`

LoRA adapter: `D3v1k4/qwen-nlp-text-to-sql`

The model is **not included in this repository**. It is downloaded/loaded at runtime in Colab or another machine.

## Repository layout

```text
NLP-Based-Text-to-SQL-System/
├── backend/
│   ├── app.py
│   ├── db.py
│   ├── model_service.py
│   ├── models.py
│   ├── pipeline.py
│   ├── validator.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── package.json
│   ├── .env.example
│   └── index.html
├── notebooks/
│   └── colab_backend_setup.ipynb
├── databases/
│   └── .gitkeep
├── .gitignore
└── README.md
```

## Important: secrets are NOT committed

Do not put Hugging Face tokens, ngrok authtokens, API keys, passwords, or private database files in Git.

This repository contains `.env.example`, not `.env`. The `.gitignore` also excludes `.env`, `.env.*` except `.env.example`, ngrok config, uploaded databases, Python caches, and Node build files.

If a token has ever been committed, deleting it from the file is **not enough**. Revoke/rotate the token immediately and then remove it from Git history.

## Local backend

From the repository root:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r backend/requirements.txt
```

Load the Qwen base model + LoRA adapter, then attach them to the pipeline in the same Python process:

```python
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
from backend.pipeline import pipeline

base = "Qwen/Qwen2.5-1.5B-Instruct"
adapter = "D3v1k4/qwen-nlp-text-to-sql"

tokenizer = AutoTokenizer.from_pretrained(base)
base_model = AutoModelForCausalLM.from_pretrained(base)
model = PeftModel.from_pretrained(base_model, adapter)
pipeline.model.attach(model, tokenizer)
```

Then run FastAPI **in the same process** if you attached the model dynamically.

## Colab

Use `notebooks/colab_backend_setup.ipynb`. It installs dependencies, downloads the project, loads Qwen + LoRA, attaches the model to FastAPI, creates a demo SQLite database, and starts Uvicorn in-process.

For public access, ngrok is optional. If you use it, keep the authtoken in your local/Colab secret environment and never paste it into Git.

## Frontend

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

On Linux/macOS use `cp .env.example .env`.

Set `VITE_API_URL` to your backend URL. For a local backend it is normally:

```text
http://127.0.0.1:8000
```

The frontend automatically sends the `ngrok-skip-browser-warning: true` header, which is useful when the backend is exposed through an ngrok browser URL.

## API endpoints

- `GET /health`
- `GET /databases`
- `GET /schema?database=<id>`
- `POST /upload-database`
- `POST /query`

Example query body:

```json
{
  "database": "demo",
  "question": "Show all students who scored more than 80."
}
```

## Git safety checklist

Before your first push:

```bash
git status

git add .
git diff --cached --name-only
```

Make sure you do NOT see:

- `.env`
- `*.pem`, `*.key`
- ngrok configuration/token files
- Hugging Face tokens
- database files containing private data
- `node_modules/`
- `.venv/`

Then commit and push:

```bash
git commit -m "Initial Text-to-SQL full-stack system"
git branch -M main
git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPO>.git
git push -u origin main
```

## If you already exposed a token

1. Revoke/rotate it at the provider immediately.
2. Remove it from the working tree.
3. Check Git history before publishing.
4. If it was committed, rewrite the history or create a fresh repository history.
5. Never rely on `.gitignore` alone to make an already-committed secret safe.
