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

    def detect_reference_format(self, text: str, reference_map: Dict[str, str]) -> Tuple[str, float]:
        """
        Detect reference format to determine processing path.

        Returns:
            Tuple of (path_type, confidence)
            path_type: "inline_links" | "needs_parsing" | "not_found"
            confidence: 0.0-1.0 quality score
        """
        # Check for numbered citations with inline URLs (AI output pattern)
        # Pattern: [1] followed by URL anywhere in the reference
        inline_pattern = r'\[(\d+)\]\s*(?:.*?)https?://[^\s<>]+'
        inline_matches = re.findall(inline_pattern, text, re.MULTILINE)

        if len(inline_matches) >= 3:
            logger.info(f"[REF PARSER] Path A: Inline links detected ({len(inline_matches)} refs with URLs)")
            return "inline_links", 1.0

        # Check for clean reference section with URLs/DOIs
        if len(reference_map) >= 3:
            has_urls = sum(1 for r in reference_map.values() if 'http' in r or 'doi:' in r or 'arxiv' in r.lower())
            if has_urls >= len(reference_map) * 0.5:  # At least 50% have URLs
                logger.info(f"[REF PARSER] Path B: Clean reference section ({len(reference_map)} refs, {has_urls} with URLs)")
                return "needs_parsing", 0.8

        # Check if there are numbered citations in text but no reference section
        citation_pattern = r'\[(\d+)\]'
        citations_in_text = set(re.findall(citation_pattern, text))

        if len(citations_in_text) >= 2 and len(reference_map) == 0:
            logger.info(f"[REF PARSER] Path C1: Numbered citations found ({len(citations_in_text)}) but no reference section")
            return "not_found", 0.3
        elif len(reference_map) == 0:
            logger.info(f"[REF PARSER] Path C2: No references or citations found (unreferenced text)")
            return "not_found", 0.0
        else:
            logger.info(f"[REF PARSER] Path B: Partial reference section ({len(reference_map)} refs)")
            return "needs_parsing", 0.5

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

    def build_enriched_text(self, text: str, reference_map: Dict[str, str], path_type: str) -> str:
        """
        Build enriched text with reference information for AI.

        Args:
            text: Original text
            reference_map: Parsed references
            path_type: Detection path (inline_links, needs_parsing, not_found)

        Returns:
            Enriched text with reference instructions
        """
        if path_type == "inline_links":
            # Path A: References already inline with URLs
            notice = f"""

--- REFERENCES DETECTED ({len(reference_map)} found) ---
References are already inline with URLs. Use these exactly as provided in the text.
Do NOT include reference_list in your output.
"""
            return text + notice

        elif path_type == "needs_parsing":
            # Path B: Parsed reference section
            ref_list = "\n".join([f"{ref_id} {citation}" for ref_id, citation in sorted(reference_map.items(), key=lambda x: int(re.search(r'\d+', x[0]).group()))])
            notice = f"""

--- PARSED REFERENCES ({len(reference_map)} found) ---
{ref_list}

Use these references when extracting claims. Only include reference_list in output if these are wrong or unusable.
If providing reference_list, it must be a COMPLETE replacement (not partial corrections).
"""
            return text + notice

        else:
            # Path C: No references found
            notice = """

--- NOTICE: No reference list detected ---
If numbered citations like [1], [2] exist in the text, you MUST provide reference_list with all numbered references.
If no numbered citations exist, this text has unreferenced claims - do not include reference_list.
"""
            return text + notice

    def parse_and_resolve(self, text: str, claims: List[Dict], ai_reference_list: List[Dict] = None) -> Tuple[List[Dict], Dict[str, str]]:
        """
        Extract reference list and resolve citations in claims.

        Args:
            text: Full submitted text
            claims: List of extracted claims with 'reference' field
            ai_reference_list: Optional reference list from AI (complete override)

        Returns:
            Tuple of (updated_claims, final_reference_map)
        """
        # Extract reference list from text
        parsed_reference_map = self.extract_reference_list(text)

        # Determine final reference map
        if ai_reference_list:
            # AI provided complete override
            final_reference_map = {r['ref_id']: r['full_citation'] for r in ai_reference_list}
            logger.info(f"[REF PARSER] Using AI-provided reference list ({len(final_reference_map)} refs)")
        else:
            # Use parsed references
            final_reference_map = parsed_reference_map
            logger.info(f"[REF PARSER] Using Python-parsed references ({len(final_reference_map)} refs)")

        # Resolve citations in each claim
        for claim in claims:
            citation = claim.get('reference')
            if citation and final_reference_map:
                resolved = self.resolve_citations(citation, final_reference_map)
                claim['reference'] = resolved
                logger.info(
                    f"[REF PARSER] Claim {claim.get('claim_id')}: "
                    f"{citation} → {len(resolved)} chars resolved"
                )

        return claims, final_reference_map


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
