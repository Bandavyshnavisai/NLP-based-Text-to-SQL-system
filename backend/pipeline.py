import time

from .model_service import ModelService
from .db import get_database_cache, execute_read_only
from .validator import validate_sql


class Pipeline:
    def __init__(self):
        self.model = ModelService()

    def run(self, question: str, database: str) -> dict:
        start = time.perf_counter()

        # No schema extraction/retrieval work is repeated here. The cache
        # manager returns the JSON-backed context for this exact DB file.
        cache = get_database_cache(database)
        schema = cache["schema"]
        schema_text = cache["schema_text"]

        generation_start = time.perf_counter()
        sql = self.model.generate(
            question,
            schema,
            schema_text=schema_text,
        )
        generation_time_ms = round(
            (time.perf_counter() - generation_start) * 1000, 2
        )

        validation = validate_sql(sql, database)
        if not validation["valid"]:
            return {
                "success": False,
                "question": question,
                "database": database,
                "sql": sql,
                "validation": validation,
                "execution": {},
                "cache": {
                    "hit": cache["cache_hit"],
                    "dir": cache["cache_dir"],
                    "sha256": cache["metadata"]["sha256"],
                },
                "generation_time_ms": generation_time_ms,
                "total_time_ms": round(
                    (time.perf_counter() - start) * 1000, 2
                ),
                "error": "Generated SQL failed safety/SQLite validation.",
            }

        exec_start = time.perf_counter()
        execution = execute_read_only(database, sql)
        execution["time_ms"] = round(
            (time.perf_counter() - exec_start) * 1000, 2
        )

        return {
            "success": execution["success"],
            "question": question,
            "database": database,
            "sql": sql,
            "validation": validation,
            "execution": execution,
            "cache": {
                "hit": cache["cache_hit"],
                "dir": cache["cache_dir"],
                "sha256": cache["metadata"]["sha256"],
            },
            "generation_time_ms": generation_time_ms,
            "total_time_ms": round(
                (time.perf_counter() - start) * 1000, 2
            ),
            "error": None,
        }


pipeline = Pipeline()
