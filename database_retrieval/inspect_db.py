"""CLI entry point: inspect a user-provided SQLite database.

Demonstrates the Dynamic User Database Mode pipeline:

    User SQLite file → load_database() → ActiveDatabase
                     → (optional) SchemaLinker → SchemaLinkingResult

Usage
-----
Inspect schema only::

    python -m database_retrieval.inspect_db "C:\\path\\to\\company.db"

Inspect schema and run schema linking on a question::

    python -m database_retrieval.inspect_db "company.db" \\
        --question "What is the average salary of employees?"

Output as JSON::

    python -m database_retrieval.inspect_db "company.db" --json

Show Member-3 prompt schema::

    python -m database_retrieval.inspect_db "company.db" \\
        --question "List employees earning more than 50000." --prompt
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure workspace root is on sys.path when executed as __main__
_WORKSPACE_ROOT = Path(__file__).parent.parent.resolve()
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from database_retrieval.loader import load_database


def _format_schema(active_db) -> str:
    """Render a human-readable summary of the database schema."""
    schema = active_db.get_schema()
    lines = []
    lines.append("=" * 60)
    lines.append(f"Database : {active_db.database_name}")
    lines.append(f"Type     : {active_db.database_type}")
    lines.append(f"File     : {active_db.path}")
    lines.append(f"Tables   : {active_db.total_tables}")
    lines.append("=" * 60)

    for tbl in schema.get("tables", []):
        pk_str = ", ".join(tbl["primary_keys"]) if tbl["primary_keys"] else "—"
        composite = " [Composite PK]" if tbl["is_composite_pk"] else ""
        lines.append(f"\nTABLE {tbl['table_name']}  (PK: {pk_str}{composite})")
        for col in tbl["columns"]:
            pk_marker = " [PK]" if col["primary_key"] else ""
            nn_marker = " NOT NULL" if col["not_null"] else ""
            lines.append(f"  - {col['name']} ({col['type']}){pk_marker}{nn_marker}")
        if tbl["foreign_keys"]:
            for fk in tbl["foreign_keys"]:
                comp = " [Composite FK]" if fk["is_composite"] else ""
                lines.append(
                    f"  → FK{comp}: {tbl['table_name']}.{fk['from_column']}"
                    f" → {fk['to_table']}.{fk['to_column']}"
                )

    rels = schema.get("relationships", [])
    if rels:
        lines.append("\nRelationships:")
        for rel in rels:
            comp = " [Composite]" if rel["is_composite"] else ""
            lines.append(
                f"  {rel['source_table']}.{rel['source_column']}"
                f" → {rel['target_table']}.{rel['target_column']}{comp}"
            )
    else:
        lines.append("\nRelationships: (none)")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect a user-supplied SQLite database and optionally run "
            "schema linking on a natural-language question.\n\n"
            "This demonstrates the Dynamic User Database Mode (Mode 2)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "db_path",
        metavar="DB_PATH",
        help="Path to the SQLite database file (.db / .sqlite / .sqlite3).",
    )
    parser.add_argument(
        "--question", "-q",
        type=str,
        default=None,
        metavar="QUESTION",
        help="Natural-language question to run schema linking on.",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output schema linking result as JSON (requires --question).",
    )
    parser.add_argument(
        "--prompt", "-p",
        action="store_true",
        help=(
            "Output the Member-3 textual prompt schema representation "
            "(requires --question)."
        ),
    )

    args = parser.parse_args()

    # ── Step 1: Load and validate database ───────────────────────────────
    try:
        active_db = load_database(args.db_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Step 2: Display schema summary ───────────────────────────────────
    if not args.question:
        print(_format_schema(active_db))
        sys.exit(0)

    # ── Step 3: Optional schema linking ──────────────────────────────────
    from schema_linking import SchemaLinker

    linker = SchemaLinker()
    result = linker.link(
        question=args.question,
        target_schema=active_db.get_schema(),
    )

    if args.json:
        print(result.to_json(indent=2))
    elif args.prompt:
        print(result.to_member3_prompt())
    else:
        # Human-readable summary (mirrors schema_linking/link.py format)
        print(_format_schema(active_db))
        print(f"Question : {result.question}")
        print(f"Intent   : {result.intent.type}")
        if result.intent.entities:
            print(f"Entities : {', '.join(result.intent.entities)}")
        print("\nRelevant Tables:")
        for t in result.tables:
            print(f"  [{t.role.upper()}] {t.name}  (score={t.score:.2f}, {t.reason})")
        print("\nRelevant Columns:")
        for c in result.columns:
            print(f"  {c.table}.{c.column}  (score={c.score:.2f}, {c.reason})")
        if result.relationships:
            print("\nRelationships:")
            for r in result.relationships:
                if r.is_composite:
                    print(
                        f"  {r.from_table}.({', '.join(r.from_columns)})"
                        f" → {r.to_table}.({', '.join(r.to_columns)}) [Composite FK]"
                    )
                else:
                    print(f"  {r.from_table}.{r.from_column} → {r.to_table}.{r.to_column}")


if __name__ == "__main__":
    main()
