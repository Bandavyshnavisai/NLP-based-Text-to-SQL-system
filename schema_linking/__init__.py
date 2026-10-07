"""Schema Linking and Query Understanding package (Member 2).

Provides:
- SchemaLinker: Full pipeline linking natural-language questions to database schemas.
- QueryUnderstanding: Semantic intent, entity, operation, and condition extraction.
- Models: TableMatch, ColumnMatch, RelationshipMatch, SchemaLinkingResult, IntentInfo.
- Normalizer: Tokenization, singularization, and query-preserving text normalization.
"""

from .linker import SchemaLinker
from .models import (
    ColumnMatch,
    IntentInfo,
    RelationshipMatch,
    SchemaLinkingResult,
    TableMatch,
)
from .normalizer import (
    clean_text,
    extract_ngrams,
    normalize_question,
    normalize_token,
    normalize_tokens,
    singularize,
    split_identifier,
    tokenize,
)
from .query_understanding import QueryUnderstanding

__all__ = [
    "SchemaLinker",
    "QueryUnderstanding",
    "SchemaLinkingResult",
    "TableMatch",
    "ColumnMatch",
    "RelationshipMatch",
    "IntentInfo",
    "clean_text",
    "tokenize",
    "singularize",
    "normalize_tokens",
    "normalize_question",
    "split_identifier",
    "extract_ngrams",
]
