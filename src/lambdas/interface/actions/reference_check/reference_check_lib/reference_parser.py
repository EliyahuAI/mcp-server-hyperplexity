"""
Reference Parser

Extracts reference list from text and resolves numbered citations to actual references.
"""

import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class ReferenceParser:
    """Parse and resolve references from text."""

    def __init__(self):
        pass

    def extract_reference_list(self, text: str) -> Dict[str, str]:
        """
        Extract reference list from end of text.

        Looks for patterns like:
        - [1] URL
        - [1] Author (Year). Title...
        - References:\n[1] Citation
        - Bibliography:\n[1] Citation

        Returns:
            Dict mapping ref_id to full citation
            Example: {"[1]": "https://example.com", "[2]": "Smith et al. (2024)..."}
        """
        references = {}

        # Look for References/Bibliography section
        ref_section_match = re.search(
            r'(?:^|\n)(References?|Bibliography|Citations?|Sources?)[\s:]*\n(.*)',
            text,
            re.IGNORECASE | re.DOTALL
        )

        if ref_section_match:
            ref_section = ref_section_match.group(2)
            logger.info(f"[REF PARSER] Found reference section: {len(ref_section)} chars")
        else:
            # No explicit section, try to find references in last 30% of text
            split_point = int(len(text) * 0.7)
            ref_section = text[split_point:]
            logger.info(f"[REF PARSER] No reference section found, searching last 30% of text")

        # Pattern for numbered references
        # Matches: [1] URL or [1] Author... or (1) URL, etc.
        patterns = [
            # [1] pattern
            r'^\[(\d+)\]\s*(.+?)(?=^\[|$)',
            # (1) pattern
            r'^\((\d+)\)\s*(.+?)(?=^\(|$)',
            # 1. pattern
            r'^(\d+)\.\s*(.+?)(?=^\d+\.|$)',
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, ref_section, re.MULTILINE | re.DOTALL)
            for match in matches:
                ref_num = match.group(1)
                ref_text = match.group(2).strip()

                # Clean up the reference text (remove extra newlines, collapse whitespace)
                ref_text = re.sub(r'\s+', ' ', ref_text)
                ref_text = ref_text.strip()

                # Store with bracket notation
                ref_id = f"[{ref_num}]"
                references[ref_id] = ref_text
                logger.info(f"[REF PARSER] Extracted {ref_id}: {ref_text[:100]}...")

        logger.info(f"[REF PARSER] Extracted {len(references)} references total")
        return references

    def resolve_citations(self, citation_text: str, reference_map: Dict[str, str]) -> str:
        """
        Resolve numbered citations to actual references.

        Args:
            citation_text: Text with citations like "[1][2][3]"
            reference_map: Dict mapping ref_id to full citation

        Returns:
            Resolved references with Excel newlines between them
            Example: "https://example.com\nhttps://another.com\nSmith et al. (2024)..."
        """
        if not citation_text or not reference_map:
            return citation_text

        # Find all citation numbers in the text
        # Matches: [1], [2], [3] or [1,2,3] or [1][2][3]
        citation_pattern = r'\[(\d+(?:,\s*\d+)*)\]|\[(\d+)\]'
        matches = re.findall(citation_pattern, citation_text)

        # Extract all unique numbers
        ref_nums = set()
        for match in matches:
            # match is a tuple: (comma_separated, single)
            if match[0]:  # Comma-separated: [1,2,3]
                nums = re.findall(r'\d+', match[0])
                ref_nums.update(nums)
            elif match[1]:  # Single: [1]
                ref_nums.add(match[1])

        # Resolve each number to its full citation
        resolved_refs = []
        for num in sorted(ref_nums, key=int):
            ref_id = f"[{num}]"
            if ref_id in reference_map:
                resolved_refs.append(reference_map[ref_id])
                logger.info(f"[REF PARSER] Resolved {ref_id} to citation")
            else:
                # Keep original if not found
                resolved_refs.append(ref_id)
                logger.warning(f"[REF PARSER] Could not resolve {ref_id}, keeping as-is")

        # Join with Excel newlines (\n for within-cell line breaks)
        return '\n'.join(resolved_refs) if resolved_refs else citation_text

    def parse_and_resolve(self, text: str, claims: List[Dict]) -> Tuple[List[Dict], Dict[str, str]]:
        """
        Extract reference list and resolve citations in claims.

        Args:
            text: Full submitted text
            claims: List of extracted claims with 'reference' field

        Returns:
            Tuple of (updated_claims, reference_map)
        """
        # Extract reference list from text
        reference_map = self.extract_reference_list(text)

        # Resolve citations in each claim
        for claim in claims:
            citation = claim.get('reference')
            if citation and reference_map:
                resolved = self.resolve_citations(citation, reference_map)
                claim['reference'] = resolved
                logger.info(
                    f"[REF PARSER] Claim {claim.get('claim_id')}: "
                    f"{citation} → {len(resolved)} chars resolved"
                )

        return claims, reference_map


def parse_and_resolve_references(text: str, claims: List[Dict]) -> Tuple[List[Dict], Dict[str, str]]:
    """
    Convenience function to parse and resolve references.

    Args:
        text: Full submitted text
        claims: List of extracted claims

    Returns:
        Tuple of (updated_claims, reference_map)
    """
    parser = ReferenceParser()
    return parser.parse_and_resolve(text, claims)
