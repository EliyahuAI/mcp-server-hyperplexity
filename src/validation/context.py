"""
Validation context models for row-level memory isolation.

Prevents cross-contamination in multi-row validation by tagging
memory entries with row identity information.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class RowIdentity:
    """Identifies a specific row being validated."""
    id_columns: List[str]
    id_values: List[str]
    row_key: str
    row_id_display: str


@dataclass
class CloneFeatures:
    """Search features extracted for a clone query."""
    search_terms: List[str] = field(default_factory=list)
    keywords: Dict[str, List[str]] = field(default_factory=dict)
    breadth: str = "narrow"
    depth: str = "shallow"
    strategy: str = "unknown"


@dataclass
class RowWarnings:
    """Warnings about potential cross-contamination."""
    similar_rows: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class EnhancedValidationContext:
    """
    Full validation context for a single row.

    Carries row identity through the memory pipeline so storage
    tags results with row identity and recall filters by it.
    """
    row_identity: Optional[RowIdentity] = None
    clone_features: Optional[CloneFeatures] = None
    row_warnings: Optional[RowWarnings] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for storage in memory entries."""
        result = {}
        if self.row_identity:
            result['row_identity'] = {
                'id_columns': self.row_identity.id_columns,
                'id_values': self.row_identity.id_values,
                'row_key': self.row_identity.row_key,
                'row_id_display': self.row_identity.row_id_display,
            }
        if self.clone_features:
            result['clone_features'] = {
                'search_terms': self.clone_features.search_terms,
                'keywords': self.clone_features.keywords,
                'breadth': self.clone_features.breadth,
                'depth': self.clone_features.depth,
                'strategy': self.clone_features.strategy,
            }
        if self.row_warnings:
            result['row_warnings'] = {
                'similar_rows': self.row_warnings.similar_rows,
                'warnings': self.row_warnings.warnings,
            }
        if self.metadata:
            result['metadata'] = self.metadata
        return result
