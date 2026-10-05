"""Question normalization module for Schema Linking.

Provides deterministic and testable text normalization:
- Lowercasing and whitespace collapsing
- Punctuation stripping
- Tokenization
- Suffix / morphological singularization (with irregular noun support)
- Query-preserving stopword filtering (preserves operational words like
  'most', 'highest', 'average', 'count', 'maximum', etc.)
- Multi-token n-gram generation for multi-word schema elements
"""

import re
from typing import List, Set, Tuple

# Irregular plural to singular mapping
IRREGULAR_PLURALS = {
    "people": "person",
    "men": "man",
    "women": "woman",
    "children": "child",
    "teeth": "tooth",
    "feet": "foot",
    "mice": "mouse",
    "criteria": "criterion",
    "data": "data",
    "indices": "index",
    "indexes": "index",
    "matrices": "matrix",
    "vertices": "vertex",
    "statuses": "status",
    "addresses": "address",
    "classes": "class",
    "glasses": "glass",
    "buses": "bus",
    "boxes": "box",
    "cities": "city",
    "countries": "country",
    "companies": "company",
    "categories": "category",
    "properties": "property",
    "facilities": "facility",
    "capacities": "capacity",
    "frequencies": "frequency",
    "libraries": "library",
    "parties": "party",
    "activities": "activity",
    "agencies": "agency",
    "allergies": "allergy",
    "authorities": "authority",
    "bodies": "body",
    "deliveries": "delivery",
    "factories": "factory",
    "galleries": "gallery",
    "histories": "history",
    "industries": "industry",
    "inventories": "inventory",
    "laboratories": "laboratory",
    "policies": "policy",
    "quantities": "quantity",
    "salaries": "salary",
    "territories": "territory",
    "universities": "university",
    "vacancies": "vacancy",
    "heroes": "hero",
    "potatoes": "potato",
    "tomatoes": "tomato",
    "leaves": "leaf",
    "halves": "half",
    "lives": "life",
    "wives": "wife",
    "thieves": "thief",
    "analyses": "analysis",
    "diagnoses": "diagnosis",
    "theses": "thesis",
    "synopses": "synopsis",
    "phenomena": "phenomenon",
}

# Words that should NOT be singularized even if ending in 's'
NON_PLURAL_S = {
    "status", "address", "class", "glass", "bus", "gas", "lens", "series",
    "species", "news", "canvas", "chess", "grass", "loss", "cross", "pass",
    "less", "mass", "alias", "bias", "chaos", "basis", "crisis", "axis",
    "paris", "texas", "kansas", "campus", "bonus", "virus", "chorus", "plus",
    "minus", "this", "is", "was", "has", "yes", "always", "sometimes",
    "csu_1", "press", "process", "access", "success", "business", "actress",
    "princess", "witness", "fitness", "darkness", "illness", "progress",
}

# Query-operation words that must NEVER be treated as disposable stopwords
PRESERVED_QUERY_WORDS = {
    "most", "least", "highest", "lowest", "maximum", "minimum", "max", "min",
    "before", "after", "between", "average", "avg", "count", "number", "total",
    "sum", "greater", "less", "more", "fewer", "top", "bottom", "first", "last",
    "all", "distinct", "unique", "order", "sort", "group", "having", "where",
    "not", "none", "without", "with", "in", "like", "join", "each", "every",
    "per", "how", "many", "much", "which", "what", "who", "whom", "whose",
    "where", "when", "why", "above", "below", "over", "under", "older", "younger",
    "earlier", "later", "larger", "smaller", "bigger", "longer", "shorter",
    "same", "different", "equal", "both", "either", "neither", "only",
}

# Standard English stopwords excluding PRESERVED_QUERY_WORDS
STANDARD_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "for", "by", "at", "on", "from",
    "into", "through", "during", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "can", "could", "shall", "should",
    "will", "would", "may", "might", "must", "it", "its", "they", "them", "their",
    "theirs", "he", "him", "his", "she", "her", "hers", "we", "us", "our", "ours",
    "you", "your", "yours", "i", "me", "my", "mine", "that", "these", "those",
    "there", "here", "please", "show", "give", "list", "tell", "find", "get",
    "display", "return", "provide", "select",
}


def clean_text(text: str) -> str:
    """Lowercase and normalize whitespace in a string.

    Args:
        text: Input string.

    Returns:
        Cleaned lowercase string with single spaces.
    """
    if not text:
        return ""
    # Collapse multiple whitespace characters into single space
    lowered = text.lower().strip()
    return re.sub(r"\s+", " ", lowered)


def remove_punctuation(text: str) -> str:
    """Remove punctuation from text while preserving alphanumeric tokens and underscores.

    Args:
        text: Input text.

    Returns:
        Text with punctuation replaced by space.
    """
    # Replace non-alphanumeric/non-underscore characters with space
    return re.sub(r"[^\w\s]", " ", text)


def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric and underscore tokens.

    Args:
        text: Input text.

    Returns:
        List of string tokens.
    """
    if not text:
        return []
    cleaned = clean_text(text)
    # Extract alphanumeric and underscore words
    tokens = re.findall(r"[a-z0-9]+(?:_[a-z0-9]+)*", cleaned)
    return tokens


def singularize(word: str) -> str:
    """Convert a plural English noun to its singular form deterministically.

    Args:
        word: Lowercase word string.

    Returns:
        Singularized word string.
    """
    if not word:
        return ""
    word = word.lower().strip()

    # Direct irregular dictionary check
    if word in IRREGULAR_PLURALS:
        return IRREGULAR_PLURALS[word]

    # Check words that should not lose trailing 's'
    if word in NON_PLURAL_S:
        return word

    # Words ending in -ies -> -y (e.g. cities -> city, countries -> country)
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"

    # Words ending in -ves -> -f or -fe (e.g. wolves -> wolf, lives -> life)
    if word.endswith("ves") and len(word) > 4:
        if word.endswith("lives"):
            return "life"
        if word.endswith("wives"):
            return "wife"
        return word[:-3] + "f"

    # Words ending in -sses, -shes, -ches, -xes, -zes -> drop -es
    if re.search(r"(?:ss|sh|ch|x|z)es$", word) and len(word) > 4:
        return word[:-2]

    # Words ending in -ses (e.g. statuses, responses, buses, databases)
    if word.endswith("ses") and len(word) > 4:
        if word.endswith("bases"):
            return word[:-1]  # databases -> database
        if word.endswith("courses"):
            return word[:-1]  # courses -> course
        if word.endswith("houses"):
            return word[:-1]  # houses -> house
        if word.endswith("expenses"):
            return word[:-1]  # expenses -> expense
        return word[:-2]

    # Words ending in -oes (heroes -> hero)
    if word.endswith("oes") and len(word) > 4:
        return word[:-2]

    # Regular plural ending in -s (singers -> singer, students -> student)
    if word.endswith("s") and not word.endswith("ss") and len(word) > 2:
        return word[:-1]

    return word


def normalize_token(token: str) -> str:
    """Normalize an individual token (lowercased and singularized).

    Args:
        token: Raw token.

    Returns:
        Normalized token.
    """
    return singularize(token.lower().strip())


def normalize_tokens(tokens: List[str], remove_stopwords: bool = False) -> List[str]:
    """Normalize a list of tokens by lowercasing and singularizing.

    Args:
        tokens: List of tokens.
        remove_stopwords: If True, remove non-operational stopwords.

    Returns:
        List of normalized tokens.
    """
    normalized: List[str] = []
    for tok in tokens:
        clean = normalize_token(tok)
        if not clean:
            continue
        if remove_stopwords and clean in STANDARD_STOPWORDS and clean not in PRESERVED_QUERY_WORDS:
            continue
        normalized.append(clean)
    return normalized


def normalize_question(question: str) -> str:
    """Perform full pipeline normalization on a natural-language question.

    Args:
        question: Raw user question string.

    Returns:
        Normalized space-delimited string with singularized tokens.
    """
    tokens = tokenize(question)
    norm_tokens = [normalize_token(t) for t in tokens]
    return " ".join(norm_tokens)


def extract_ngrams(tokens: List[str], min_n: int = 1, max_n: int = 3) -> List[str]:
    """Generate n-grams (1-gram to max_n-gram) joined by underscore and space.

    Args:
        tokens: List of normalized tokens.
        min_n: Minimum n-gram length.
        max_n: Maximum n-gram length.

    Returns:
        List of n-gram strings.
    """
    ngrams: List[str] = []
    n_tokens = len(tokens)
    for n in range(min_n, min(max_n + 1, n_tokens + 1)):
        for i in range(n_tokens - n + 1):
            window = tokens[i : i + n]
            ngrams.append(" ".join(window))
            if n > 1:
                ngrams.append("_".join(window))
    return ngrams


def split_identifier(identifier: str) -> List[str]:
    """Split snake_case, camelCase, or dot-separated identifier into component words.

    Examples:
        'Stadium_ID' -> ['stadium', 'id']
        'concertName' -> ['concert', 'name']
        'stadium.Capacity' -> ['stadium', 'capacity']

    Args:
        identifier: Schema identifier name.

    Returns:
        List of lowercase component word tokens.
    """
    if not identifier:
        return []
    # Replace dots and dashes with underscore
    text = identifier.replace(".", "_").replace("-", "_")
    # Split camelCase (e.g. concertName -> concert_Name)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    # Split tokens
    tokens = [t.lower() for t in text.split("_") if t]
    return tokens
