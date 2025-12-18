#!/usr/bin/env python3
"""
Code Resolver for Code-Based Extraction.
Resolves location codes back to text with graceful fallback.
"""

import re
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class CodeResolver:
    """
    Resolves location codes (H1.2, H1.2-4, H1.2.W5-7) back to text.
    Implements graceful fallback when codes are invalid.
    """

    def __init__(self, structure: Dict, labeled_text: str = None, original_text: str = None):
        """
        Initialize resolver with text structure.

        Args:
            structure: Structure dict from TextLabeler
            labeled_text: Labeled text with `X.Y suffixes (for suffix-based resolution)
            original_text: Original unlabeled text (for `* pass-all code)
        """
        self.structure = structure
        self.sections = {s["id"]: s for s in structure.get("sections", [])}
        self.headings = structure.get("headings", {})
        self.labeled_text = labeled_text
        self.original_text = original_text
        self.label_map = structure.get('label_map', {})  # Direct label->text mapping

    def resolve(self, code: str) -> str:
        """
        Resolve a location code to text with graceful fallback.

        Supported formats:
        - H1.2         → Single sentence
        - H1.2-4       → Sentence range (shorthand for H1.2-H1.4)
        - H1.2-H1.4    → Sentence range (explicit)
        - H1.2.W5-7    → Word range within sentence
        - [H1.2.W1-3] H1.5 → Bracketed code resolved and prepended
        - H1.2 [literal text] → Literal text in brackets preserved
        - [re: Context] H1.2 → Context marker (literal) preserved

        Resolution strategy for brackets:
        - Try to parse bracket content as location code
        - If matches → resolve to text
        - If doesn't match → keep as literal annotation

        Fallback strategy:
        - Word range invalid → Return full sentence(s)
        - Sentence range too large → Return available sentences
        - Section missing → Return empty string and log

        Args:
            code: Location code string (may include brackets)

        Returns:
            Resolved text (empty string if completely invalid)
        """
        if not code or not code.strip():
            return ""

        code_clean = code.strip()

        try:
            # Special case: `* means pass entire source
            if code_clean == '`*' or code_clean == '*':
                if self.original_text:
                    logger.info(f"[RESOLVER] Pass-all code `* - returning entire source ({len(self.original_text)} chars)")
                    return self.original_text
                else:
                    logger.warning(f"[RESOLVER] Pass-all code `* but no original_text available")
                    return ""

            # For simple codes without brackets (e.g., "`1", "`1-3"), directly resolve
            # Strip backtick prefix if present
            if code_clean.startswith('`'):
                code_clean = code_clean[1:]

            if not '[' in code_clean and self._is_location_code(code_clean):
                result = self._resolve_location_code(code_clean)
                return self._deduplicate_lines(result)

            # Parse complex code strings with brackets and/or literals
            resolved_parts = []
            current_pos = 0

            # Find all [...] patterns and `code patterns
            # Pattern: [...] or `code (with backtick prefix)
            # Order matters: match longer patterns first (section.sentence before simple number)
            pattern = r'\[([^\]]+)\]|`(H\d+(?:\.\d+)?(?:\.w\d+(?:-(?:\d+|H\d+\.\d+(?:\.w\d+)?))?)?(?:-(?:\d+|H\d+\.\d+))?)|`(\d+\.\d+(?:\.w\d+(?:-\d+)?)?(?:-\d+\.\d+)?)|`(\d+(?:\.w\d+(?:-\d+)?)?(?:-\d+)?)'

            for match in re.finditer(pattern, code_clean, re.IGNORECASE):
                # Add any literal text before this match
                if match.start() > current_pos:
                    literal = code_clean[current_pos:match.start()].strip()
                    if literal:
                        resolved_parts.append(literal)

                if match.group(1):  # Bracketed content
                    bracket_content = match.group(1).strip()
                    # Strip backtick prefix if present
                    if bracket_content.startswith('`'):
                        bracket_content = bracket_content[1:]
                    # Try to resolve as location code
                    if self._is_location_code(bracket_content):
                        resolved_text = self._resolve_location_code(bracket_content)
                        if resolved_text:
                            resolved_parts.append(f"[{resolved_text}]")
                        else:
                            # Failed to resolve, keep as literal
                            logger.debug(f"[RESOLVER] Bracket code '{bracket_content}' failed to resolve, keeping as literal")
                            resolved_parts.append(f"[{bracket_content}]")
                    else:
                        # Not a location code, keep as literal (restore backtick if it had one)
                        original_bracket = match.group(1)
                        resolved_parts.append(f"[{original_bracket}]")

                elif match.group(2) or match.group(3) or match.group(4):  # Backtick-prefixed location code
                    # Group 2: H codes, Group 3: section.sentence, Group 4: simple
                    location_code = match.group(2) or match.group(3) or match.group(4)
                    resolved_text = self._resolve_location_code(location_code)
                    if resolved_text:
                        resolved_parts.append(resolved_text)
                    else:
                        # Failed to resolve, skip
                        logger.warning(f"[RESOLVER] Failed to resolve location code '{location_code}'")

                current_pos = match.end()

            # Add any remaining literal text
            if current_pos < len(code_clean):
                literal = code_clean[current_pos:].strip()
                if literal:
                    resolved_parts.append(literal)

            # Join all parts with appropriate spacing
            result = " ".join(resolved_parts)
            return self._deduplicate_lines(result.strip())

        except Exception as e:
            logger.warning(f"[RESOLVER] Failed to resolve code '{code}': {e}")
            return ""

    def _deduplicate_lines(self, text: str) -> str:
        """Remove consecutive duplicate lines from text."""
        if not text:
            return text

        lines = text.split('\n')
        deduped = []
        prev_line = None

        for line in lines:
            line_stripped = line.strip()
            if line_stripped != prev_line:
                deduped.append(line)
                prev_line = line_stripped

        return '\n'.join(deduped)

    def _is_location_code(self, text: str) -> bool:
        """Check if text matches location code pattern."""
        # Patterns:
        # Section.sentence: 1.1, 2.3, 1.0 (with sentence number)
        # Simple: 1, 1-3, 1.w5-7 (single number or range)
        # Heading-only: H1, H2 (entire section)
        # Full: H1.2, H1.2-4, H1.2.w5-7 (with H prefix)
        section_sentence_pattern = r'^\d+\.\d+(?:\.w\d+(?:-\d+)?)?(?:-\d+(?:\.\d+)?)?$'  # 1.1, 1.1.w5-7, 1.1-1.3, 1.1-3
        simple_pattern = r'^\d+(?:\.w\d+(?:-\d+)?)?(?:-\d+)?$'  # 1, 1-3, 1.w5-7
        heading_only_pattern = r'^H\d+$'  # H1, H2
        full_pattern = r'^H\d+\.\d+(?:\.w\d+(?:-\d+)?)?(?:-(?:\d+|H\d+\.\d+(?:\.w\d+)?))?$'  # H1.2, H1.2-4
        return bool(
            re.match(section_sentence_pattern, text, re.IGNORECASE) or
            re.match(simple_pattern, text, re.IGNORECASE) or
            re.match(heading_only_pattern, text) or
            re.match(full_pattern, text, re.IGNORECASE)
        )

    def _resolve_location_code(self, code: str) -> str:
        """
        Resolve a single location code (without brackets or literals).
        Handles both simple (1, 1-3, 1.w5-7) and full (H1.2, H1.2-4) formats.
        """
        if not code or not code.strip():
            return ""

        code = code.strip()

        try:
            # Normalize simple codes to full format for single-section documents
            # If code is just a number (e.g., "1", "1-3", "1.w5-7"), assume H1 section
            if re.match(r'^\d', code):
                # Simple format - normalize to H1.X
                code = self._normalize_simple_code(code)

            # Parse the code (now in full H1.X format)
            if '.w' in code.lower():
                # Word-level code
                return self._resolve_word_code(code)
            elif '-' in code:
                # Range code
                return self._resolve_range_code(code)
            else:
                # Single sentence code
                return self._resolve_sentence_code(code)

        except Exception as e:
            logger.warning(f"[RESOLVER] Failed to resolve location code '{code}': {e}")
            return ""

    def _normalize_simple_code(self, code: str) -> str:
        """
        Convert simple code to full H format. Parse left-to-right:
        - 1.1-1.3 → H1.1-H1.3 (explicit range, has D.D after dash)
        - 1.1-3 → H1.1-H1.3 (shorthand, just D after dash)
        - 1.1.w5-7 → H1.1.w5-7 (word range)
        - 1.1 → H1.1 (single)
        - 1 → H1.1 (bare number)
        """
        # Clean spaces around dashes
        code = code.replace(' -', '-').replace('- ', '-')

        # Check for section.sentence pattern at start: D.D
        if re.match(r'^\d+\.\d+', code):
            # Has section.sentence, check what follows
            if '-' in code:
                # Has a dash - check what's after it
                base, after_dash = code.split('-', 1)

                if re.match(r'^\d+\.\d+', after_dash):
                    # Explicit range: 1.1-1.3 → H1.1-H1.3
                    return f"H{base}-H{after_dash}"
                elif re.match(r'^\d+$', after_dash):
                    # Shorthand: 1.1-3 → H1.1-H1.3
                    section = base.split('.')[0]
                    return f"H{base}-H{section}.{after_dash}"
                else:
                    # Unknown format, just prepend H
                    return f"H{code}"
            else:
                # No dash, pure section.sentence or word range
                return f"H{code}"

        # Simple number range: 1-3 → H1.1-H1.3
        if re.match(r'^\d+-\d+$', code):
            parts = code.split('-')
            return f"H1.{parts[0]}-H1.{parts[1]}"

        # Simple number: 1 → H1.1
        if re.match(r'^\d+$', code):
            return f"H1.{code}"

        # Already in H format or unknown, return as-is
        return code

    def _resolve_sentence_code(self, code: str) -> str:
        """
        Resolve single sentence code: H1.2 or 1.2

        Uses direct label_map lookup first, then falls back to structure dict.
        """
        original_code = code

        # Try direct label_map lookup first (fast path)
        if self.label_map and code in self.label_map:
            text = self.label_map[code]

            # Check if this is a table row - auto-prepend header
            sent_id = f"H{code}" if not code.startswith('H') else code
            for section in self.sections.values():
                sent_data = section['sentences'].get(sent_id)
                if sent_data and sent_data.get('is_table_row'):
                    # This is a table data row, prepend header
                    header_id = sent_data.get('table_header_id')
                    if header_id:
                        header_text = section['sentences'].get(header_id, {}).get('text', '')
                        if header_text:
                            logger.info(f"[RESOLVER] Auto-prepending table header to row {code}")
                            return f"{header_text}\n{text}"

            return text

        # Normalize code format (1.2 → H1.2)
        if re.match(r'^\d+\.\d+$', code):
            # Simple format like 1.2 - check label_map first
            if code in self.label_map:
                return self.label_map[code]
            # Convert to H1.2 for structure lookup
            code = f"H{code}"
            logger.debug(f"[RESOLVER] Normalized {original_code} → {code}")

        # Check for heading-only code: H1, H2, etc. (no sentence number)
        heading_only_match = re.match(r'^H(\d+)$', code)
        if heading_only_match:
            section_num = heading_only_match.group(1)
            section_id = f"H{section_num}"
            section = self.sections.get(section_id)

            if not section:
                logger.warning(f"[RESOLVER] Section {section_id} not found")
                return ""

            # Return all sentences from this section joined together
            sentences = section.get("sentences", {})
            if not sentences:
                logger.warning(f"[RESOLVER] Section {section_id} has no sentences")
                return ""

            # Get all sentences in order
            sent_ids = sorted(sentences.keys(), key=lambda x: int(x.split('.')[-1]))
            all_text = " ".join(sentences[sid]["text"] for sid in sent_ids)

            logger.info(f"[RESOLVER] Heading-only code {code} resolved to entire section ({len(sent_ids)} sentences)")
            return all_text

        # Parse H1.2 (with sentence number)
        match = re.match(r'H(\d+)\.(\d+)', code)
        if not match:
            logger.warning(f"[RESOLVER] Invalid sentence code format: {code}")
            return ""

        section_num = match.group(1)
        sent_num = match.group(2)
        section_id = f"H{section_num}"
        sent_id = f"H{section_num}.{sent_num}"

        # Lookup sentence
        section = self.sections.get(section_id)
        if not section:
            logger.warning(f"[RESOLVER] Section {section_id} not found")
            return ""

        sent_data = section["sentences"].get(sent_id)
        if not sent_data:
            logger.warning(f"[RESOLVER] Sentence {sent_id} not found in section {section_id}")
            return ""

        return sent_data["text"]

    def _resolve_range_code(self, code: str) -> str:
        """
        Resolve range code: 1.2-1.4, H1.2-4, or H1.2-H1.4

        Fallback: If range is too large, take what exists
        """
        # Check for section.sentence range: 1.2-1.4 (normalize to H1.2-H1.4)
        section_range_match = re.match(r'(\d+)\.(\d+)-(\d+)\.(\d+)$', code)
        if section_range_match:
            section_num = section_range_match.group(1)
            start_sent = section_range_match.group(2)
            end_section = section_range_match.group(3)
            end_sent = section_range_match.group(4)

            # If different sections, not supported yet
            if section_num != end_section:
                logger.warning(f"[RESOLVER] Cross-section ranges not supported: {code}")
                return ""

            # Convert to H format and continue to explicit range parsing
            code = f"H{section_num}.{start_sent}-H{section_num}.{end_sent}"
            logger.debug(f"[RESOLVER] Normalized section.sentence range to: {code}")
            # Fall through to explicit range parsing below

        # Check for shorthand: H1.2-4 (expand to H1.2-H1.4)
        # But NOT 1.2-1.4 or H1.2-H1.4 (those have explicit end section)
        shorthand_match = re.match(r'^(H\d+)\.(\d+)-(\d+)$', code)
        if shorthand_match:
            section_id = shorthand_match.group(1)
            start_sent = shorthand_match.group(2)
            end_sent = shorthand_match.group(3)
            code = f"{section_id}.{start_sent}-{section_id}.{end_sent}"
            logger.debug(f"[RESOLVER] Expanded shorthand to: {code}")

        # Parse explicit range: H1.2-H1.4
        range_match = re.match(r'(H\d+)\.(\d+)-(H\d+)\.(\d+)', code)
        if not range_match:
            logger.warning(f"[RESOLVER] Invalid range code format: {code}")
            return ""

        start_section = range_match.group(1)
        start_sent = int(range_match.group(2))
        end_section = range_match.group(3)
        end_sent = int(range_match.group(4))

        # For simplicity, only support ranges within same section
        if start_section != end_section:
            logger.warning(f"[RESOLVER] Cross-section ranges not yet supported: {code}")
            # Fallback: just return first sentence
            return self._resolve_sentence_code(f"{start_section}.{start_sent}")

        section_num = start_section[1:]  # H1 -> 1

        # Use label_map for fast lookup if available
        if self.label_map:
            sentences = []
            for sent_num in range(start_sent, end_sent + 1):
                label = f"{section_num}.{sent_num}"
                text = self.label_map.get(label)
                if text:
                    sentences.append(text)
                else:
                    # Sentence doesn't exist, clamp range
                    logger.warning(f"[RESOLVER] Sentence {label} not found, clamping range")
                    break
            # Join with newlines (important for table rows)
            return "\n".join(sentences) if sentences else ""

        # Fallback to structure lookup
        section_id = start_section
        section = self.sections.get(section_id)
        if not section:
            logger.warning(f"[RESOLVER] Section {section_id} not found")
            return ""

        # Collect sentences in range
        sentences = []
        for sent_num in range(start_sent, end_sent + 1):
            sent_id = f"{section_id}.{sent_num}"
            sent_data = section["sentences"].get(sent_id)
            if sent_data:
                sentences.append(sent_data["text"])
            else:
                logger.warning(f"[RESOLVER] Sentence {sent_id} not in range, clamping")
                break

        # Join with newlines (important for table rows)
        return "\n".join(sentences) if sentences else ""

    def _resolve_word_code(self, code: str) -> str:
        """
        Resolve word-level code: H1.2.w5-7 or H1.2.w5-H1.3.w2

        Fallback: If word range invalid, return full sentence(s)
        """
        # Check for cross-sentence word range: H1.2.w5-H1.3.w2
        cross_match = re.match(r'(H\d+\.\d+)\.w(\d+)-(H\d+\.\d+)\.w(\d+)', code, re.IGNORECASE)
        if cross_match:
            # Complex case - get full sentences and extract words
            start_sent_id = cross_match.group(1)
            start_word = int(cross_match.group(2))
            end_sent_id = cross_match.group(3)
            end_word = int(cross_match.group(4))

            # For now, fallback to full sentence range
            logger.warning(f"[RESOLVER] Cross-sentence word ranges not fully supported, "
                          f"returning full sentences: {code}")
            return self._resolve_range_code(f"{start_sent_id}-{end_sent_id}")

        # Single sentence word range: H1.2.w5-7
        word_match = re.match(r'(H\d+\.\d+)\.w(\d+)(?:-(\d+))?', code, re.IGNORECASE)
        if not word_match:
            logger.warning(f"[RESOLVER] Invalid word code format: {code}")
            return ""

        sent_id = word_match.group(1)
        start_word = int(word_match.group(2))
        end_word = int(word_match.group(3)) if word_match.group(3) else start_word

        # Get sentence text - try label_map first
        sent_text = None
        if self.label_map:
            # Extract simple label from H1.1 format
            parts = sent_id.split('.')
            if len(parts) >= 2 and parts[0].startswith('H'):
                simple_label = f"{parts[0][1:]}.{parts[1]}"
                sent_text = self.label_map.get(simple_label) or self.label_map.get(sent_id)

        # Fallback to structure lookup
        if not sent_text:
            section_id = sent_id.rsplit('.', 1)[0]
            section = self.sections.get(section_id)
            if not section:
                logger.warning(f"[RESOLVER] Section {section_id} not found")
                return ""

            sent_data = section["sentences"].get(sent_id)
            if not sent_data:
                logger.warning(f"[RESOLVER] Sentence {sent_id} not found")
                return ""
            sent_text = sent_data["text"]

        words = sent_text.split()
        total_words = len(words)

        # Clamp word indices (1-indexed in code, 0-indexed in array)
        start_idx = max(0, start_word - 1)
        end_idx = min(total_words - 1, end_word - 1)

        # Fallback if indices are completely out of bounds
        if start_idx >= total_words:
            logger.warning(f"[RESOLVER] Word range {start_word}-{end_word} out of bounds "
                          f"(max {total_words}), returning full sentence")
            return sent_data["text"]

        # Clamp and warn if needed
        if end_word > total_words:
            logger.warning(f"[RESOLVER] End word {end_word} exceeds max {total_words}, clamping")

        # Extract word range
        selected_words = words[start_idx:end_idx + 1]
        return " ".join(selected_words) if selected_words else sent_data["text"]

    def get_heading_for_sentence(self, sent_id: str) -> Optional[str]:
        """
        Get heading text for a sentence ID.

        Args:
            sent_id: Sentence ID like H1.2

        Returns:
            Heading text or None
        """
        section_id = sent_id.rsplit('.', 1)[0]
        return self.headings.get(section_id)
