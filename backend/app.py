from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .models import QueryRequest
from .pipeline import pipeline
from .db import list_databases, get_schema, save_uploaded_database

app = FastAPI(title="NLP Text-to-SQL Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status":"ok", "model_loaded": pipeline.model.loaded, "mock_model": False, "base_model": pipeline.model.base_model, "adapter": pipeline.model.adapter}

@app.get("/databases")
def databases():
    return {"databases": list_databases()}

@app.get("/schema")
def schema(database: str):
    try:
        return get_schema(database)
    except Exception as e:
        raise HTTPException(404, str(e))

@app.post("/upload-database")
async def upload_database(file: UploadFile = File(...)):
    try:
        data = await file.read()
        return save_uploaded_database(file.filename or "database.sqlite", data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Upload failed: {e}")

@app.post("/query")
def query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty")
    try:
        return pipeline.run(req.question, req.database)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        return {"success": False, "question": req.question, "database": req.database, "sql": None, "validation": {}, "execution": {}, "error": str(e)}
