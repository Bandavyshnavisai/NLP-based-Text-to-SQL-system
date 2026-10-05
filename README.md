# NLP-based Text-to-SQL System

An end-to-end Natural Language Processing system that translates user questions in plain English into executable SQL queries.

---

## 📁 Project Structure

```text
NLP-based-Text-to-SQL-system/
│
├── databases/              # SQLite / sample database files and schema definitions
├── database_retrieval/     # Modules for schema linking, table retrieval, and database querying
├── evaluation/             # Scripts and benchmarks for evaluating model accuracy & execution accuracy
├── README.md               # Project documentation
├── requirements.txt        # Python package dependencies
└── .gitignore              # Files and directories ignored by Git
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.9+ installed

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

---

## 📌 Modules Overview

- **`databases/`**: Store relational database instances (e.g. SQLite `.sqlite` or `.db` files) and schemas.
- **`database_retrieval/`**: Logic for schema extraction, table selection, and interacting with the database engine.
- **`evaluation/`**: Evaluation pipelines for exact set match (ESM) and execution accuracy (EX).
