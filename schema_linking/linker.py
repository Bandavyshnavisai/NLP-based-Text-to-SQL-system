"""Schema Linker module for NLP-based Text-to-SQL system (Member 2).

Performs explainable, deterministic schema linking:
- Table relevance scoring and primary / bridge role assignment
- Column relevance scoring (exact matches, question keywords, conditions, PKs, FKs)
- Relational graph pathfinding and multi-hop bridge/junction table detection
- Composite foreign key preservation
- Controlled fallback across Member 1 top-K database candidates
"""

from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple, Union

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
    PRESERVED_QUERY_WORDS,
    STANDARD_STOPWORDS,
)
from .query_understanding import QueryUnderstanding


# Domain synonym mapping for database schemas
SYNONYM_MAP: Dict[str, Set[str]] = {
    # Generic abbreviations & core concepts
    "num": {"number", "count", "quantity", "total", "amount"},
    "nbr": {"number", "count"},
    "no": {"number", "count", "id"},
    "number": {"num", "count", "quantity", "total"},
    "desc": {"description", "summary", "detail", "explanation"},
    "description": {"desc", "summary", "detail", "explanation"},
    "qty": {"quantity", "count", "amount"},
    "dept": {"department", "division", "section", "branch", "unit", "engineering", "sales", "marketing", "finance", "hr", "accounting"},
    "department": {"dept", "division", "section", "branch", "unit", "engineering", "sales", "marketing", "finance", "hr", "accounting"},
    "engineering": {"department", "dept", "division", "field", "faculty", "major"},
    "emp": {"employee", "staff", "worker", "person"},
    "employee": {"emp", "staff", "worker", "person"},
    "worker": {"employee", "emp", "staff", "person"},
    "staff": {"employee", "emp", "worker", "person", "faculty"},
    "mgr": {"manager", "lead", "supervisor", "director", "head"},
    "manager": {"mgr", "lead", "supervisor", "director", "head"},
    "proj": {"project", "task", "assignment"},
    "project": {"proj", "task", "assignment"},
    "sal": {"salary", "wage", "pay", "income", "compensation", "amount"},
    "salary": {"sal", "wage", "pay", "income", "compensation", "amount"},
    "wage": {"salary", "sal", "pay", "income"},
    "cust": {"customer", "client", "buyer", "consumer", "patron", "user"},
    "customer": {"cust", "client", "buyer", "consumer", "patron", "user"},
    "client": {"customer", "cust", "buyer", "patron", "user"},
    "order": {"purchase", "transaction", "sale"},
    "prod": {"product", "item", "merchandise", "good"},
    "product": {"prod", "item", "merchandise", "good"},
    "item": {"product", "prod", "merchandise", "good"},
    "id": {"identifier", "code", "key", "number"},
    "loc": {"location", "place", "address", "city"},
    "yr": {"year", "date", "period"},
    "addr": {"address", "location", "residence"},
    "tel": {"telephone", "phone", "contact"},
    "phone": {"telephone", "cell", "contact"},
    "pic": {"picture", "photo", "image"},
    "photo": {"picture", "photo", "image"},
    "auth": {"author", "writer", "creator"},
    "org": {"organization", "company", "institution"},
    "avg": {"average", "mean"},
    "max": {"maximum", "highest", "most"},
    "min": {"minimum", "lowest", "least"},
    "cnt": {"count", "number"},
    "pct": {"percent", "percentage", "rate"},
    "dob": {"birthday", "birth_date", "date_of_birth", "age", "birth"},

    # Concepts & Entities
    "venue": {"stadium", "arena", "location", "hall", "ground"},
    "arena": {"stadium", "venue", "ground"},
    "stadium": {"venue", "arena", "ground"},
    "cost": {"price", "fee", "rate", "amount", "charge"},
    "price": {"cost", "fee", "rate", "amount", "charge"},
    "fee": {"cost", "price", "charge", "rate"},
    "title": {"name", "headline", "topic"},
    "name": {"title", "fullname", "first_name", "last_name", "full_name"},
    "song": {"track", "music", "tune", "title"},
    "track": {"song", "music"},
    "instructor": {"teacher", "faculty", "professor", "educator", "staff"},
    "teacher": {"instructor", "faculty", "professor", "staff"},
    "faculty": {"instructor", "teacher", "professor", "staff"},
    "professor": {"instructor", "teacher", "faculty"},
    "student": {"pupil", "scholar", "learner"},
    "city": {"location", "town", "place"},
    "country": {"nation", "state", "land", "citizenship", "nationality"},
    "nation": {"country", "state"},
    "car": {"automobile", "vehicle", "model"},
    "vehicle": {"car", "automobile", "truck"},
    "airline": {"flight", "carrier", "company"},
    "flight": {"airline", "plane", "trip"},
    "airport": {"station", "terminal"},
    "actor": {"performer", "artist", "star", "actress"},
    "actress": {"performer", "artist", "star", "actor"},
    "singer": {"artist", "vocalist", "musician", "performer"},
    "album": {"record", "release", "collection"},
    "concert": {"show", "performance", "gig", "event"},
    "match": {"game", "fixture", "contest", "competition"},
    "game": {"match", "fixture", "contest"},
    "team": {"club", "squad", "group"},
    "club": {"team", "association", "organization"},
    "doctor": {"physician", "specialist"},
    "hospital": {"clinic", "medical center"},
    "course": {"class", "subject", "module"},
    "class": {"course", "subject"},
    "hotel": {"inn", "resort", "motel"},
    "inn": {"hotel", "resort"},
    "headquarter": {"headquarter", "headquarters", "location", "city"},

    # Wh-question words
    "who": {
        "person", "user", "customer", "employee", "student", "singer", "actor",
        "actress", "author", "driver", "player", "doctor", "client", "member",
        "faculty", "staff", "guest", "visitor", "host", "candidate", "voter",
        "pilot", "wrestler", "gymnast", "scientist", "director", "manager", "name"
    },
    "where": {
        "location", "country", "city", "address", "state", "stadium", "venue",
        "place", "building", "airport", "station", "dorm", "hotel", "resort", "inn"
    },
    "when": {"year", "date", "time", "month", "day", "season", "period"},
    "age": {"age", "birth_date", "dob", "birth_year", "year", "date_of_birth"},
}


class SchemaLinker:
    """Core engine for query understanding, schema linking, and bridge-table detection."""

    def __init__(self, retriever: Optional[Any] = None):
        """Initialize the SchemaLinker.

        Args:
            retriever: Optional instance of DatabaseRetriever from Member 1.
        """
        self.retriever = retriever
        self._catalog_by_name: Optional[Dict[str, Any]] = None

    def _ensure_retriever_loaded(self) -> None:
        """Lazily initialize and load the DatabaseRetriever if not provided."""
        if self.retriever is None:
            from database_retrieval.retriever import DatabaseRetriever
            self.retriever = DatabaseRetriever()
            self.retriever.load_index()

        if self._catalog_by_name is None:
            catalog = self.retriever.load_catalog()
            self._catalog_by_name = {e["database_name"]: e for e in catalog}

    # ------------------------------------------------------------------
    # Optional Database Cell-Value Matching (SQLite)
    # ------------------------------------------------------------------

    @staticmethod
    def _find_matching_db_columns(
        db_path: Optional[str],
        tables: List[Dict[str, Any]],
        candidate_values: List[str],
    ) -> Dict[Tuple[str, str], str]:
        """Check SQLite database for cell-value matches against question filters.

        Args:
            db_path: Path to SQLite database file.
            tables: Tables metadata list from schema.
            candidate_values: List of candidate literal values / filter strings.

        Returns:
            Dict mapping (table_name, column_name) -> matched_value.
        """
        if not db_path:
            return {}
        try:
            from pathlib import Path
            import sqlite3

            p = Path(db_path)
            if not p.is_file():
                return {}

            matches: Dict[Tuple[str, str], str] = {}
            clean_cands: List[str] = []
            for val in candidate_values:
                v = str(val).strip().strip("'\"").strip()
                if len(v) >= 2 and not v.isdigit() and v.lower() not in STANDARD_STOPWORDS:
                    clean_cands.append(v)

            if not clean_cands:
                return {}

            conn = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
            cur = conn.cursor()
            for tbl in tables:
                tname = tbl["table_name"]
                quoted_tbl = f'"{tname.replace(chr(34), chr(34)+chr(34))}"'
                for col in tbl.get("columns", []):
                    cname = col["name"]
                    ctype = col.get("type", "").upper()
                    if ctype and not any(t in ctype for t in ("CHAR", "TEXT", "CLOB", "STR")):
                        continue
                    quoted_col = f'"{cname.replace(chr(34), chr(34)+chr(34))}"'
                    for cand in clean_cands:
                        try:
                            cur.execute(
                                f"SELECT 1 FROM {quoted_tbl} WHERE {quoted_col} LIKE ? LIMIT 1",
                                (f"%{cand}%",)
                            )
                            if cur.fetchone():
                                matches[(tname, cname)] = cand
                                break
                        except sqlite3.Error:
                            continue
            conn.close()
            return matches
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Table Linking
    # ------------------------------------------------------------------

    @staticmethod
    def _match_table(
        table_name: str,
        table_columns: List[Dict[str, Any]],
        q_tokens: List[str],
        q_norm_tokens: List[str],
        q_ngrams: Set[str],
        entities: List[str],
        member1_hints: Set[str],
        column_matches_count: int,
        has_value_match: bool = False,
    ) -> Tuple[float, str]:
        """Compute an explainable relevance score for a single table.

        Args:
            table_name: Table name from database schema.
            table_columns: List of columns in this table.
            q_tokens: Raw tokens from question.
            q_norm_tokens: Normalized/singularized tokens from question.
            q_ngrams: Set of question n-grams.
            entities: Extracted entities from query understanding.
            member1_hints: Set of matched table names from Member 1.
            column_matches_count: Number of columns strongly matched in this table.
            has_value_match: True if a column in this table matched a literal cell value in the DB.

        Returns:
            Tuple of (score, reason).
        """
        # 0. Direct database cell-value match on table column
        if has_value_match:
            return 0.95, "value_match"

        tbl_clean = table_name.lower().strip()
        tbl_sing = singularize(tbl_clean)
        tbl_tokens = [singularize(t) for t in split_identifier(table_name)]

        # 1. Exact full name match (e.g. 'stadium', 'concert_singer')
        if tbl_clean in q_ngrams or tbl_sing in q_ngrams:
            return 1.0, "exact_match"

        # 2. Singularized entity match (e.g. question has 'singers' -> entity 'singer')
        if tbl_sing in entities or tbl_clean in entities:
            return 0.95, "entity_match"

        # 3. Multi-word table name exact match (e.g. 'flight_company' -> 'flight company')
        space_name = " ".join(tbl_tokens)
        if space_name in q_ngrams:
            return 0.95, "exact_match"

        # 4. Table name tokens subset of question tokens (e.g. 'course_teach' where question has 'course' and 'teach')
        if tbl_tokens and all(t in q_norm_tokens or t in entities for t in tbl_tokens):
            return 0.92, "entity_match"

        # 5. Single-token table name matching normalized question token
        if len(tbl_tokens) == 1 and tbl_tokens[0] in q_norm_tokens:
            return 0.90, "normalized_match"

        # 6. Compound / Junction table containing multiple question entities
        overlap = [t for t in tbl_tokens if t in q_norm_tokens or t in entities]
        if len(overlap) >= 2:
            return 0.88, "junction_entity_overlap"

        # 7. Check if table column is uniquely mentioned in question (e.g. 'stadium_id' or distinct col)
        col_names = [c["name"].lower() for c in table_columns]
        for cname in col_names:
            c_sing = singularize(cname)
            if cname in q_ngrams or c_sing in q_ngrams:
                if cname not in ("id", "code", "name", "type", "date"):
                    return 0.82, "column_mention_match"

        # 8. Synonym matching on table name
        for t_tok in tbl_tokens:
            synonyms = SYNONYM_MAP.get(t_tok, set())
            if any(syn in q_norm_tokens or syn in entities for syn in synonyms):
                return 0.85, "synonym_match"

        # 9. Partial token overlap
        if overlap:
            overlap_ratio = len(overlap) / len(tbl_tokens)
            score = 0.50 + 0.30 * overlap_ratio
            return round(score, 3), "token_overlap"

        # 10. Member 1 hint boost
        if table_name in member1_hints:
            return 0.70, "member1_hint"

        # 11. Column evidence boost (table contains matched columns)
        if column_matches_count >= 2:
            return 0.65, "column_evidence"
        elif column_matches_count == 1:
            return 0.45, "weak_column_evidence"

        return 0.0, "unmatched"

    def link_tables(
        self,
        schema: Dict[str, Any],
        question: str,
        intent: IntentInfo,
        member1_table_hints: Optional[List[str]] = None,
        member1_column_hints: Optional[List[str]] = None,
        tables_with_value_matches: Optional[Set[str]] = None,
    ) -> List[TableMatch]:
        """Score all tables in the schema and identify relevant candidate tables.

        Args:
            schema: Database schema dict.
            question: Cleaned question string.
            intent: Query intent analysis object.
            member1_table_hints: Matched tables from Member 1 retriever.
            member1_column_hints: Matched columns from Member 1 retriever.
            tables_with_value_matches: Optional set of table names with cell-value matches.

        Returns:
            List of TableMatch objects for tables in the schema.
        """
        q_tokens = tokenize(question)
        q_norm_tokens = normalize_tokens(q_tokens)
        q_ngrams = set(extract_ngrams(q_norm_tokens, min_n=1, max_n=3))
        q_ngrams.update(extract_ngrams(q_tokens, min_n=1, max_n=3))

        hints_set = set(member1_table_hints or [])
        col_hints_set = set(member1_column_hints or [])

        # Count column hints per table
        col_count_by_table: Dict[str, int] = {}
        for col_hint in col_hints_set:
            if "." in col_hint:
                tbl, _ = col_hint.split(".", 1)
                col_count_by_table[tbl] = col_count_by_table.get(tbl, 0) + 1

        val_tables = tables_with_value_matches or set()
        matches: List[TableMatch] = []
        for tbl in schema.get("tables", []):
            tbl_name = tbl["table_name"]
            c_count = col_count_by_table.get(tbl_name, 0)
            has_val = tbl_name in val_tables
            score, reason = self._match_table(
                tbl_name,
                tbl.get("columns", []),
                q_tokens,
                q_norm_tokens,
                q_ngrams,
                intent.entities,
                hints_set,
                c_count,
                has_value_match=has_val,
            )

            # Determine initial role
            role = "primary" if score >= 0.70 else ("context" if score > 0 else "unmatched")
            matches.append(TableMatch(
                name=tbl_name,
                role=role,
                score=score,
                reason=reason,
            ))

        # Sort matches by score descending
        matches.sort(key=lambda m: m.score, reverse=True)

        # Ensure at least one primary table if any table has positive score
        primary_exists = any(m.role == "primary" for m in matches)
        if not primary_exists and matches and matches[0].score > 0:
            matches[0].role = "primary"

        return matches

    # ------------------------------------------------------------------
    # Relationship & Bridge Table Detection
    # ------------------------------------------------------------------

    @staticmethod
    def _build_relationship_graph(
        relationships: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Build an undirected adjacency list from foreign key relationships.

        Args:
            relationships: List of FK relationship dicts from schema.

        Returns:
            Dict mapping table_name -> list of edge dicts.
        """
        graph: Dict[str, List[Dict[str, Any]]] = {}
        for rel in relationships:
            src = rel["source_table"]
            tgt = rel["target_table"]

            if src not in graph:
                graph[src] = []
            if tgt not in graph:
                graph[tgt] = []

            graph[src].append({
                "neighbor": tgt,
                "relationship": rel,
                "direction": "outgoing",
            })
            graph[tgt].append({
                "neighbor": src,
                "relationship": rel,
                "direction": "incoming",
            })
        return graph

    @classmethod
    def find_shortest_path(
        cls,
        graph: Dict[str, List[Dict[str, Any]]],
        start: str,
        goal: str,
    ) -> Optional[List[Tuple[str, Dict[str, Any]]]]:
        """Find the shortest foreign key path between two tables using BFS.

        Args:
            graph: FK adjacency graph.
            start: Starting table name.
            goal: Destination table name.

        Returns:
            List of (next_table, relationship_dict) tuples along the path, or None if no path.
        """
        if start == goal:
            return []
        if start not in graph or goal not in graph:
            return None

        queue: deque[Tuple[str, List[Tuple[str, Dict[str, Any]]]]] = deque([(start, [])])
        visited: Set[str] = {start}

        while queue:
            current, path = queue.popleft()
            if current == goal:
                return path

            for edge in graph.get(current, []):
                neighbor = edge["neighbor"]
                if neighbor not in visited:
                    visited.add(neighbor)
                    new_path = list(path)
                    new_path.append((neighbor, edge["relationship"]))
                    queue.append((neighbor, new_path))

        return None

    @classmethod
    def detect_bridge_tables_and_relationships(
        cls,
        table_matches: List[TableMatch],
        relationships: List[Dict[str, Any]],
    ) -> Tuple[List[TableMatch], List[RelationshipMatch]]:
        """Connect all primary tables via the FK graph and identify bridge tables.

        For every pair of primary tables, uses BFS to find the shortest join path.
        Any intermediate table on the shortest path is assigned the role 'bridge'.

        Args:
            table_matches: Current list of TableMatch objects.
            relationships: List of schema relationship dicts.

        Returns:
            Tuple of (updated_table_matches, selected_relationships).
        """
        graph = cls._build_relationship_graph(relationships)
        table_dict = {t.name: t for t in table_matches}

        primary_tables = [t.name for t in table_matches if t.role == "primary"]
        selected_rel_set: Set[Tuple[str, str, str, str]] = set()
        selected_relationships: List[RelationshipMatch] = []
        bridge_tables_found: Set[str] = set()

        def add_rel(rel_dict: Dict[str, Any]):
            key = (
                rel_dict["source_table"],
                rel_dict["source_column"],
                rel_dict["target_table"],
                rel_dict["target_column"],
            )
            if key not in selected_rel_set:
                selected_rel_set.add(key)
                selected_relationships.append(RelationshipMatch(
                    from_table=rel_dict["source_table"],
                    from_column=rel_dict["source_column"],
                    to_table=rel_dict["target_table"],
                    to_column=rel_dict["target_column"],
                    from_columns=rel_dict.get("source_columns", [rel_dict["source_column"]]),
                    to_columns=rel_dict.get("target_columns", [rel_dict["target_column"]]),
                    is_composite=rel_dict.get("is_composite", False),
                ))

        # 1. Multi-primary connections (shortest paths)
        if len(primary_tables) >= 2:
            for i in range(len(primary_tables)):
                for j in range(i + 1, len(primary_tables)):
                    t1, t2 = primary_tables[i], primary_tables[j]
                    path = cls.find_shortest_path(graph, t1, t2)
                    if path is not None:
                        for step_table, rel_dict in path:
                            add_rel(rel_dict)
                            if step_table != t1 and step_table != t2:
                                if step_table not in primary_tables:
                                    bridge_tables_found.add(step_table)

        # 2. Check direct relationships between any active tables
        active_tables = set(primary_tables) | bridge_tables_found
        for rel in relationships:
            src, tgt = rel["source_table"], rel["target_table"]
            if src in active_tables and tgt in active_tables:
                add_rel(rel)

        # 3. Update table matches list with bridge tables
        for b_name in bridge_tables_found:
            if b_name in table_dict:
                table_dict[b_name].role = "bridge"
                table_dict[b_name].reason = "bridge_junction"
                table_dict[b_name].score = max(table_dict[b_name].score, 0.85)
            else:
                new_match = TableMatch(
                    name=b_name,
                    role="bridge",
                    score=0.85,
                    reason="bridge_junction",
                )
                table_matches.append(new_match)
                table_dict[b_name] = new_match

        # Filter out unneeded non-participating tables from final active set
        active_matches = [
            t for t in table_matches
            if t.role in ("primary", "bridge")
        ]
        # Sort so primary tables come first, then bridge tables
        active_matches.sort(
            key=lambda t: (0 if t.role == "primary" else 1, -t.score)
        )

        return active_matches, selected_relationships

    # ------------------------------------------------------------------
    # Column Linking
    # ------------------------------------------------------------------

    @staticmethod
    def _match_column(
        table_name: str,
        column_dict: Dict[str, Any],
        q_tokens: List[str],
        q_norm_tokens: List[str],
        q_ngrams: Set[str],
        conditions: List[str],
        member1_col_hints: Set[str],
        is_pk: bool,
        is_fk: bool,
        is_value_match: bool = False,
        tbl_role: str = "context",
    ) -> Tuple[float, str]:
        """Compute an explainable relevance score for a column in an active table.

        Args:
            table_name: Parent table name.
            column_dict: Column definition dict.
            q_tokens: Raw question tokens.
            q_norm_tokens: Normalized tokens from question.
            q_ngrams: Set of question n-grams.
            conditions: Conditions extracted from query understanding.
            member1_col_hints: Matched columns from Member 1.
            is_pk: True if column is a primary key.
            is_fk: True if column is part of a selected foreign key relationship.
            is_value_match: True if column value matched a cell in the database.
            tbl_role: Role of the parent table ('primary', 'bridge', 'context').

        Returns:
            Tuple of (score, reason).
        """
        # 0. Direct database cell-value match
        if is_value_match:
            return 0.95, "condition_match"

        col_name = column_dict["name"]
        col_clean = col_name.lower().strip()
        col_sing = singularize(col_clean)
        col_tokens = [singularize(t) for t in split_identifier(col_name)]
        full_name = f"{table_name}.{col_name}".lower()

        # 1. Exact column name match in question n-grams
        if col_clean in q_ngrams or col_sing in q_ngrams or " ".join(col_tokens) in q_ngrams:
            # Exclude generic 'id' from 1.0 exact match unless explicitly asked
            if col_clean == "id" and "id" not in q_tokens:
                pass
            else:
                return 1.0, "exact_match"

        # 2. Condition match: column relates to a filter phrase or value
        for cond in conditions:
            cond_clean = cond.lower()
            if col_clean in cond_clean or any(t in cond_clean for t in col_tokens if len(t) > 2):
                return 0.95, "condition_match"

        # 3. Foreign key join column active in a relationship
        if is_fk:
            return 0.90, "foreign_key_join"

        # 4. Synonym match
        for c_tok in col_tokens:
            synonyms = SYNONYM_MAP.get(c_tok, set())
            if any(syn in q_norm_tokens for syn in synonyms):
                return 0.85, "synonym_match"

        # 5. Primary entity descriptor column (e.g. name, title, <tbl>_name)
        tbl_clean = table_name.lower().strip()
        tbl_sing = singularize(tbl_clean)
        if tbl_role == "primary" and (
            col_clean in ("name", "full_name", "title")
            or col_clean == f"{tbl_sing}_name"
            or col_clean == f"{tbl_clean}_name"
        ):
            return 0.85, "entity_descriptor"

        # 6. Member 1 hint match
        if full_name in member1_col_hints or col_name in member1_col_hints:
            return 0.85, "member1_hint"

        # 7. Partial token overlap
        overlap = [t for t in col_tokens if t in q_norm_tokens and t not in ("id", "pk", "fk")]
        if overlap:
            return 0.80, "token_overlap"

        # 8. Primary key column of an active table
        if is_pk:
            return 0.75, "primary_key"

        return 0.0, "unmatched"

    def link_columns(
        self,
        schema: Dict[str, Any],
        active_tables: List[TableMatch],
        relationships: List[RelationshipMatch],
        question: str,
        conditions: List[str],
        member1_column_hints: Optional[List[str]] = None,
        value_matches: Optional[Dict[Tuple[str, str], str]] = None,
    ) -> List[ColumnMatch]:
        """Identify relevant columns for all active (primary and bridge) tables.

        Args:
            schema: Full schema dict.
            active_tables: List of active TableMatch objects.
            relationships: List of selected RelationshipMatch objects.
            question: Cleaned question string.
            conditions: Extracted query conditions.
            member1_column_hints: Member 1 column match hints.
            value_matches: Optional dict mapping (table, column) -> matched value.

        Returns:
            List of ColumnMatch objects.
        """
        q_tokens = tokenize(question)
        q_norm_tokens = normalize_tokens(q_tokens)
        q_ngrams = set(extract_ngrams(q_norm_tokens, min_n=1, max_n=3))
        q_ngrams.update(extract_ngrams(q_tokens, min_n=1, max_n=3))

        hints_set = {h.lower() for h in (member1_column_hints or [])}
        val_map = value_matches or {}

        # Build sets of PK and FK columns
        fk_columns: Set[Tuple[str, str]] = set()
        for rel in relationships:
            for c in rel.from_columns:
                fk_columns.add((rel.from_table, c))
            for c in rel.to_columns:
                fk_columns.add((rel.to_table, c))

        column_matches: List[ColumnMatch] = []
        table_meta_by_name = {t["table_name"]: t for t in schema.get("tables", [])}

        for tbl_match in active_tables:
            tbl_name = tbl_match.name
            tbl_role = tbl_match.role
            tbl_meta = table_meta_by_name.get(tbl_name)
            if not tbl_meta:
                continue

            pks_set = set(tbl_meta.get("primary_keys", []))

            for col in tbl_meta.get("columns", []):
                col_name = col["name"]
                is_pk = col_name in pks_set
                is_fk = (tbl_name, col_name) in fk_columns
                is_val = (tbl_name, col_name) in val_map

                score, reason = self._match_column(
                    tbl_name,
                    col,
                    q_tokens,
                    q_norm_tokens,
                    q_ngrams,
                    conditions,
                    hints_set,
                    is_pk,
                    is_fk,
                    is_value_match=is_val,
                    tbl_role=tbl_role,
                )

                # Include columns with meaningful relevance score
                if score >= 0.70:
                    column_matches.append(ColumnMatch(
                        table=tbl_name,
                        column=col_name,
                        score=score,
                        reason=reason,
                    ))

        # Sort columns: exact/condition matches first, then FK/PK
        column_matches.sort(key=lambda c: (c.table, -c.score))
        return column_matches

    # ------------------------------------------------------------------
    # End-to-End Pipeline
    # ------------------------------------------------------------------

    def link(
        self,
        question: str,
        top_k: int = 5,
        target_db: Optional[str] = None,
        target_schema: Optional[Dict[str, Any]] = None,
    ) -> SchemaLinkingResult:
        """Perform full query understanding and schema linking for a question.

        Supports both:
        1. Standalone / known database evaluation (target_db / target_schema provided)
        2. Full pipeline with Member 1 retrieval & controlled fallback

        Args:
            question: Natural language question.
            top_k: Number of retrieved databases to examine.
            target_db: Optional database name override.
            target_schema: Optional schema dictionary override.

        Returns:
            Structured SchemaLinkingResult object.
        """
        # Step 1: Query normalization and intent understanding
        intent_dict = QueryUnderstanding.analyze(question)
        intent = IntentInfo(
            type=intent_dict["intent_type"],
            entities=intent_dict["entities"],
            operations=intent_dict["operations"],
            conditions=intent_dict["conditions"],
            operation_details=intent_dict["operation_details"],
        )

        if not question or not question.strip():
            return SchemaLinkingResult(
                question="",
                database="",
                retrieval_score=0.0,
                intent=intent,
            )

        # Step 2: Database selection
        chosen_db: Optional[str] = None
        chosen_schema: Optional[Dict[str, Any]] = None
        retrieval_score: float = 1.0
        candidate_rank: int = 1
        table_hints: List[str] = []
        column_hints: List[str] = []

        if target_schema is not None:
            chosen_schema = target_schema
            chosen_db = target_db or target_schema.get("database_name", "unknown")
        elif target_db is not None:
            self._ensure_retriever_loaded()
            chosen_db = target_db
            chosen_schema = self._catalog_by_name.get(target_db)
            if chosen_schema is None:
                raise ValueError(f"Database '{target_db}' not found in catalog.")
        else:
            # Full retrieval from Member 1
            self._ensure_retriever_loaded()
            candidates = self.retriever.retrieve(question, top_k=top_k)

            if not candidates:
                return SchemaLinkingResult(
                    question=question,
                    database="none",
                    retrieval_score=0.0,
                    intent=intent,
                )

            # Controlled fallback: evaluate top candidates in order
            best_candidate = candidates[0]
            best_db = best_candidate["database"]
            best_schema = self._catalog_by_name.get(best_db)

            # If top candidate score is 0.0 or has 0 table overlap, check if rank 2/3 has better entity match
            if best_candidate["score"] == 0.0 and len(candidates) > 1:
                for cand in candidates[1:]:
                    cand_db = cand["database"]
                    cand_schema = self._catalog_by_name.get(cand_db)
                    if cand_schema:
                        # Quick table match check
                        test_matches = self.link_tables(
                            cand_schema,
                            question,
                            intent,
                            cand.get("matched_tables", []),
                            cand.get("matched_columns", []),
                        )
                        if any(m.score >= 0.80 for m in test_matches):
                            best_candidate = cand
                            best_db = cand_db
                            best_schema = cand_schema
                            break

            chosen_db = best_db
            chosen_schema = best_schema
            retrieval_score = float(best_candidate.get("score", 0.0))
            candidate_rank = int(best_candidate.get("rank", 1))
            table_hints = best_candidate.get("matched_tables", [])
            column_hints = best_candidate.get("matched_columns", [])

        if chosen_schema is None:
            return SchemaLinkingResult(
                question=question,
                database=chosen_db or "unknown",
                retrieval_score=retrieval_score,
                intent=intent,
                candidate_rank=candidate_rank,
            )

        # Step 3: Optional Cell-Value Matching in Database
        db_path = chosen_schema.get("database_path")
        candidate_values = list(intent.conditions) + list(intent.entities)
        value_matches = self._find_matching_db_columns(
            db_path,
            chosen_schema.get("tables", []),
            candidate_values,
        )
        tables_with_values = {tbl for (tbl, _) in value_matches.keys()}

        # Step 4: Table Matching
        table_matches = self.link_tables(
            chosen_schema,
            question,
            intent,
            table_hints,
            column_hints,
            tables_with_value_matches=tables_with_values,
        )

        # Step 5: Relationship Analysis & Bridge Table Detection
        relationships_raw = chosen_schema.get("relationships", [])
        active_tables, selected_relationships = self.detect_bridge_tables_and_relationships(
            table_matches,
            relationships_raw,
        )

        # Step 6: Column Matching
        column_matches = self.link_columns(
            chosen_schema,
            active_tables,
            selected_relationships,
            question,
            intent.conditions,
            column_hints,
            value_matches=value_matches,
        )

        # Step 6: Construct linked_schema dictionary
        linked_tables_dict: Dict[str, Any] = {}
        table_meta_by_name = {t["table_name"]: t for t in chosen_schema.get("tables", [])}

        for tm in active_tables:
            meta = table_meta_by_name.get(tm.name, {})
            # Columns in table that were matched or PKs
            matched_cols_for_table = [
                c.column for c in column_matches if c.table == tm.name
            ]
            # Column dicts
            cols_info = [
                c for c in meta.get("columns", [])
                if c["name"] in matched_cols_for_table
            ]
            if not cols_info:
                # If no column specifically linked, include PKs or all columns
                cols_info = meta.get("columns", [])

            linked_tables_dict[tm.name] = {
                "role": tm.role,
                "score": tm.score,
                "primary_keys": meta.get("primary_keys", []),
                "columns": cols_info,
            }

        linked_schema_data = {
            "database_name": chosen_db,
            "total_linked_tables": len(active_tables),
            "tables": linked_tables_dict,
            "relationships": [r.to_dict() for r in selected_relationships],
        }

        return SchemaLinkingResult(
            question=question,
            database=chosen_db,
            retrieval_score=retrieval_score,
            intent=intent,
            tables=active_tables,
            columns=column_matches,
            relationships=selected_relationships,
            linked_schema=linked_schema_data,
            candidate_rank=candidate_rank,
        )
