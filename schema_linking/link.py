"""CLI entry point for Schema Linking and Query Understanding.

Usage (Spider Benchmark Mode):
    python -m schema_linking.link "Which stadium has hosted the most concerts?"
    python -m schema_linking.link "What are the names of singers?" --json
    python -m schema_linking.link "Find students in CS department." --database college_2
    python -m schema_linking.link "Which stadium has hosted the most concerts?" --prompt

Usage (Dynamic User Database Mode):
    python -m schema_linking.link "What is the average salary?" --db-path company.db
    python -m schema_linking.link "List all employees" --db-path /path/to/hr.sqlite --json
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure the workspace root is on the path for direct script execution
_WORKSPACE_ROOT = Path(__file__).parent.parent.resolve()
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from schema_linking import SchemaLinker


def format_human_readable(result) -> str:
    """Format a SchemaLinkingResult into a human-readable CLI summary."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"Question: {result.question}")
    lines.append(f"Database: {result.database} (Retrieval Score: {result.retrieval_score:.4f}, Rank: {result.candidate_rank})")
    lines.append("=" * 60)

    # Intent
    lines.append("\nIntent:")
    lines.append(f"  Type       : {result.intent.type}")
    if result.intent.entities:
        lines.append(f"  Entities   : {', '.join(result.intent.entities)}")
    if result.intent.operations:
        lines.append(f"  Operations : {', '.join(result.intent.operations)}")
    if result.intent.conditions:
        lines.append(f"  Conditions : {', '.join(result.intent.conditions)}")

    # Relevant Tables
    lines.append("\nRelevant Tables:")
    if result.tables:
        for t in result.tables:
            role_tag = f"[{t.role.upper()}]"
            lines.append(f"  - {t.name:<25} {role_tag:<10} (score: {t.score:.2f}, reason: {t.reason})")
    else:
        lines.append("  (None)")

    # Relevant Columns
    lines.append("\nRelevant Columns:")
    if result.columns:
        for c in result.columns:
            lines.append(f"  - {c.table}.{c.column:<20} (score: {c.score:.2f}, reason: {c.reason})")
    else:
        lines.append("  (None)")

    # Relationships
    lines.append("\nRelationships:")
    if result.relationships:
        for r in result.relationships:
            if r.is_composite:
                from_cols = ", ".join(r.from_columns)
                to_cols = ", ".join(r.to_columns)
                lines.append(f"  - {r.from_table}.({from_cols}) -> {r.to_table}.({to_cols}) [Composite FK]")
            else:
                lines.append(f"  - {r.from_table}.{r.from_column} -> {r.to_table}.{r.to_column}")
    else:
        lines.append("  (None)")

    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Run query understanding and schema linking on a natural-language question."
    )
    parser.add_argument(
        "question",
        nargs="?",
        default=None,
        help="Natural-language question to link against schema.",
    )

    # --- Mode 1: Spider Benchmark Mode ---
    parser.add_argument(
        "--database", "-d",
        type=str,
        default=None,
        help=(
            "[Mode 1 — Spider] Target Spider database name override "
            "(skips retrieval, uses Spider catalog)."
        ),
    )

    # --- Mode 2: Dynamic User Database Mode ---
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        metavar="DB_PATH",
        help=(
            "[Mode 2 — Dynamic] Path to a user-supplied SQLite database file "
            "(.db / .sqlite / .sqlite3). No Spider metadata required."
        ),
    )

    parser.add_argument(
        "--top-k", "-k",
        type=int,
        default=5,
        help="Number of retrieved database candidates to consider (default: 5). Mode 1 only.",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output structured JSON format.",
    )
    parser.add_argument(
        "--prompt", "-p",
        action="store_true",
        help="Output Member 3 textual prompt schema representation.",
    )

    args = parser.parse_args()

    if not args.question:
        parser.print_help()
        sys.exit(1)

    if args.database and args.db_path:
        print(
            "[ERROR] --database (Spider mode) and --db-path (Dynamic mode) are mutually exclusive.",
            file=sys.stderr,
        )
        sys.exit(1)

    linker = SchemaLinker()

    if args.db_path:
        # ── Mode 2: Dynamic User Database ────────────────────────────────
        from database_retrieval.loader import load_database
        try:
            active_db = load_database(args.db_path)
        except (FileNotFoundError, ValueError) as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            sys.exit(1)
        result = linker.link(
            question=args.question,
            target_schema=active_db.get_schema(),
        )
    else:
        # ── Mode 1: Spider Benchmark (or full retrieval) ─────────────────
        result = linker.link(
            question=args.question,
            top_k=args.top_k,
            target_db=args.database,
        )

    if args.json:
        print(result.to_json(indent=2))
    elif args.prompt:
        print(result.to_member3_prompt())
    else:
        print(format_human_readable(result))


if __name__ == "__main__":
    main()
