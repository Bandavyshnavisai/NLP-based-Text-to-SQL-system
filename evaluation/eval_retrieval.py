"""Evaluation framework for database retrieval accuracy.

Computes Top-1, Top-3, and Top-5 retrieval accuracy using
the official Spider question-to-database mappings from
dev.json and train_spider.json.

Usage:
    python -m evaluation.eval_retrieval
    python -m evaluation.eval_retrieval --split dev
    python -m evaluation.eval_retrieval --split train --sample 500
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure the workspace root is on the path for module imports
_WORKSPACE_ROOT = Path(__file__).parent.parent.resolve()
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from database_retrieval.retriever import DatabaseRetriever


_SPIDER_FILES = {
    "dev": _WORKSPACE_ROOT / "dev.json",
    "train": _WORKSPACE_ROOT / "train_spider.json",
    "train_others": _WORKSPACE_ROOT / "train_others.json",
}


def load_spider_pairs(split: str = "dev") -> List[Tuple[str, str]]:
    """Load (question, db_id) pairs from the specified Spider split.

    Args:
        split: One of 'dev', 'train', 'train_others'.

    Returns:
        List of (question, db_id) tuples.
    """
    path = _SPIDER_FILES.get(split)
    if path is None or not path.exists():
        raise FileNotFoundError(
            f"Spider split '{split}' not found at {path}. "
            "Ensure dev.json / train_spider.json exist in the project root."
        )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [(entry["question"], entry["db_id"]) for entry in data]


def evaluate_retrieval(
    retriever: DatabaseRetriever,
    pairs: List[Tuple[str, str]],
    top_k_values: Tuple[int, ...] = (1, 3, 5),
    verbose: bool = False,
) -> Dict[str, Any]:
    """Evaluate retrieval accuracy over a set of (question, ground_truth_db) pairs.

    Args:
        retriever: A DatabaseRetriever instance (index must be loaded).
        pairs: List of (question, correct_db_id) tuples.
        top_k_values: Which Top-K accuracies to compute.
        verbose: If True, print per-example misses.

    Returns:
        Dict with:
            - total (int)
            - top_k_hits (Dict[int, int])
            - top_k_accuracy (Dict[int, float])
            - misses (List[dict])
    """
    max_k = max(top_k_values)
    hits = {k: 0 for k in top_k_values}
    misses: List[Dict[str, Any]] = []

    total = len(pairs)
    for i, (question, expected_db) in enumerate(pairs, 1):
        results = retriever.retrieve(question, top_k=max_k)
        retrieved_dbs = [r["database"] for r in results]

        for k in top_k_values:
            if expected_db in retrieved_dbs[:k]:
                hits[k] += 1

        if expected_db not in retrieved_dbs[:max_k]:
            misses.append({
                "question": question,
                "expected": expected_db,
                "got": retrieved_dbs[:3],
            })
            if verbose:
                print(
                    f"  [MISS] Q: {question[:70]!r} | expected={expected_db} | got={retrieved_dbs[:3]}"
                )

        if i % 100 == 0:
            print(f"  Evaluated {i}/{total}...")

    accuracy = {k: round(hits[k] / total, 4) for k in top_k_values}

    return {
        "total": total,
        "top_k_hits": hits,
        "top_k_accuracy": accuracy,
        "misses": misses,
    }


def print_report(report: Dict[str, Any], split: str) -> None:
    """Print a human-readable evaluation report."""
    print("\n" + "=" * 60)
    print(f"  Database Retrieval Evaluation — split: {split}")
    print("=" * 60)
    print(f"  Total questions evaluated : {report['total']}")
    for k, acc in sorted(report["top_k_accuracy"].items()):
        hits = report["top_k_hits"][k]
        print(f"  Top-{k} Accuracy: {acc:.4f}  ({hits}/{report['total']})")
    print("=" * 60)
    if report["misses"]:
        print(f"\n  Missed {len(report['misses'])} examples. First 5 misses:")
        for miss in report["misses"][:5]:
            print(f"    Q : {miss['question'][:80]!r}")
            print(f"        expected={miss['expected']!r}, got={miss['got']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Evaluate database retrieval accuracy on Spider.")
    parser.add_argument(
        "--split",
        choices=["dev", "train", "train_others"],
        default="dev",
        help="Spider split to evaluate on (default: dev).",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        metavar="N",
        help="Randomly sample N questions (default: all).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        nargs="+",
        default=[1, 3, 5],
        metavar="K",
        help="Top-K values to evaluate (default: 1 3 5).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-example misses.",
    )
    parser.add_argument(
        "--databases-dir",
        type=str,
        default=None,
        help="Path to Spider databases directory.",
    )
    args = parser.parse_args()

    print(f"Loading Spider '{args.split}' split...")
    pairs = load_spider_pairs(args.split)
    print(f"  Loaded {len(pairs)} (question, db_id) pairs.")

    if args.sample and args.sample < len(pairs):
        import random
        random.seed(42)
        pairs = random.sample(pairs, args.sample)
        print(f"  Sampled {len(pairs)} pairs (seed=42).")

    retriever = DatabaseRetriever(databases_dir=args.databases_dir)
    print("Loading TF-IDF index...")
    retriever.load_index()
    if retriever._catalog is None and retriever.catalog_path.exists():
        retriever._catalog = retriever._catalog_builder.load_catalog()
    print("  Index loaded.")

    print(f"\nEvaluating retrieval (top-k = {args.top_k})...")
    report = evaluate_retrieval(
        retriever,
        pairs,
        top_k_values=tuple(args.top_k),
        verbose=args.verbose,
    )
    print_report(report, args.split)


if __name__ == "__main__":
    main()
