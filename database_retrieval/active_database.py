"""ActiveDatabase — Represents a validated, loaded user-provided database.

Encapsulates all information needed by downstream pipeline stages
(schema linking, text-to-SQL) about a single active database.

This is the output of :func:`database_retrieval.loader.load_database` and
is consumed by :class:`schema_linking.SchemaLinker` via its
``target_schema`` parameter.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict


@dataclass
class ActiveDatabase:
    """Represents a validated, schema-extracted user database.

    Attributes:
        path: Absolute path to the SQLite file.
        database_name: Logical name of the database (derived from the file stem).
        database_type: Database engine type; currently always ``"sqlite"``.
        schema: Structured schema dict in the standard Member-1 format::

            {
                "database_name": str,
                "database_path": str,
                "total_tables":  int,
                "tables": [...],       # List[TableDict]
                "relationships": [...] # List[RelDict]
            }

        This dict is directly compatible with
        :meth:`schema_linking.SchemaLinker.link` ``target_schema`` parameter.
    """

    path: Path
    database_name: str
    database_type: str = "sqlite"
    schema: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_schema(self) -> Dict[str, Any]:
        """Return the schema dict for direct use with SchemaLinker.

        Returns:
            Schema dict compatible with Member 2's ``target_schema`` parameter.
        """
        return self.schema

    @property
    def table_names(self):
        """List of user table names in the database."""
        return [t["table_name"] for t in self.schema.get("tables", [])]

    @property
    def total_tables(self) -> int:
        """Number of user tables."""
        return self.schema.get("total_tables", 0)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary (path rendered as string)."""
        return {
            "path": str(self.path),
            "database_name": self.database_name,
            "database_type": self.database_type,
            "schema": self.schema,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"ActiveDatabase(name={self.database_name!r}, "
            f"type={self.database_type!r}, "
            f"tables={self.table_names})"
        )
