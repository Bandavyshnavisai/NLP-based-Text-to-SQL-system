"""Evaluation framework for Schema Linking accuracy on the Spider benchmark.

Derives ground truth tables, columns, and relationships directly from the gold SQL
and evaluates the predictions of Member 2 Schema Linking.

Computes:
1. Table Linking: Precision, Recall, F1, Exact Match Accuracy, and Coverage Accuracy
2. Column Linking: Precision, Recall, F1, and Coverage Accuracy
3. Relationship Linking: Precision, Recall, F1, and Coverage Accuracy
4. Overall Schema Linking Accuracy (all gold tables & columns covered)

Usage:
    python -m evaluation.eval_schema_linking --split dev
    python -m evaluation.eval_schema_linking --split dev --sample 100
    python -m evaluation.eval_schema_linking --split dev --use-gold-db
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import sqlparse
from sqlparse.sql import Identifier, IdentifierList, Where
from sqlparse.tokens import Keyword, Name

# Ensure workspace root is on sys.path
_WORKSPACE_ROOT = Path(__file__).parent.parent.resolve()
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from database_retrieval.retriever import DatabaseRetriever
from schema_linking import SchemaLinker


_SPIDER_FILES = {
    "dev": _WORKSPACE_ROOT / "dev.json",
    "train": _WORKSPACE_ROOT / "train_spider.json",
    "train_others": _WORKSPACE_ROOT / "train_others.json",
}


def load_spider_data(split: str = "dev") -> List[Dict[str, Any]]:
    """Load Spider examples from local JSON files or datasets fallback."""
    path = _SPIDER_FILES.get(split)
    if path is not None and path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # Fallback to Hugging Face datasets if local files not present
    import datasets
    hf_split = "validation" if split == "dev" else "train"
    ds = datasets.load_dataset("xlangai/spider", split=hf_split)
    return [item for item in ds]


def extract_gold_schema_elements(
    sql_query: str,
    db_schema: Dict[str, Any]
) -> Dict[str, Any]:
    """Extract ground truth tables, columns, and relationships referenced in the gold SQL.

    Cross-references SQL tokens against the known database schema.

    Args:
        sql_query: Ground truth SQL string.
        db_schema: Database schema dict from catalog.

    Returns:
        Dict containing:
            - tables: Set[str] (lowercase table names)
            - columns: Set[Tuple[str, str]] (lowercase (table_name, column_name) tuples)
            - relationships: Set[Tuple[str, str]] (lowercase (table1, table2) pairs)
    """
    if not sql_query or not db_schema:
        return {"tables": set(), "columns": set(), "relationships": set()}

    table_names_lower = {t["table_name"].lower(): t["table_name"] for t in db_schema.get("tables", [])}
    
    # Map column name -> list of tables that contain it
    cols_to_tables: Dict[str, List[str]] = {}
    col_lookup_set: Set[Tuple[str, str]] = set()

    for tbl in db_schema.get("tables", []):
        tname = tbl["table_name"].lower()
        for col in tbl.get("columns", []):
            cname = col["name"].lower()
            cols_to_tables.setdefault(cname, []).append(tname)
            col_lookup_set.add((tname, cname))

    # Tokenize SQL query
    tokens = re.findall(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)?", sql_query)

    gold_tables: Set[str] = set()
    gold_columns: Set[Tuple[str, str]] = set()

    # Step 1: Find all tables explicitly referenced
    for tok in tokens:
        tok_low = tok.lower()
        if "." in tok_low:
            parts = tok_low.split(".", 1)
            if parts[0] in table_names_lower:
                gold_tables.add(table_names_lower[parts[0]])
                if (parts[0], parts[1]) in col_lookup_set:
                    gold_columns.add((table_names_lower[parts[0]], parts[1]))
        elif tok_low in table_names_lower:
            gold_tables.add(table_names_lower[tok_low])

    # Step 2: Find columns and resolve their parent tables
    for tok in tokens:
        tok_low = tok.lower()
        if "." not in tok_low and tok_low in cols_to_tables:
            candidate_tbls = cols_to_tables[tok_low]
            # Disambiguate if only one candidate or if candidate is in gold_tables
            matched_tbl = None
            for ct in candidate_tbls:
                if ct in {t.lower() for t in gold_tables}:
                    matched_tbl = table_names_lower.get(ct, ct)
                    break
            if not matched_tbl and candidate_tbls:
                matched_tbl = table_names_lower.get(candidate_tbls[0], candidate_tbls[0])

            if matched_tbl:
                gold_columns.add((matched_tbl, tok_low))
                gold_tables.add(matched_tbl)

    # Step 3: Extract gold relationships (joins between active tables)
    gold_relationships: Set[Tuple[str, str]] = set()
    for rel in db_schema.get("relationships", []):
        src = rel["source_table"]
        tgt = rel["target_table"]
        if src in gold_tables and tgt in gold_tables:
            pair = tuple(sorted([src.lower(), tgt.lower()]))
            gold_relationships.add(pair)

    return {
        "tables": gold_tables,
        "columns": gold_columns,
        "relationships": gold_relationships,
    }


def compute_set_metrics(predicted: Set[Any], ground_truth: Set[Any]) -> Dict[str, float]:
    """Compute precision, recall, F1, and exact match for predicted set vs ground truth set."""
    if not ground_truth:
        return {
            "precision": 1.0 if not predicted else 0.0,
            "recall": 1.0,
            "f1": 1.0 if not predicted else 0.0,
            "exact_match": 1.0 if not predicted else 0.0,
            "coverage": 1.0,
        }

    if not predicted:
        return {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "exact_match": 0.0,
            "coverage": 0.0,
        }

    intersection = predicted & ground_truth
    precision = len(intersection) / len(predicted)
    recall = len(intersection) / len(ground_truth)
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    exact_match = 1.0 if predicted == ground_truth else 0.0
    coverage = 1.0 if ground_truth.issubset(predicted) else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "exact_match": exact_match,
        "coverage": coverage,
    }


def evaluate_schema_linking(
    linker: SchemaLinker,
    catalog_by_name: Dict[str, Any],
    examples: List[Dict[str, Any]],
    use_gold_db: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Evaluate schema linking across a dataset of Spider examples.

    Args:
        linker: SchemaLinker instance.
        catalog_by_name: Catalog lookup dictionary.
        examples: List of Spider example dicts.
        use_gold_db: If True, link against the gold database (isolates Member 2 performance).
        verbose: If True, print misses.

    Returns:
        Summary metrics dictionary.
    """
    total = len(examples)
    table_metrics_list = []
    column_metrics_list = []
    relationship_metrics_list = []
    overall_success = 0

    for i, ex in enumerate(examples, 1):
        question = ex["question"]
        gold_db = ex["db_id"]
        gold_sql = ex.get("query", ex.get("sql", ""))

        db_schema = catalog_by_name.get(gold_db)
        if not db_schema:
            continue

        gold_elements = extract_gold_schema_elements(gold_sql, db_schema)
        gold_tables_norm = {t.lower() for t in gold_elements["tables"]}
        gold_cols_norm = {(t.lower(), c.lower()) for t, c in gold_elements["columns"]}
        gold_rels_norm = gold_elements["relationships"]

        # Run Member 2 schema linking
        if use_gold_db:
            result = linker.link(question, target_schema=db_schema)
        else:
            result = linker.link(question, top_k=5)

        # Extract predictions
        pred_tables_norm = {t.name.lower() for t in result.tables}
        pred_cols_norm = {(c.table.lower(), c.column.lower()) for c in result.columns}
        pred_rels_norm = {
            tuple(sorted([r.from_table.lower(), r.to_table.lower()]))
            for r in result.relationships
        }

        # Evaluate
        t_m = compute_set_metrics(pred_tables_norm, gold_tables_norm)
        c_m = compute_set_metrics(pred_cols_norm, gold_cols_norm)
        r_m = compute_set_metrics(pred_rels_norm, gold_rels_norm)

        table_metrics_list.append(t_m)
        column_metrics_list.append(c_m)
        relationship_metrics_list.append(r_m)

        # Overall success: all gold tables and all gold columns are covered
        is_covered = (
            gold_tables_norm.issubset(pred_tables_norm)
            and gold_cols_norm.issubset(pred_cols_norm)
        )
        if is_covered:
            overall_success += 1

        if verbose and not is_covered and i <= 10:
            print(f"\n[MISS #{i}] Q: {question}")
            print(f"  Expected Tables: {gold_tables_norm} | Pred: {pred_tables_norm}")
            print(f"  Expected Columns: {gold_cols_norm} | Pred: {pred_cols_norm}")

        if i % 100 == 0:
            print(f"  Evaluated {i}/{total} examples...")

    n = len(table_metrics_list) or 1

    def avg_metric(m_list, key):
        return round(sum(m[key] for m in m_list) / n, 4)

    return {
        "total": n,
        "table_linking": {
            "precision": avg_metric(table_metrics_list, "precision"),
            "recall": avg_metric(table_metrics_list, "recall"),
            "f1": avg_metric(table_metrics_list, "f1"),
            "exact_match": avg_metric(table_metrics_list, "exact_match"),
            "coverage_accuracy": avg_metric(table_metrics_list, "coverage"),
        },
        "column_linking": {
            "precision": avg_metric(column_metrics_list, "precision"),
            "recall": avg_metric(column_metrics_list, "recall"),
            "f1": avg_metric(column_metrics_list, "f1"),
            "coverage_accuracy": avg_metric(column_metrics_list, "coverage"),
        },
        "relationship_linking": {
            "precision": avg_metric(relationship_metrics_list, "precision"),
            "recall": avg_metric(relationship_metrics_list, "recall"),
            "f1": avg_metric(relationship_metrics_list, "f1"),
            "coverage_accuracy": avg_metric(relationship_metrics_list, "coverage"),
        },
        "overall_schema_coverage_accuracy": round(overall_success / n, 4),
    }


def print_evaluation_report(report: Dict[str, Any], split: str, use_gold_db: bool) -> None:
    """Print formatted evaluation report."""
    mode_str = "Gold DB Provided" if use_gold_db else "Full Pipeline (Retriever + Linker)"
    print("\n" + "=" * 70)
    print(f"  Member 2 Schema Linking Evaluation Report")
    print(f"  Split: {split} | Mode: {mode_str} | Total: {report['total']}")
    print("=" * 70)

    t = report["table_linking"]
    print("\n1. Table Linking Metrics:")
    print(f"   - Precision         : {t['precision'] * 100:.2f}%")
    print(f"   - Recall            : {t['recall'] * 100:.2f}%")
    print(f"   - F1-Score          : {t['f1'] * 100:.2f}%")
    print(f"   - Exact Match Acc   : {t['exact_match'] * 100:.2f}%")
    print(f"   - Coverage Accuracy : {t['coverage_accuracy'] * 100:.2f}%")

    c = report["column_linking"]
    print("\n2. Column Linking Metrics:")
    print(f"   - Precision         : {c['precision'] * 100:.2f}%")
    print(f"   - Recall            : {c['recall'] * 100:.2f}%")
    print(f"   - F1-Score          : {c['f1'] * 100:.2f}%")
    print(f"   - Coverage Accuracy : {c['coverage_accuracy'] * 100:.2f}%")

    r = report["relationship_linking"]
    print("\n3. Relationship Linking Metrics:")
    print(f"   - Precision         : {r['precision'] * 100:.2f}%")
    print(f"   - Recall            : {r['recall'] * 100:.2f}%")
    print(f"   - F1-Score          : {r['f1'] * 100:.2f}%")
    print(f"   - Coverage Accuracy : {r['coverage_accuracy'] * 100:.2f}%")

    print("\n" + "=" * 70)
    print(f"  Overall Schema Coverage Accuracy: {report['overall_schema_coverage_accuracy'] * 100:.2f}%")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Evaluate Schema Linking on Spider dataset.")
    parser.add_argument(
        "--split",
        choices=["dev", "train", "train_others"],
        default="dev",
        help="Spider split to evaluate (default: dev).",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Sample N examples randomly (default: all).",
    )
    parser.add_argument(
        "--use-gold-db",
        action="store_true",
        help="Evaluate schema linking directly on gold database schema (isolates Member 2).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose failure information.",
    )

    args = parser.parse_args()

    print(f"Loading Spider '{args.split}' split...")
    examples = load_spider_data(args.split)
    print(f"  Loaded {len(examples)} examples.")

    if args.sample and args.sample < len(examples):
        import random
        random.seed(42)
        examples = random.sample(examples, args.sample)
        print(f"  Sampled {len(examples)} examples (seed=42).")

    print("Initializing DatabaseRetriever and SchemaLinker...")
    retriever = DatabaseRetriever()
    retriever.load_index()
    catalog = retriever.load_catalog()
    catalog_by_name = {e["database_name"]: e for e in catalog}

    linker = SchemaLinker(retriever=retriever)
    linker._catalog_by_name = catalog_by_name

    print("\nRunning Schema Linking Evaluation...")
    report = evaluate_schema_linking(
        linker=linker,
        catalog_by_name=catalog_by_name,
        examples=examples,
        use_gold_db=args.use_gold_db,
        verbose=args.verbose,
    )

    print_evaluation_report(report, args.split, args.use_gold_db)


if __name__ == "__main__":
    main()
