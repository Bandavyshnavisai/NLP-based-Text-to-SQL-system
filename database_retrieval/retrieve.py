"""CLI entry point for database retrieval.

Usage:
    python -m database_retrieval.retrieve "What are the names of students enrolled in CS?"
    python -m database_retrieval.retrieve "What are the names of students enrolled in CS?" --top-k 3
    python -m database_retrieval.retrieve --build-index
    python -m database_retrieval.retrieve --build-index --rebuild-catalog
"""

import argparse
import sys
from pathlib import Path

from .retriever import DatabaseRetriever


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve the most relevant Spider database(s) for a natural-language question."
    )
    parser.add_argument(
        "question",
        nargs="?",
        default=None,
        help="Natural-language question to retrieve a database for.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        metavar="K",
        help="Number of top databases to return (default: 5).",
    )
    parser.add_argument(
        "--build-index",
        action="store_true",
        help="Build (or rebuild) the TF-IDF index and exit.",
    )
    parser.add_argument(
        "--rebuild-catalog",
        action="store_true",
        help="Force catalog regeneration even if a catalog already exists.",
    )
    parser.add_argument(
        "--databases-dir",
        type=str,
        default=None,
        help="Path to Spider databases directory (default: ./databases).",
    )
    parser.add_argument(
        "--catalog-path",
        type=str,
        default=None,
        help="Path to catalog JSON file.",
    )

    args = parser.parse_args()

    retriever = DatabaseRetriever(
        databases_dir=args.databases_dir,
        catalog_path=args.catalog_path,
    )

    if args.build_index:
        retriever.build_index(
            rebuild_catalog=args.rebuild_catalog,
            verbose=True,
        )
        print("Index built successfully.")
        return

    if not args.question:
        parser.print_help()
        sys.exit(1)

    results = retriever.retrieve(args.question, top_k=args.top_k)
    print(f"\nQuestion: {args.question}\n")
    print(retriever.format_results(results))


if __name__ == "__main__":
    main()
