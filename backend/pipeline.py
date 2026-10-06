import time
from .model_service import ModelService
from .db import get_schema, execute_read_only
from .validator import validate_sql

class Pipeline:
    def __init__(self):
        self.model = ModelService()

    def run(self, question: str, database: str) -> dict:
        start = time.perf_counter()
        schema = get_schema(database)
        sql = self.model.generate(question, schema)
        validation = validate_sql(sql, database)
        if not validation["valid"]:
            return {"success": False, "question": question, "database": database, "sql": sql, "validation": validation, "execution": {}, "error": "Generated SQL failed safety/SQLite validation."}
        exec_start = time.perf_counter()
        execution = execute_read_only(database, sql)
        execution["time_ms"] = round((time.perf_counter() - exec_start) * 1000, 2)
        return {"success": execution["success"], "question": question, "database": database, "sql": sql, "validation": validation, "execution": execution, "total_time_ms": round((time.perf_counter() - start) * 1000, 2), "error": None}

pipeline = Pipeline()
