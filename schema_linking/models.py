"""Data models and serialization structures for Schema Linking.

Defines standard schemas for:
- Intent analysis
- Table link candidates and assignments
- Column link candidates and assignments
- Relationship paths (including composite keys)
- Full machine-readable schema linking outputs for Member 3
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class IntentInfo:
    """Structured representation of natural language query intent."""
    type: str
    entities: List[str] = field(default_factory=list)
    operations: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    operation_details: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TableMatch:
    """A matched table in the target database schema."""
    name: str
    role: str  # 'primary' | 'bridge' | 'context'
    score: float
    reason: str  # e.g., 'exact_match', 'entity_match', 'bridge_junction', 'member1_hint'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ColumnMatch:
    """A matched column in the target database schema."""
    table: str
    column: str
    score: float
    reason: str  # e.g., 'exact_match', 'primary_key', 'foreign_key_join', 'condition_match'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RelationshipMatch:
    """A foreign key relationship connecting linked tables."""
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    from_columns: List[str] = field(default_factory=list)
    to_columns: List[str] = field(default_factory=list)
    is_composite: bool = False

    def __post_init__(self):
        if not self.from_columns:
            self.from_columns = [c.strip() for c in self.from_column.split(",") if c.strip()]
        if not self.to_columns:
            self.to_columns = [c.strip() for c in self.to_column.split(",") if c.strip()]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SchemaLinkingResult:
    """Full structured output of Member 2 Schema Linking."""
    question: str
    database: str
    retrieval_score: float
    intent: IntentInfo
    tables: List[TableMatch] = field(default_factory=list)
    columns: List[ColumnMatch] = field(default_factory=list)
    relationships: List[RelationshipMatch] = field(default_factory=list)
    linked_schema: Dict[str, Any] = field(default_factory=dict)
    candidate_rank: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert entire SchemaLinkingResult to a clean Python dictionary."""
        return {
            "question": self.question,
            "intent": self.intent.to_dict(),
            "database": self.database,
            "retrieval_score": round(self.retrieval_score, 4),
            "candidate_rank": self.candidate_rank,
            "tables": [t.to_dict() for t in self.tables],
            "columns": [c.to_dict() for c in self.columns],
            "relationships": [r.to_dict() for r in self.relationships],
            "linked_schema": self.linked_schema,
            "member3_prompt_schema": self.to_member3_prompt(),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize output to a pretty JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_member3_prompt(self) -> str:
        """Generate a concise, structured textual schema for Member 3 Text-to-SQL model.

        Format:
        TABLE table_name
        - col1 (type) [PK]
        - col2 (type)

        RELATIONSHIPS:
        tableA.col1 -> tableB.col2
        """
        lines: List[str] = []

        # Tables and columns
        tables_dict = self.linked_schema.get("tables", {})
        if not tables_dict:
            # Fallback if linked_schema is empty
            for tbl in self.tables:
                lines.append(f"TABLE {tbl.name} ({tbl.role})")
                cols = [c.column for c in self.columns if c.table == tbl.name]
                for col in cols:
                    lines.append(f"  - {col}")
                lines.append("")
        else:
            for tbl_name, tbl_info in tables_dict.items():
                role = tbl_info.get("role", "primary")
                lines.append(f"TABLE {tbl_name} ({role})")
                cols = tbl_info.get("columns", [])
                pks = set(tbl_info.get("primary_keys", []))
                for col in cols:
                    col_name = col.get("name", col) if isinstance(col, dict) else str(col)
                    col_type = col.get("type", "") if isinstance(col, dict) else ""
                    type_str = f" ({col_type})" if col_type else ""
                    pk_str = " [PK]" if col_name in pks else ""
                    lines.append(f"  - {col_name}{type_str}{pk_str}")
                lines.append("")

        # Relationships
        if self.relationships:
            lines.append("RELATIONSHIPS:")
            for rel in self.relationships:
                if rel.is_composite:
                    from_cols = ", ".join(rel.from_columns)
                    to_cols = ", ".join(rel.to_columns)
                    lines.append(f"  {rel.from_table}.({from_cols}) -> {rel.to_table}.({to_cols}) [Composite FK]")
                else:
                    lines.append(f"  {rel.from_table}.{rel.from_column} -> {rel.to_table}.{rel.to_column}")

        return "\n".join(lines).strip()
