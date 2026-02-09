"""
Similar row detection for cross-contamination warnings.

Detects rows with overlapping ID values that could cause
memory cross-contamination during multi-row validation.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def find_similar_rows(
    current_row: Dict[str, Any],
    all_rows: List[Dict[str, Any]],
    table_columns: List[str]
) -> List[Dict[str, Any]]:
    """
    Detect rows with overlapping ID values that could cause cross-contamination.

    Args:
        current_row: The row currently being validated
        all_rows: All rows in the table
        table_columns: Column names used as identifiers

    Returns:
        List of {row_id_display, similarity, matching_ids} for similar rows
    """
    if not table_columns or not all_rows:
        return []

    current_values = {
        col: str(current_row.get(col, '')).strip().lower()
        for col in table_columns
        if current_row.get(col, '')
    }

    if not current_values:
        return []

    similar = []
    for other_row in all_rows:
        if other_row is current_row:
            continue

        matching_ids = []
        for col, val in current_values.items():
            other_val = str(other_row.get(col, '')).strip().lower()
            if other_val and val == other_val:
                matching_ids.append(col)

        if matching_ids:
            # Calculate similarity as fraction of matching ID columns
            similarity = len(matching_ids) / len(current_values)

            # Build display string from ID columns
            other_display = ' | '.join(
                str(other_row.get(col, '')) for col in table_columns
                if other_row.get(col, '')
            )

            similar.append({
                'row_id_display': other_display,
                'similarity': similarity,
                'matching_ids': matching_ids
            })

    # Sort by similarity descending
    similar.sort(key=lambda x: x['similarity'], reverse=True)

    if similar:
        logger.debug(
            f"[SIMILAR_ROWS] Found {len(similar)} similar rows "
            f"(top match: {similar[0]['row_id_display']}, "
            f"similarity={similar[0]['similarity']:.2f})"
        )

    return similar
