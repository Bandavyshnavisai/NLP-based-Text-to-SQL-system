"""Database Retriever.

Provides TF-IDF + cosine-similarity-based retrieval of the most relevant
Spider database(s) given a natural-language user question.

Architecture:
- The retriever works against a pre-built JSON catalog (see catalog_builder.py).
- On first use (or explicit rebuild), it fits a TF-IDF matrix over all
  database schema_text fields.  Schema texts are stemmed before indexing.
- At query time, the question is stemmed and transformed into the same TF-IDF
  space; cosine similarity is computed against every database schema.
- The top-k results are returned with similarity scores and matched
  table/column names.

Stemming ensures that inflected question words such as "singers", "enrolled"
or "flights" correctly match schema tokens "singer", "enrol", "flight".
"""

import json
import os
import pickle
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
from nltk.stem import SnowballStemmer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .catalog_builder import CatalogBuilder

# Module-level stemmer instance (English, thread-safe to share)
_STEMMER = SnowballStemmer("english")


def _stem_text(text: str) -> str:
    """Tokenise a lowercase string and stem every word.

    Args:
        text: Lowercase space-delimited text.

    Returns:
        Space-delimited string of stemmed tokens.
    """
    tokens = re.findall(r"[a-z][a-z0-9]*", text)
    return " ".join(_STEMMER.stem(t) for t in tokens)


_DEFAULT_CATALOG_PATH = (Path(__file__).parent / "spider_catalog.json").resolve()
_DEFAULT_INDEX_PATH = (Path(__file__).parent / "spider_tfidf_index.pkl").resolve()


class DatabaseRetriever:
    """Retrieves the most relevant Spider databases for a given NL question.

    Usage:
        retriever = DatabaseRetriever()
        retriever.build_index()                     # build once
        results = retriever.retrieve("...", top_k=5)
    """

    def __init__(
        self,
        catalog_path: Optional[Union[str, Path]] = None,
        index_path: Optional[Union[str, Path]] = None,
        databases_dir: Optional[Union[str, Path]] = None,
    ):
        self.catalog_path = Path(catalog_path or _DEFAULT_CATALOG_PATH).resolve()
        self.index_path = Path(index_path or _DEFAULT_INDEX_PATH).resolve()

        self._catalog: Optional[List[Dict[str, Any]]] = None
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._tfidf_matrix = None   # sparse matrix (n_dbs × n_terms)
        self._db_names: Optional[List[str]] = None

        self._catalog_builder = CatalogBuilder(
            databases_dir=databases_dir,
            catalog_path=self.catalog_path,
        )

    # ------------------------------------------------------------------
    # Catalog helpers
    # ------------------------------------------------------------------

    def build_catalog(self, verbose: bool = True) -> None:
        """Build the schema catalog and persist to disk."""
        self._catalog = self._catalog_builder.build_and_save(verbose=verbose)

    def load_catalog(self) -> List[Dict[str, Any]]:
        """Load the catalog from disk, building it if necessary."""
        if self._catalog is None:
            if not self.catalog_path.exists():
                raise FileNotFoundError(
                    f"Catalog not found at {self.catalog_path}. "
                    "Call build_index() first."
                )
            self._catalog = self._catalog_builder.load_catalog()
        return self._catalog

    # ------------------------------------------------------------------
    # Index helpers
    # ------------------------------------------------------------------

    def build_index(
        self,
        rebuild_catalog: bool = False,
        verbose: bool = True,
    ) -> None:
        """Build (or rebuild) the TF-IDF index over the catalog.

        Args:
            rebuild_catalog: If True, regenerate the catalog from the SQLite
                files even if a catalog already exists on disk.
            verbose: Print progress messages.
        """
        # 1. Ensure catalog exists
        if rebuild_catalog or not self.catalog_path.exists():
            if verbose:
                print("Building catalog from SQLite databases...")
            self.build_catalog(verbose=verbose)
        else:
            if verbose:
                print(f"Loading existing catalog from {self.catalog_path}...")

        catalog = self.load_catalog()

        # 2. Fit TF-IDF vectorizer over stemmed schema texts
        if verbose:
            print(f"Fitting TF-IDF vectorizer over {len(catalog)} databases (with stemming)...")

        schema_texts = [_stem_text(entry["schema_text"]) for entry in catalog]
        self._db_names = [entry["database_name"] for entry in catalog]

        self._vectorizer = TfidfVectorizer(
            analyzer="word",
            token_pattern=r"[a-z][a-z0-9]*",  # lowercase stemmed tokens
            ngram_range=(1, 2),                 # unigrams + bigrams
            min_df=1,
            max_df=0.95,
            sublinear_tf=True,                  # log(1+tf) dampening
        )
        self._tfidf_matrix = self._vectorizer.fit_transform(schema_texts)

        # 3. Save to disk
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, "wb") as f:
            pickle.dump(
                {
                    "vectorizer": self._vectorizer,
                    "tfidf_matrix": self._tfidf_matrix,
                    "db_names": self._db_names,
                },
                f,
            )

        if verbose:
            print(f"TF-IDF index saved to {self.index_path}")
            print(f"Index shape: {self._tfidf_matrix.shape[0]} docs × {self._tfidf_matrix.shape[1]} terms")

    def load_index(self) -> None:
        """Load a pre-built TF-IDF index from disk."""
        if not self.index_path.exists():
            raise FileNotFoundError(
                f"TF-IDF index not found at {self.index_path}. "
                "Call build_index() first."
            )
        with open(self.index_path, "rb") as f:
            data = pickle.load(f)
        self._vectorizer = data["vectorizer"]
        self._tfidf_matrix = data["tfidf_matrix"]
        self._db_names = data["db_names"]

    def _ensure_index_loaded(self) -> None:
        """Load the index from disk if not already in memory."""
        if self._vectorizer is None:
            if self.index_path.exists():
                self.load_index()
                # Also load catalog for metadata
                if self._catalog is None and self.catalog_path.exists():
                    self._catalog = self._catalog_builder.load_catalog()
            else:
                raise RuntimeError(
                    "No TF-IDF index loaded. Call build_index() or load_index() first."
                )

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_question(question: str) -> str:
        """Lowercase and collapse whitespace for consistent tokenisation."""
        return re.sub(r"\s+", " ", question.strip().lower())

    def retrieve(
        self,
        question: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve the top-k most relevant databases for a natural-language question.

        Args:
            question: The natural-language query string.
            top_k: Number of ranked results to return.

        Returns:
            List of dicts, each with keys:
                - rank (int)
                - database (str)
                - score (float, 0–1)
                - matched_tables (List[str])
                - matched_columns (List[str])
        """
        if not question or not question.strip():
            return []

        self._ensure_index_loaded()
        catalog = self.load_catalog()

        # Build a dict for fast metadata lookup
        catalog_by_name = {e["database_name"]: e for e in catalog}

        # Vectorize question — stem before transforming so vocabulary aligns
        q_clean = _stem_text(self._clean_question(question))
        q_vec = self._vectorizer.transform([q_clean])

        # Cosine similarity against all database schema representations
        sims = cosine_similarity(q_vec, self._tfidf_matrix).flatten()

        # Rank by descending similarity, take top_k
        top_indices = np.argsort(sims)[::-1][:top_k]

        results: List[Dict[str, Any]] = []
        for rank, idx in enumerate(top_indices, 1):
            db_name = self._db_names[idx]
            score = float(sims[idx])

            if score == 0.0:
                # No overlap at all — still include but flag
                results.append({
                    "rank": rank,
                    "database": db_name,
                    "score": 0.0,
                    "matched_tables": [],
                    "matched_columns": [],
                })
                continue

            entry = catalog_by_name.get(db_name, {})
            matched_tables, matched_columns = self._find_matches(
                question, entry
            )

            results.append({
                "rank": rank,
                "database": db_name,
                "score": round(score, 6),
                "matched_tables": matched_tables,
                "matched_columns": matched_columns,
            })

        return results

    @staticmethod
    def _find_matches(
        question: str,
        entry: Dict[str, Any],
    ) -> tuple:
        """Find which tables and columns from the entry appear in the question.

        Uses simple substring matching on lowercased tokens to surface
        the most relevant schema elements for the result.

        Args:
            question: The original natural-language question.
            entry: A catalog entry dict.

        Returns:
            Tuple of (matched_tables, matched_columns).
        """
        q_lower = question.lower()
        # Tokenise question into words
        q_words = set(re.findall(r"[a-z][a-z0-9]*", q_lower))

        matched_tables: List[str] = []
        matched_columns: List[str] = []

        for tbl in entry.get("tables", []):
            tbl_name = tbl["table_name"]
            tbl_tokens = set(re.findall(r"[a-z][a-z0-9]*", tbl_name.lower()))
            if tbl_tokens & q_words:
                matched_tables.append(tbl_name)

            for col in tbl["columns"]:
                col_name = col["name"]
                col_tokens = set(re.findall(r"[a-z][a-z0-9]*", col_name.lower()))
                if col_tokens & q_words:
                    matched_columns.append(f"{tbl_name}.{col_name}")

        return matched_tables, matched_columns

    def format_results(self, results: List[Dict[str, Any]]) -> str:
        """Format retrieval results into a human-readable string."""
        if not results:
            return "No results found."

        lines = []
        for r in results:
            lines.append(f"{r['rank']}. database: {r['database']}")
            lines.append(f"   score: {r['score']:.4f}")
            if r["matched_tables"]:
                lines.append(f"   matched_tables: {r['matched_tables']}")
            if r["matched_columns"]:
                lines.append(f"   matched_columns: {r['matched_columns'][:10]}")
            lines.append("")
        return "\n".join(lines).rstrip()
