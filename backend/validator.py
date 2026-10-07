import re
import sqlite3
from .db import resolve_database

BLOCKED = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|VACUUM|REINDEX|PRAGMA)\b", re.I)

def validate_sql(sql: str, database: str) -> dict:
    sql = sql.strip()
    if sql.endswith(";"):
        sql_no_semicolon = sql[:-1].strip()
    else:
        sql_no_semicolon = sql
    statements = [s.strip() for s in sql_no_semicolon.split(";") if s.strip()]
    result = {"valid": False, "read_only": False, "single_statement": len(statements) == 1, "tables_known": False, "parser_available": True}
    if len(statements) != 1:
        return result
    if BLOCKED.search(sql_no_semicolon):
        return result
    if not re.match(r"^(SELECT|WITH)\b", sql_no_semicolon, re.I):
        return result
    try:
        con = sqlite3.connect(f"file:{resolve_database(database).as_posix()}?mode=ro", uri=True)
        try:
            con.execute("EXPLAIN " + sql_no_semicolon).fetchall()
        finally:
            con.close()
        result.update(valid=True, read_only=True, tables_known=True)
        return result
    except sqlite3.Error:
        return result
