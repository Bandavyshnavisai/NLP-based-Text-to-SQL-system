"""Query Understanding module for Schema Linking.

Extracts semantic query concepts deterministically without external LLM calls:
- Intent classification (count, aggregation, ranking, filtering, retrieval, etc.)
- Entity extraction (potential domain objects / table / column targets)
- Operation detection (aggregation, comparison, sorting, ranking)
- Condition extraction (string literals, numeric constants, filter phrases)
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple
from .normalizer import (
    clean_text,
    extract_ngrams,
    normalize_token,
    normalize_tokens,
    singularize,
    tokenize,
    PRESERVED_QUERY_WORDS,
    STANDARD_STOPWORDS,
)

# Aggregation keywords mapping
AGGREGATION_KEYWORDS = {
    "count": ["how many", "number of", "count of", "total number of", "count", "num"],
    "sum": ["total", "sum of", "sum", "combined", "cumulative"],
    "average": ["average", "avg", "mean", "per capita"],
    "maximum": ["maximum", "max", "highest", "most", "largest", "greatest", "oldest", "longest", "maximum of", "top"],
    "minimum": ["minimum", "min", "lowest", "least", "smallest", "fewest", "youngest", "shortest", "minimum of", "bottom"],
}

# Ordering keywords mapping
ORDERING_KEYWORDS = {
    "descending": [
        "most", "highest", "largest", "greatest", "top", "maximum", "max",
        "descending", "desc", "best", "oldest", "longest", "heaviest", "highest to lowest"
    ],
    "ascending": [
        "least", "lowest", "smallest", "fewest", "bottom", "minimum", "min",
        "ascending", "asc", "worst", "youngest", "shortest", "lightest", "lowest to highest"
    ],
}

# Comparison keywords mapping
COMPARISON_KEYWORDS = {
    "greater_than": [
        "more than", "greater than", "higher than", "above", "exceeding",
        "older than", "longer than", "larger than", "bigger than", "over", "after"
    ],
    "less_than": [
        "less than", "fewer than", "lower than", "below", "under",
        "younger than", "shorter than", "smaller than", "before"
    ],
    "between": ["between", "from ... to ...", "in the range of"],
    "equal": ["equal to", "is", "are", "named", "called", "in", "with", "same"],
    "like": ["like", "starting with", "starts with", "ending with", "ends with", "containing", "contains"],
}

# Question verbs / phrases to skip when extracting entities
ENTITY_DISALLOWED_WORDS = {
    "what", "which", "who", "whom", "whose", "where", "when", "why", "how",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "can", "could", "should", "would", "will", "may",
    "show", "list", "give", "tell", "find", "get", "display", "return", "provide",
    "select", "all", "each", "every", "many", "much", "more", "most", "less",
    "least", "top", "bottom", "first", "last", "any", "some", "none", "not",
    "there", "here", "the", "a", "an", "of", "in", "on", "at", "to", "for",
    "with", "by", "from", "and", "or", "than", "between", "among", "per",
}


class QueryUnderstanding:
    """Analyzes natural language questions and extracts structured intent representations."""

    @staticmethod
    def extract_quoted_conditions(question: str) -> List[str]:
        """Extract explicit string literals within quotes (single or double quotes).

        Args:
            question: Raw natural-language question.

        Returns:
            List of quoted string literals.
        """
        quotes = re.findall(r"['\"]([^'\"]+)['\"]", question)
        return [q.strip() for q in quotes if q.strip()]

    @staticmethod
    def extract_numeric_conditions(question: str) -> List[str]:
        """Extract numeric constants (integers, floats, years) from the question.

        Args:
            question: Raw natural-language question.

        Returns:
            List of string representations of numbers found.
        """
        # Exclude numbers that are part of identifiers or ordinal numbers like 1st, 2nd
        nums = re.findall(r"\b\d+(?:\.\d+)?\b", question)
        return nums

    @staticmethod
    def extract_filter_phrases(question: str) -> List[str]:
        """Extract semantic condition / filter phrases based on prepositions.

        Examples:
            'in the computer science department' -> 'computer science'
            'born after 1990' -> '1990'
            'with status active' -> 'active'

        Args:
            question: Natural language question.

        Returns:
            List of identified filter strings.
        """
        conditions: List[str] = []

        # 1. Quoted strings are direct conditions
        quoted = QueryUnderstanding.extract_quoted_conditions(question)
        conditions.extend(quoted)

        # 2. Extract prepositional phrases: in/for/of/with/named [phrase] [table_name]
        # Pattern: (in|enrolled in|majoring in|from|for|with|named|called) (the)? ([A-Za-z0-9 ]+?) (department|country|city|state|year|status|category|group|type|name)?
        matches = re.findall(
            r"\b(?:enrolled in|majored in|majoring in|located in|born in|living in|from|named|called|with name|with status|with type|of type)\s+(?:the\s+)?([A-Za-z0-9\s]+?)(?:\s+(?:department|company|country|city|stadium|hotel|school|college|university|club|airport|team|band|season|room|building|area|district|store|branch|division|state))?(?=[,\.]|\s+who|\s+which|\s+that|\s+and|\s+or|\s+with|\s+whose|$)",
            question,
            re.IGNORECASE,
        )
        for m in matches:
            cleaned = m.strip()
            # Filter out non-condition words
            if cleaned and cleaned.lower() not in ENTITY_DISALLOWED_WORDS and len(cleaned) > 1:
                if cleaned not in conditions:
                    conditions.append(cleaned)

        # 3. Numeric values
        nums = QueryUnderstanding.extract_numeric_conditions(question)
        for n in nums:
            if n not in conditions:
                conditions.append(n)

        return conditions

    @staticmethod
    def detect_operations(question: str) -> Dict[str, List[str]]:
        """Detect aggregation, ordering, and comparison operations in the question.

        Args:
            question: Raw or cleaned question string.

        Returns:
            Dict containing detected operation categories and their specific operators.
        """
        q_lower = question.lower()
        q_clean = clean_text(question)

        detected_aggs: List[str] = []
        for agg_op, patterns in AGGREGATION_KEYWORDS.items():
            for pat in patterns:
                # Check pattern with word boundaries
                if re.search(r"\b" + re.escape(pat) + r"\b", q_lower):
                    if agg_op not in detected_aggs:
                        detected_aggs.append(agg_op)
                    break

        detected_orderings: List[str] = []
        for order_op, patterns in ORDERING_KEYWORDS.items():
            for pat in patterns:
                if re.search(r"\b" + re.escape(pat) + r"\b", q_lower):
                    if order_op not in detected_orderings:
                        detected_orderings.append(order_op)
                    break

        detected_comparisons: List[str] = []
        for comp_op, patterns in COMPARISON_KEYWORDS.items():
            for pat in patterns:
                if re.search(r"\b" + re.escape(pat) + r"\b", q_lower):
                    if comp_op not in detected_comparisons:
                        detected_comparisons.append(comp_op)
                    break

        return {
            "aggregations": detected_aggs,
            "orderings": detected_orderings,
            "comparisons": detected_comparisons,
        }

    @staticmethod
    def classify_intent_type(
        question: str,
        operations: Dict[str, List[str]],
        conditions: List[str]
    ) -> str:
        """Classify the primary query intent type.

        Intent types:
        - 'count': question asks for a count/quantity
        - 'ranking': question asks for extremes/top/bottom (most, least, highest)
        - 'aggregation': question computes avg, sum, min, max
        - 'filtering': question retrieves items satisfying specific condition filters
        - 'retrieval': standard projection / select query

        Args:
            question: Natural language question.
            operations: Detected operations dict.
            conditions: Extracted conditions list.

        Returns:
            Intent type string.
        """
        q_lower = question.lower()

        # Check for count questions
        if "count" in operations["aggregations"] or q_lower.startswith("how many") or "number of" in q_lower:
            return "count"

        # Check for ranking questions
        if operations["orderings"] or any(w in q_lower for w in ["most", "least", "highest", "lowest", "top", "bottom"]):
            return "ranking"

        # Check for other aggregations (average, sum, max, min)
        if any(op in operations["aggregations"] for op in ["average", "sum", "maximum", "minimum"]):
            return "aggregation"

        # Check for filtering
        if conditions or operations["comparisons"]:
            return "filtering"

        return "retrieval"

    @staticmethod
    def extract_entities(question: str) -> List[str]:
        """Extract candidate domain entities / concepts from question tokens and phrases.

        Args:
            question: Raw natural-language question.

        Returns:
            List of singularized candidate entity strings (unigrams and multi-word phrases).
        """
        raw_tokens = tokenize(question)
        if not raw_tokens:
            return []

        entities: List[str] = []
        
        # 1. Filter out known functional stopwords and question markers
        cand_tokens = [
            t for t in raw_tokens
            if t.lower() not in ENTITY_DISALLOWED_WORDS
            and not t.isdigit()
            and len(t) > 1
        ]

        # 2. Add singularized candidate tokens
        for t in cand_tokens:
            sing = singularize(t)
            if sing and sing not in entities and sing not in ENTITY_DISALLOWED_WORDS:
                entities.append(sing)

        # 3. Add 2-gram noun phrases (e.g. 'concert singer', 'computer science', 'course teach')
        norm_tokens = [singularize(t) for t in raw_tokens]
        for i in range(len(norm_tokens) - 1):
            t1, t2 = norm_tokens[i], norm_tokens[i + 1]
            if (
                t1 not in ENTITY_DISALLOWED_WORDS
                and t2 not in ENTITY_DISALLOWED_WORDS
                and not t1.isdigit()
                and not t2.isdigit()
            ):
                phrase = f"{t1}_{t2}"
                if phrase not in entities:
                    entities.append(phrase)
                space_phrase = f"{t1} {t2}"
                if space_phrase not in entities:
                    entities.append(space_phrase)

        return entities

    @classmethod
    def analyze(cls, question: str) -> Dict[str, Any]:
        """Perform comprehensive query understanding on a user question.

        Args:
            question: Natural language question.

        Returns:
            Dict containing:
                - question (str)
                - intent_type (str)
                - entities (List[str])
                - operations (List[str])
                - conditions (List[str])
                - operation_details (Dict[str, List[str]])
        """
        if not question or not question.strip():
            return {
                "question": "",
                "intent_type": "unknown",
                "entities": [],
                "operations": [],
                "conditions": [],
                "operation_details": {
                    "aggregations": [],
                    "orderings": [],
                    "comparisons": [],
                },
            }

        operations = cls.detect_operations(question)
        conditions = cls.extract_filter_phrases(question)
        intent_type = cls.classify_intent_type(question, operations, conditions)
        entities = cls.extract_entities(question)

        # Flat list of all operation labels for consumption
        flat_ops: List[str] = []
        for op_list in operations.values():
            for op in op_list:
                if op not in flat_ops:
                    flat_ops.append(op)

        return {
            "question": question.strip(),
            "intent_type": intent_type,
            "entities": entities,
            "operations": flat_ops,
            "conditions": conditions,
            "operation_details": operations,
        }
