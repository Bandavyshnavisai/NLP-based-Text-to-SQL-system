"""Database retrieval and schema extraction module.

Provides:
    - SchemaExtractor: Extract structured schema metadata from SQLite databases.
    - CatalogBuilder: Build and persist a searchable catalog of all Spider schemas.
    - DatabaseRetriever: Retrieve the most relevant database(s) for a NL question.
"""

from .schema_extractor import SchemaExtractor
from .catalog_builder import CatalogBuilder
from .retriever import DatabaseRetriever

__all__ = ["SchemaExtractor", "CatalogBuilder", "DatabaseRetriever"]
