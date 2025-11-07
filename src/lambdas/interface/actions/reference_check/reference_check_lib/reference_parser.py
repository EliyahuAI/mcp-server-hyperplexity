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

    def detect_content_type(self, text: str) -> str:
        """Detect if content is AI-generated response or academic paper."""
        ai_indicators = 0
        academic_indicators = 0

        # AI response indicators
        if re.search(r"I'll|I've|Let me|Here's what|Based on|According to my", text, re.IGNORECASE):
            ai_indicators += 2
        if re.search(r"\*\*.*?\*\*", text):  # Bold markdown
            ai_indicators += 1
        if re.search(r"^###?\s+", text, re.MULTILINE):  # Markdown headings
            ai_indicators += 1

        # Academic paper indicators
        if re.search(r"Abstract|Introduction|Methods|Results|Discussion|Conclusion", text):
            academic_indicators += 2
        if re.search(r"et al\.|doi:|PMID:", text):
            academic_indicators += 2

        if ai_indicators > academic_indicators + 1:
            return "ai_response"
        elif academic_indicators > ai_indicators + 1:
            return "academic_paper"
        return "mixed"

    def detect_reference_format(self, text: str, reference_map: Dict[str, str]) -> Tuple[str, float]:
        """
        Detect reference format to determine processing path.

        Returns:
            Tuple of (path_type, confidence)
            path_type: "inline_links" | "needs_parsing" | "not_found"
            confidence: 0.0-1.0 quality score
        """
        content_type = self.detect_content_type(text)
        logger.info(f"[REF PARSER] Content type: {content_type}")

        # AI-specific patterns
        # Perplexity: [1](https://url)
        perplexity_pattern = r'\[(\d+)\]\(https?://[^\)]+\)'
        perplexity_matches = re.findall(perplexity_pattern, text)

        # ChatGPT/Claude: [1] at end with URL below or [Source][1]
        inline_url_pattern = r'\[(\d+)\]\s*https?://[^\s<>\)]+'
        inline_matches = re.findall(inline_url_pattern, text)

        # End reference block: [1]: https://
        end_ref_pattern = r'\[(\d+)\][:]\s*https?://[^\s<>]+'
        end_ref_matches = re.findall(end_ref_pattern, text)

        total_inline = len(perplexity_matches) + len(inline_matches) + len(end_ref_matches)

        if total_inline >= 3:
            logger.info(f"[REF PARSER] Path A: Inline links ({total_inline} refs, type: {content_type})")
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
        Extract reference list from text using multiple aggressive strategies.

        Implements comprehensive reference detection:
        1. Multiple section header detection (References, Bibliography, Citations, etc.)
        2. Multiple reference format patterns ([1], (1), 1., ^1, superscript)
        3. Searches last 20-40% of text if no headers found
        4. Handles multi-line references with embedded URLs
        5. Fuzzy matching for non-sequential references
        6. Extracts DOI, arXiv, and wrapped URLs

        Returns:
            Dict mapping ref_id to full citation
            Example: {"[1]": "https://example.com", "[2]": "Smith et al. (2024)..."}
        """
        all_references = {}

        # Strategy 1: Look for explicit reference sections with headers
        refs_from_sections = self._extract_from_sections(text)
        logger.info(f"[REF PARSER] Strategy 1 (sections): {len(refs_from_sections)} refs found")
        all_references.update(refs_from_sections)

        # Strategy 2: Look for markdown/plain text headings
        refs_from_headings = self._extract_from_headings(text)
        logger.info(f"[REF PARSER] Strategy 2 (headings): {len(refs_from_headings)} refs found")
        all_references.update(refs_from_headings)

        # Strategy 3: Search last 20-40% for reference patterns (no header required)
        refs_from_tail = self._extract_from_tail(text)
        logger.info(f"[REF PARSER] Strategy 3 (tail search): {len(refs_from_tail)} refs found")
        all_references.update(refs_from_tail)

        # Strategy 4: Look for inline reference blocks (references scattered in text)
        refs_from_inline = self._extract_inline_blocks(text)
        logger.info(f"[REF PARSER] Strategy 4 (inline blocks): {len(refs_from_inline)} refs found")
        all_references.update(refs_from_inline)

        # Strategy 5: Extract citations with immediate URLs
        refs_from_urls = self._extract_citation_url_pairs(text)
        logger.info(f"[REF PARSER] Strategy 5 (citation-URL pairs): {len(refs_from_urls)} refs found")
        all_references.update(refs_from_urls)

        # Post-process: enhance references with URL extraction and cleaning
        all_references = self._enhance_references(all_references)

        logger.info(f"[REF PARSER] TOTAL: Extracted {len(all_references)} unique references")
        return all_references

    def _extract_author_year_citations(self, section: str) -> Dict[str, str]:
        """
        Extract author-year format citations (academic papers without numbers).
        Assigns sequential numbers [1], [2], [3]...

        Looks for patterns like:
        - Author, A. (Year). Title...
        - Author et al. Title. Journal...
        - Multiple authors. (Year). Title...
        """
        references = {}

        # Strategy 1: Try simple blank-line splitting first (Nature HTML format)
        # Each citation is on its own line or paragraph
        citation_blocks = re.split(r'\n\s*\n', section)
        simple_refs = {}
        ref_num = 1

        for block in citation_blocks:
            block = block.strip()
            # Skip if too short or starts with "References"
            if len(block) < 30 or block.lower().startswith('reference'):
                continue

            # Check if looks like a citation
            has_year = bool(re.search(r'\(\d{4}[a-z]?\)|\b\d{4}[a-z]?\b', block))
            starts_with_author = bool(re.match(r'^[A-Z][a-z]+[,\s]|^[A-Z][a-z]+\s+et al\.', block))
            has_citation_markers = bool(re.search(r'pp\.|Vol\.|doi:|https?://|arXiv', block, re.IGNORECASE))

            # Accept if has author start AND (year OR citation markers)
            if block[0].isupper() and starts_with_author and (has_year or has_citation_markers):
                ref_id = f"[{ref_num}]"
                simple_refs[ref_id] = block
                logger.info(f"[REF PARSER] Simple author-year {ref_id}: {block[:80]}...")
                ref_num += 1

        # If simple splitting worked well (got 3+ refs), use it
        if len(simple_refs) >= 3:
            logger.info(f"[REF PARSER] Author-year simple: Extracted {len(simple_refs)} single-line citations")
            return simple_refs

        # Strategy 2: More complex line-by-line parsing for multi-line citations (PDF format)
        logger.info(f"[REF PARSER] Author-year complex: Trying multi-line citation parsing")

        # Split into lines and group into citations
        # Academic refs start with Author name and may span multiple lines
        lines = section.split('\n')

        ref_num = 1
        current_citation = []

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Check if previous line ended mid-sentence (no period, continuation)
            prev_line_incomplete = (
                current_citation and
                len(current_citation) > 0 and
                current_citation[-1] and
                not current_citation[-1].rstrip().endswith(('.', ')', '!', '?', '"'))
            )

            # Check if this starts a new citation
            # Must start with Author name pattern AND previous citation is complete
            starts_citation = (
                len(line_stripped) > 15 and
                line_stripped[0].isupper() and
                not prev_line_incomplete and  # Previous line must be complete
                (re.match(r'^[A-Z][a-z]+[a-z\s,]+[A-Z]', line_stripped) or  # Author Name, Initial
                 re.match(r'^[A-Z][a-z]+\s+et al\.', line_stripped) or       # Author et al.
                 re.match(r'^[A-Z][a-z]+,\s+[A-Z]\.', line_stripped))  # Author, A.
            )

            if starts_citation:
                # Save previous citation if exists and it looks complete
                if current_citation:
                    citation_text = ' '.join(current_citation)
                    if len(citation_text) > 50:  # Minimum length check
                        ref_id = f"[{ref_num}]"
                        references[ref_id] = citation_text
                        logger.info(f"[REF PARSER] Author-year {ref_id}: {citation_text[:80]}...")
                        ref_num += 1

                # Start new citation
                current_citation = [line_stripped]
            elif line_stripped:
                # Continue current citation or start first one
                if current_citation:
                    current_citation.append(line_stripped)
                elif len(line_stripped) > 15:  # Start first citation if substantial
                    current_citation = [line_stripped]
            elif not line_stripped and current_citation:
                # Empty line - might be end of citation, but only save if we've accumulated enough
                if len(' '.join(current_citation)) > 100:
                    citation_text = ' '.join(current_citation)
                    ref_id = f"[{ref_num}]"
                    references[ref_id] = citation_text
                    logger.info(f"[REF PARSER] Author-year {ref_id}: {citation_text[:80]}...")
                    ref_num += 1
                    current_citation = []

        # Don't forget last citation
        if current_citation:
            citation_text = ' '.join(current_citation)
            if len(citation_text) > 50:
                ref_id = f"[{ref_num}]"
                references[ref_id] = citation_text
                logger.info(f"[REF PARSER] Author-year {ref_id}: {citation_text[:80]}...")

        return references

    def _extract_from_sections(self, text: str) -> Dict[str, str]:
        """Extract references from explicit section headers."""
        references = {}

        # Look for References/Bibliography/Citations/Sources/Works Cited sections
        # Enhanced patterns - grab everything until next major section or end
        section_patterns = [
            # Greedy - take everything after References until obvious section break
            r'(?:^|\n)(REFERENCES?)[\s:]*\n(.*?)(?=\n\n(?:Acknowledgements?|Funding|Author|Appendix|Supplementary|Data Availability|Code Availability|Ethics|Competing|Download)|\Z)',
            r'(?:^|\n)(References?)[\s:]*\n(.*?)(?=\n\n(?:Acknowledgements?|Funding|Author|Appendix|Supplementary|Data Availability|Code Availability|Ethics|Competing|Download)|\Z)',
            r'(?:^|\n)(BIBLIOGRAPHY)[\s:]*\n(.*?)(?=\n\n(?:Acknowledgements?|Funding|Author|Appendix)|\Z)',
            r'(?:^|\n)(Bibliography)[\s:]*\n(.*?)(?=\n\n(?:Acknowledgements?|Funding|Author|Appendix)|\Z)',
            r'(?:^|\n)(Citations?)[\s:]*\n(.*?)(?=\n\n(?:Acknowledgements?|Funding|Author)|\Z)',
            r'(?:^|\n)(Sources?)[\s:]*\n(.*?)(?=\n\n(?:Acknowledgements?|Funding)|\Z)',
            r'(?:^|\n)(Works Cited)[\s:]+\n(.*?)(?=\n\n[A-Z][a-z]+:|\n\n#{1,6}\s|\Z)',
            r'(?:^|\n)(Further Reading)[\s:]+\n(.*?)(?=\n\n[A-Z][a-z]+:|\n\n#{1,6}\s|\Z)',
            r'(?:^|\n)(Literature Cited)[\s:]+\n(.*?)(?=\n\n[A-Z][a-z]+:|\n\n#{1,6}\s|\Z)',
            # No colon variants
            r'(?:^|\n)(References?)\s*\n(.*?)(?=\n\n[A-Z][a-z]+:|\n\n#{1,6}\s|\Z)',
            r'(?:^|\n)(Bibliography)\s*\n(.*?)(?=\n\n[A-Z][a-z]+:|\n\n#{1,6}\s|\Z)',
            # Bold markdown variants
            r'(?:^|\n)\*\*(References?)\*\*[\s:]*\n(.*?)(?=\n\n[A-Z][a-z]+:|\n\n#{1,6}\s|\Z)',
            r'(?:^|\n)\*\*(Bibliography)\*\*[\s:]*\n(.*?)(?=\n\n[A-Z][a-z]+:|\n\n#{1,6}\s|\Z)',
            # All caps variants
            r'(?:^|\n)(REFERENCES?)[\s:]*\n(.*?)(?=\n\n[A-Z]+:|\n\n#{1,6}\s|\Z)',
            r'(?:^|\n)(BIBLIOGRAPHY)[\s:]*\n(.*?)(?=\n\n[A-Z]+:|\n\n#{1,6}\s|\Z)',
        ]

        for pattern in section_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                section_name = match.group(1)
                ref_section = match.group(2)
                logger.info(f"[REF PARSER] Found '{section_name}' section: {len(ref_section)} chars")
                refs = self._parse_reference_section(ref_section)

                # If no numbered refs found, try author-year format
                if len(refs) == 0:
                    logger.info(f"[REF PARSER] No numbered refs, trying author-year format")
                    refs = self._extract_author_year_citations(ref_section)

                references.update(refs)
                if refs:  # If we found refs, don't try other patterns
                    break

        return references

    def _extract_from_headings(self, text: str) -> Dict[str, str]:
        """Extract references from markdown headings or plain text headings."""
        references = {}

        # Markdown heading patterns: # References, ## References, etc.
        # Enhanced to handle more variations
        heading_patterns = [
            # Standard markdown headings (# to ######)
            r'(?:^|\n)(#{1,6})\s*(References?|Bibliography|Citations?|Sources?|Works Cited|Further Reading|Literature Cited)[\s:]*\n(.*?)(?=\n#{1,6}\s|\Z)',
            # Underlined headings (===== or -----)
            r'(?:^|\n)(References?|Bibliography|Citations?|Sources?|Works Cited)[\s:]*\n[=\-]{3,}\n(.*?)(?=\n[A-Z][a-z]+\n[=\-]{3,}|\Z)',
            # HTML heading tags
            r'<h[1-6]>\s*(References?|Bibliography|Citations?|Sources?|Works Cited)[\s:]*</h[1-6]>\s*(.*?)(?=<h[1-6]>|\Z)',
        ]

        for pattern in heading_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                # Pattern might have different group counts
                if len(match.groups()) == 3:
                    heading = match.group(2)
                    ref_section = match.group(3)
                else:
                    heading = match.group(1)
                    ref_section = match.group(2)
                logger.info(f"[REF PARSER] Found heading '{heading}': {len(ref_section)} chars")
                refs = self._parse_reference_section(ref_section)
                references.update(refs)
                if refs:
                    break

        return references

    def _extract_from_tail(self, text: str) -> Dict[str, str]:
        """Search last 20-40% of text for reference patterns without requiring headers."""
        references = {}

        # Try 40% first, then 30%, then 20%, then even 50% for edge cases
        for percentage in [0.5, 0.6, 0.7, 0.8]:
            split_point = int(len(text) * percentage)
            tail_section = text[split_point:]

            refs = self._parse_reference_section(tail_section)
            if len(refs) >= 2:  # Found meaningful references
                logger.info(f"[REF PARSER] Found {len(refs)} refs in last {int((1-percentage)*100)}% of text")
                references.update(refs)
                break
            elif len(refs) == 1 and percentage == 0.8:
                # Accept single reference in last 20% if nothing else found
                logger.info(f"[REF PARSER] Found 1 ref in last 20% of text (accepting)")
                references.update(refs)

        return references

    def _extract_inline_blocks(self, text: str) -> Dict[str, str]:
        """Extract reference blocks that appear inline in text (not in dedicated section)."""
        references = {}

        # Look for clusters of numbered citations (3+ consecutive numbered items)
        # This catches reference blocks without headers
        lines = text.split('\n')

        i = 0
        while i < len(lines):
            # Check if this line starts a reference block
            if self._is_reference_start(lines[i]):
                block_lines = [lines[i]]
                j = i + 1

                # Collect consecutive reference-like lines
                while j < len(lines) and (self._is_reference_start(lines[j]) or self._is_reference_continuation(lines[j])):
                    block_lines.append(lines[j])
                    j += 1

                # If we found a cluster of 3+ references, parse them
                ref_count = sum(1 for line in block_lines if self._is_reference_start(line))
                if ref_count >= 3:
                    block_text = '\n'.join(block_lines)
                    refs = self._parse_reference_section(block_text)
                    references.update(refs)
                    logger.info(f"[REF PARSER] Found inline block with {len(refs)} refs at line {i}")
                    i = j
                    continue

            i += 1

        return references

    def _extract_citation_url_pairs(self, text: str) -> Dict[str, str]:
        """Extract citations that have immediate URL following them."""
        references = {}

        # Multiple patterns to handle various formats
        patterns = [
            # Perplexity format: [1](https://url) - markdown link
            (r'\[(\d+)\]\((https?://[^\)]+)\)', lambda m: (m.group(1), m.group(2))),
            # ChatGPT end format: [1]: https://url with optional title
            (r'\[(\d+)\]:\s*(https?://[^\s<>]+)(?:\s+"([^"]+)")?', lambda m: (m.group(1), f"{m.group(2)} {m.group(3) if m.group(3) else ''}".strip())),
            # [1] followed by URL (possibly with text in between, up to 300 chars)
            (r'\[(\d+)\]\s*(?:.{0,300}?)(https?://[^\s<>)\]]+)', lambda m: (m.group(1), m.group(2))),
            # [1] followed by DOI
            (r'\[(\d+)\]\s*(?:.{0,200}?)(doi:[\d.]+/[^\s]+)', lambda m: (m.group(1), m.group(2))),
            # [1] followed by arXiv
            (r'\[(\d+)\]\s*(?:.{0,200}?)(arxiv:[\d.]+)', lambda m: (m.group(1), m.group(2))),
            # (1) format with URL
            (r'\((\d+)\)\s*(?:.{0,300}?)(https?://[^\s<>)\]]+)', lambda m: (m.group(1), m.group(2))),
            # Numbered format with URL: 1. URL
            (r'(?:^|\n)(\d+)\.\s+(?:.{0,300}?)(https?://[^\s<>)\]]+)', lambda m: (m.group(1), m.group(2))),
        ]

        for pattern, extractor in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                ref_num, citation = extractor(match)
                ref_id = f"[{ref_num}]"

                # For Perplexity format [1](url), the citation is just the URL
                # For others, try to get more context
                if '(' not in pattern or ')' not in pattern:
                    # Not Perplexity format, try to get more context
                    start_pos = max(0, match.start() - 300)
                    end_pos = min(len(text), match.end() + 150)
                    context = text[start_pos:end_pos]
                    full_citation = self._extract_full_citation_from_context(ref_num, context)
                else:
                    # Perplexity format - just use the URL
                    full_citation = citation

                if ref_id not in references:  # Don't override better extractions
                    references[ref_id] = full_citation
                    logger.info(f"[REF PARSER] URL pair: {ref_id} → {full_citation[:80]}...")

        return references

    def _parse_reference_section(self, section: str) -> Dict[str, str]:
        """
        Parse a text section for numbered references using multiple format patterns.

        Handles:
        - [1] citation
        - (1) citation
        - 1. citation
        - ^1 citation (superscript marker)
        - ¹ citation (Unicode superscript)
        - Multi-line references with URLs on next line
        """
        references = {}

        # Multiple format patterns with different strategies - more aggressive
        patterns = [
            # [1] pattern - multi-line aware, more flexible
            (r'\[(\d+)\]\s*(.+?)(?=\n\s*\[\d+\]|\n\n|\Z)', re.MULTILINE | re.DOTALL),
            # (1) pattern - multi-line aware, more flexible
            (r'\((\d+)\)\s*(.+?)(?=\n\s*\(\d+\)|\n\n|\Z)', re.MULTILINE | re.DOTALL),
            # 1. pattern - multi-line aware (accepts both uppercase and lowercase starts)
            (r'(?:^|\n)(\d+)\.\s+([A-Za-z][^\n]+(?:\n(?!\d+\.)[^\n]+)*)(?=\n\s*\d+\.|\n\n|\Z)', re.MULTILINE | re.DOTALL),
            # ^1 pattern (superscript marker)
            (r'\^(\d+)\s*(.+?)(?=\n\s*\^\d+|\n\n|\Z)', re.MULTILINE | re.DOTALL),
            # Unicode superscript (¹, ², ³, etc.)
            (r'([¹²³⁴⁵⁶⁷⁸⁹⁰]+)\s*(.+?)(?=\n\s*[¹²³⁴⁵⁶⁷⁸⁹⁰]|\n\n|\Z)', re.MULTILINE | re.DOTALL),
            # Fallback: any line starting with digit + dot/bracket
            (r'(?:^|\n)(\d+)[\.\)]\s*(.+?)(?=\n\d+[\.\)]|\n\n|\Z)', re.MULTILINE | re.DOTALL),
        ]

        for pattern, flags in patterns:
            matches = re.finditer(pattern, section, flags)
            for match in matches:
                ref_num_raw = match.group(1)
                ref_text = match.group(2).strip() if len(match.groups()) >= 2 else ""

                # Convert Unicode superscript to regular numbers
                ref_num = self._superscript_to_number(ref_num_raw)

                # More lenient minimum length (was 10, now 5) to catch short citations
                if not ref_text or len(ref_text) < 5:
                    continue

                # Clean up the reference text
                ref_text = self._clean_reference_text(ref_text)

                # Store with bracket notation
                ref_id = f"[{ref_num}]"

                # Don't override if we already have this reference (first match wins)
                if ref_id not in references:
                    references[ref_id] = ref_text
                    logger.info(f"[REF PARSER] Extracted {ref_id}: {ref_text[:80]}...")

        return references

    def _is_reference_start(self, line: str) -> bool:
        """Check if a line starts a numbered reference."""
        line = line.strip()
        # Check for common reference start patterns
        patterns = [
            r'^\[\d+\]',  # [1]
            r'^\(\d+\)',  # (1)
            r'^\d+\.\s+[A-Z]',  # 1. Author (must start with capital)
            r'^\^\d+',  # ^1
            r'^[¹²³⁴⁵⁶⁷⁸⁹]',  # Unicode superscript
        ]
        return any(re.match(pattern, line) for pattern in patterns)

    def _is_reference_continuation(self, line: str) -> bool:
        """Check if a line is a continuation of a reference (wrapped line)."""
        line = line.strip()
        if not line:
            return False
        # Continuation lines often start with whitespace or lowercase, or contain URLs
        return (line[0].islower() or
                line.startswith('http') or
                'doi:' in line.lower() or
                'arxiv' in line.lower() or
                len(line) > 40)  # Long lines likely part of citation

    def _extract_full_citation_from_context(self, ref_num: str, context: str) -> str:
        """Extract full citation text around a reference number from context."""
        # Find the reference marker in context
        markers = [f'[{ref_num}]', f'({ref_num})', f'{ref_num}.', f'^{ref_num}']

        for marker in markers:
            if marker in context:
                # Extract from marker to next marker or end
                start = context.find(marker)

                # Look for next reference marker
                next_markers = [r'\[\d+\]', r'\(\d+\)', r'\d+\.', r'\^\d+']
                next_match = None
                for pattern in next_markers:
                    match = re.search(pattern, context[start + len(marker):])
                    if match:
                        if next_match is None or match.start() < next_match.start():
                            next_match = match

                if next_match:
                    end = start + len(marker) + next_match.start()
                else:
                    end = len(context)

                citation = context[start:end]
                return self._clean_reference_text(citation)

        return self._clean_reference_text(context)

    def _clean_reference_text(self, text: str) -> str:
        """Clean and normalize reference text."""
        # Remove excessive whitespace but preserve structure
        text = re.sub(r'[ \t]+', ' ', text)  # Collapse spaces/tabs
        text = re.sub(r'\n\s*\n', '\n', text)  # Remove empty lines
        text = re.sub(r'\n\s+', '\n', text)  # Remove leading whitespace on new lines

        # Handle wrapped URLs (URLs split across lines)
        text = re.sub(r'(https?://[^\s]*)\n([^\s]+)', r'\1\2', text)

        # Normalize Unicode characters
        text = text.replace('\u2019', "'")  # Smart apostrophe
        text = text.replace('\u201c', '"').replace('\u201d', '"')  # Smart quotes
        text = text.replace('\u2013', '-').replace('\u2014', '-')  # En/em dash

        # Final cleanup
        text = text.strip()

        return text

    def _superscript_to_number(self, text: str) -> str:
        """Convert Unicode superscript numbers to regular numbers."""
        superscript_map = {
            '¹': '1', '²': '2', '³': '3', '⁴': '4', '⁵': '5',
            '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9', '⁰': '0'
        }

        result = text
        for sup, reg in superscript_map.items():
            result = result.replace(sup, reg)

        return result

    def _enhance_references(self, references: Dict[str, str]) -> Dict[str, str]:
        """
        Post-process references to enhance URL extraction and handle special cases.

        - Extract DOI links
        - Extract arXiv links
        - Handle wrapped URLs
        - Ensure URLs are complete
        """
        enhanced = {}

        for ref_id, citation in references.items():
            # Extract and normalize URLs
            citation = self._normalize_urls(citation)

            # Extract DOI if present
            citation = self._normalize_doi(citation)

            # Extract arXiv if present
            citation = self._normalize_arxiv(citation)

            enhanced[ref_id] = citation

        return enhanced

    def _normalize_urls(self, text: str) -> str:
        """Normalize and complete URLs in text."""
        # Find all URLs
        url_pattern = r'https?://[^\s<>)"\']+'
        urls = re.findall(url_pattern, text)

        for url in urls:
            # Remove trailing punctuation that's not part of URL
            cleaned_url = re.sub(r'[.,;:!?]+$', '', url)
            if cleaned_url != url:
                text = text.replace(url, cleaned_url)

        return text

    def _normalize_doi(self, text: str) -> str:
        """Normalize DOI links to standard format."""
        # Pattern: doi:10.xxxx/yyyy or doi.org/10.xxxx/yyyy
        doi_patterns = [
            r'doi:\s*(10\.\d+/[^\s]+)',
            r'doi\.org/(10\.\d+/[^\s]+)',
        ]

        for pattern in doi_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                doi = match.group(1)
                # Ensure it's in URL format
                if 'https://doi.org/' not in text:
                    text = text.replace(match.group(0), f'https://doi.org/{doi}')

        return text

    def _normalize_arxiv(self, text: str) -> str:
        """Normalize arXiv links to standard format."""
        # Pattern: arxiv:2401.12345 or arxiv.org/abs/2401.12345
        arxiv_patterns = [
            r'arxiv:\s*([\d.]+)',
            r'arxiv\.org/abs/([\d.]+)',
        ]

        for pattern in arxiv_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                arxiv_id = match.group(1)
                # Ensure it's in URL format
                if 'https://arxiv.org/abs/' not in text:
                    text = text.replace(match.group(0), f'https://arxiv.org/abs/{arxiv_id}')

        return text

    def resolve_citations(self, citation_text: str, reference_map: Dict[str, str], format_as_hyperlink: bool = False) -> str:
        """
        Resolve numbered citations to actual references with Excel hyperlinks.

        Args:
            citation_text: Text with citations like "[1][2][3]"
            reference_map: Dict mapping ref_id to full citation
            format_as_hyperlink: If True, format URLs as Excel HYPERLINK formulas

        Returns:
            Resolved references with Excel newlines between them
            Example: "[1] =HYPERLINK(\"https://...\", \"https://...\")\n[2] Smith et al. (2024)..."
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
                citation = reference_map[ref_id]

                # Clean up URL: remove https:// prefix for cleaner display
                if re.match(r'https?://', citation):
                    clean_citation = re.sub(r'^https?://', '', citation)
                else:
                    clean_citation = citation

                # Format as "[1] domain.com/path" or "[1] citation text"
                formatted = f"{ref_id} {clean_citation}"
                resolved_refs.append(formatted)
                logger.info(f"[REF PARSER] Resolved {ref_id}")
            else:
                # Keep original if not found
                resolved_refs.append(ref_id)
                logger.warning(f"[REF PARSER] Could not resolve {ref_id}, keeping as-is")

        # Join with comma-space (works in preview and Excel without special formatting)
        return ', '.join(resolved_refs) if resolved_refs else citation_text

    def guess_source_type(self, text: str, reference_map: Dict[str, str], content_type: str, path_type: str) -> str:
        """
        Guess the source of the text based on format clues.

        Returns:
            Source type: "Perplexity", "ChatGPT", "Claude", "Grok", "Academic Paper", "Unknown"
        """
        # Check for AI assistant signatures
        if "perplexity" in text.lower() or re.search(r'\[\d+\]\(https?://[^\)]+\)', text):
            return "Perplexity"
        elif "chatgpt" in text.lower() or re.search(r'\[\d+\]:\s*https?://', text):
            return "ChatGPT"
        elif "claude" in text.lower() or "anthropic" in text.lower():
            return "Claude"
        elif "grok" in text.lower() or "x.ai" in text.lower():
            return "Grok"

        # Check for academic paper indicators
        if content_type == "academic_paper":
            # Check citation style
            has_author_year = any(re.search(r'et al\.|[A-Z][a-z]+,\s+[A-Z]\.', ref) for ref in reference_map.values())
            if has_author_year:
                return "Academic Paper (author-year)"
            else:
                return "Academic Paper"

        # Check for AI response with inline citations
        if path_type == "inline_links":
            return "AI Assistant Output"

        return "Unknown"

    def build_enriched_text(self, text: str, reference_map: Dict[str, str], path_type: str, source_guess: str = None) -> str:
        """
        Build enriched text with reference information for AI.

        Args:
            text: Original text
            reference_map: Parsed references
            path_type: Detection path (inline_links, needs_parsing, not_found)
            source_guess: Guessed source type (optional)

        Returns:
            Enriched text with reference instructions
        """
        source_info = f" (Detected source: {source_guess})" if source_guess else ""

        if path_type == "inline_links":
            # Path A: References already inline with URLs
            notice = f"""

--- REFERENCES DETECTED ({len(reference_map)} found){source_info} ---
References are already inline with URLs. Use these exactly as provided in the text.
Do NOT include reference_list in your output.
"""
            return text + notice

        elif path_type == "needs_parsing":
            # Path B: Parsed reference section
            ref_list = "\n".join([f"{ref_id} {citation}" for ref_id, citation in sorted(reference_map.items(), key=lambda x: int(re.search(r'\d+', x[0]).group()))])
            notice = f"""

--- PARSED REFERENCES ({len(reference_map)} found){source_info} ---
{ref_list}

Use these references when extracting claims. Only include reference_list in output if these are wrong or unusable.
If providing reference_list, it must be a COMPLETE replacement (not partial corrections).
"""
            return text + notice

        else:
            # Path C: No references found
            notice = f"""

--- NOTICE: No reference list detected{source_info} ---
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
