#!/usr/bin/env python3
"""
Bridge between the_clone output and validator Excel comment format.

Converts the_clone's p-scores and citations into the validator's
Excel comment format for iterative validation.
"""

from typing import List, Dict, Optional
from shared.confidence_mapper import get_highest_confidence_from_snippets


def format_clone_output_as_comment(
    value: str,
    snippets: List[Dict],
    citations: List[Dict],
    key_citation_index: int = 0
) -> str:
    """
    Format the_clone output into validator Excel comment format.

    Args:
        value: The cell value
        snippets: Snippets from the_clone that support this value
        citations: Citation objects from the_clone
        key_citation_index: Which citation is the "key" one (default: first)

    Returns:
        Formatted comment string ready for Excel

    Example Output:
        ```
        Original Value: ABC Corp (MEDIUM Confidence)

        Key Citation: Company website (https://example.com)

        Sources:
        [1] Forbes (https://forbes.com): "ABC Corp is a leading..."
        [2] Bloomberg (https://bloomberg.com): "The company operates..."
        ```
    """
    # Map confidence from snippets
    confidence = get_highest_confidence_from_snippets(snippets)

    comment_parts = []

    # Original Value line with confidence
    comment_parts.append(f"Original Value: {value} ({confidence} Confidence)")

    # Key Citation
    if citations and len(citations) > key_citation_index:
        key_cite = citations[key_citation_index]
        key_url = key_cite.get('url', '')
        key_title = key_cite.get('title', 'Source')
        comment_parts.append(f"Key Citation: {key_title} ({key_url})")

    # Sources section
    if citations:
        sources_lines = ["Sources:"]
        for i, cite in enumerate(citations, 1):
            title = cite.get('title', 'Untitled')
            url = cite.get('url', '')
            snippet = cite.get('snippet', '')

            # Truncate long snippets to fit in Excel comment
            if len(snippet) > 100:
                snippet = snippet[:97] + "..."

            cite_line = f"[{i}] {title}"
            if url:
                cite_line += f" ({url})"
            if snippet:
                # Escape quotes in snippet
                snippet_clean = snippet.replace('"', "'")
                cite_line += f": \"{snippet_clean}\""

            sources_lines.append(cite_line)

        comment_parts.append("\n".join(sources_lines))

    return "\n\n".join(comment_parts)


def extract_confidence_from_clone_answer(
    clone_result: Dict,
    field_name: str
) -> str:
    """
    Extract confidence level for a specific field from the_clone result.

    Looks at all snippets that were used for the answer and determines
    the confidence level based on p-scores.

    Args:
        clone_result: Full result from the_clone.query()
        field_name: Name of the field to get confidence for

    Returns:
        "HIGH", "MEDIUM", or "LOW"
    """
    snippets = clone_result.get('all_snippets', [])
    return get_highest_confidence_from_snippets(snippets)


def create_field_comment_from_clone(
    field_value: str,
    field_name: str,
    clone_result: Dict,
    max_citations: int = 5
) -> str:
    """
    Create an Excel comment for a specific field using the_clone output.

    Useful when the_clone was used to generate/validate a single field value.

    Args:
        field_value: The value to document
        field_name: Name of the field
        clone_result: Full result from the_clone.query()
        max_citations: Maximum citations to include (default: 5)

    Returns:
        Formatted comment string
    """
    citations = clone_result.get('citations', [])[:max_citations]
    snippets = clone_result.get('all_snippets', [])

    return format_clone_output_as_comment(
        value=field_value,
        snippets=snippets,
        citations=citations
    )
