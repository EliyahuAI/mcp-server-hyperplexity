#!/usr/bin/env python3
"""
Text Labeler for Code-Based Extraction.
Converts source text into labeled format with heading and sentence markers.
"""

import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# Try to import nltk for better sentence splitting
try:
    import nltk
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        # Download punkt if not available
        try:
            nltk.download('punkt', quiet=True)
        except:
            pass
    HAS_NLTK = True
except ImportError:
    HAS_NLTK = False
    logger.warning("nltk not available, using simple sentence splitting")


class TextLabeler:
    """
    Labels source text with heading and sentence markers for code-based extraction.
    Format: H1| heading, then 1|, 2|, 3| for sentences under that heading.
    """

    def __init__(self):
        """Initialize text labeler."""
        pass

    def label_text(self, text: str) -> Tuple[str, Dict]:
        """
        Convert source text into labeled format with SUFFIX labels.
        Preserves all original text - just adds `X.Y labels at end of sentences.

        Args:
            text: Raw source text

        Returns:
            Tuple of (labeled_text, structure_dict)
            - labeled_text: Original text with `X.Y suffix labels
            - structure_dict: Lookup dict for reconstruction
        """
        if not text or not text.strip():
            return "", {}

        # Split into sentences while preserving original structure
        labeled_parts, structure = self._label_with_suffixes(text)

        labeled_text = "".join(labeled_parts)

        logger.debug(f"[LABELER] Labeled {len(structure.get('sections', []))} sections, "
                    f"{sum(len(s['sentences']) for s in structure.get('sections', []))} sentences")

        return labeled_text, structure

    def _label_with_suffixes(self, text: str) -> Tuple[List[str], Dict]:
        """
        Label text with suffix markers, preserving all original content.
        Returns list of text chunks and structure dict.
        """
        structure = {
            "sections": [],
            "headings": {}
        }

        lines = text.split('\n')
        current_section = 1
        current_sentence = 0
        labeled_parts = []
        current_section_sentences = {}
        current_heading = ""
        accumulated_text = []

        for line in lines:
            line_stripped = line.strip()

            # Check if this is a heading
            if line_stripped and self._is_heading(line_stripped):
                # Save previous section if exists
                if current_section_sentences:
                    structure["sections"].append({
                        "id": f"H{current_section}",
                        "heading": current_heading,
                        "sentences": current_section_sentences
                    })
                    current_section_sentences = {}
                    current_section += 1  # Increment for new section

                # New section
                current_heading = self._clean_heading(line_stripped)
                structure["headings"][f"H{current_section}"] = current_heading

                # Add heading with label (sentence 0)
                labeled_parts.append(line)
                labeled_parts.append(f" `{current_section}.0\n")

                # Store heading in structure
                sent_id = f"H{current_section}.0"
                current_section_sentences[sent_id] = {
                    "text": line_stripped,
                    "words": line_stripped.split()
                }

                current_sentence = 0

            elif line_stripped:
                # Regular content - split into sentences and label each
                sentences = self._split_sentences(line_stripped)

                for sent in sentences:
                    current_sentence += 1
                    sent_id = f"H{current_section}.{current_sentence}"

                    # Add sentence with suffix label
                    labeled_parts.append(sent)
                    labeled_parts.append(f" `{current_section}.{current_sentence}\n")

                    # Store in structure
                    current_section_sentences[sent_id] = {
                        "text": sent,
                        "words": sent.split()
                    }

            else:
                # Empty line - preserve it
                labeled_parts.append(line + "\n")

        # Save final section
        if current_section_sentences:
            structure["sections"].append({
                "id": f"H{current_section}",
                "heading": current_heading,
                "sentences": current_section_sentences
            })

        return labeled_parts, structure

    def _parse_sections(self, text: str) -> List[Dict]:
        """
        Parse text into sections with headings and sentences.

        Returns:
            List of dicts with {heading: str, sentences: List[str]}
        """
        # Detect headings using multiple strategies
        lines = text.split('\n')
        sections = []
        current_heading = ""
        current_text = []

        for line in lines:
            line_stripped = line.strip()

            if not line_stripped:
                continue

            # Check if this line is a heading
            if self._is_heading(line_stripped):
                # Save previous section if exists
                if current_text:
                    sentences = self._split_sentences(' '.join(current_text))
                    if sentences:
                        sections.append({
                            "heading": current_heading,
                            "sentences": sentences
                        })
                    current_text = []

                # Start new section
                current_heading = self._clean_heading(line_stripped)
            else:
                # Accumulate text
                current_text.append(line_stripped)

        # Add final section
        if current_text:
            sentences = self._split_sentences(' '.join(current_text))
            if sentences:
                sections.append({
                    "heading": current_heading,
                    "sentences": sentences
                })

        # If no sections were created (no headings detected), treat entire text as one section
        if not sections:
            sentences = self._split_sentences(text)
            if sentences:
                sections.append({
                    "heading": "",
                    "sentences": sentences
                })

        return sections

    def _is_heading(self, line: str) -> bool:
        """
        Detect if a line is a heading.
        Strategies:
        - Markdown: starts with # (but not #hashtags)
        - HTML: <h1> tags
        - Heuristic: short line, ends without punctuation, possibly all caps

        EXCLUDE:
        - Bullet points (-, *, •)
        - Table separators (|--|)
        - Lines with only emojis/symbols
        - Links (starts with http)
        """
        # Exclude markdown artifacts
        if line.startswith(('-', '*', '•', '|')):
            return False

        # Exclude links
        if line.startswith(('http://', 'https://', 'www.')):
            return False

        # Exclude emoji-only or symbol-heavy lines (>30% non-alphanumeric)
        alphanumeric = sum(c.isalnum() or c.isspace() for c in line)
        if len(line) > 0 and alphanumeric / len(line) < 0.5:
            return False

        # Markdown heading (# Header, ## Header, etc.)
        # Must have space after # to avoid hashtags
        if re.match(r'^#{1,6}\s+\w', line):
            return True

        # HTML heading
        if re.match(r'<h[1-6]>', line, re.IGNORECASE):
            return True

        # Heuristic: short, no ending punctuation, mostly alphanumeric
        if len(line) < 100 and not line.endswith(('.', '!', '?', ',')):
            # Remove markdown formatting for analysis
            clean_line = re.sub(r'[*_`]', '', line).strip()

            # Check if mostly uppercase or reasonable heading length
            if clean_line.isupper() and len(clean_line.split()) >= 2:
                return True
            # Short line without ending punctuation might be a heading
            if len(clean_line) < 60 and 2 <= len(clean_line.split()) <= 8:
                return True

        return False

    def _clean_heading(self, line: str) -> str:
        """Clean heading text by removing markdown/HTML markers."""
        # Remove markdown #
        line = re.sub(r'^#+\s*', '', line)

        # Remove HTML tags
        line = re.sub(r'</?h[1-6]>', '', line, flags=re.IGNORECASE)

        # Remove markdown bold/italic
        line = re.sub(r'\*+', '', line)

        return line.strip()

    def _split_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences.
        Uses nltk if available, otherwise improved regex.
        """
        if not text or not text.strip():
            return []

        if HAS_NLTK:
            try:
                sentences = nltk.sent_tokenize(text)
                return [s.strip() for s in sentences if s.strip()]
            except Exception as e:
                logger.warning(f"[LABELER] nltk tokenization failed: {e}, using regex")

        # Fallback: improved regex splitting
        # Common abbreviations that shouldn't split sentences
        # Replace abbreviations temporarily
        protected = text
        abbreviations = ['Dr.', 'Mr.', 'Mrs.', 'Ms.', 'Prof.', 'Sr.', 'Jr.',
                        'vs.', 'Inc.', 'Ltd.', 'Corp.', 'Co.', 'etc.', 'e.g.', 'i.e.']

        # Temporarily replace periods in abbreviations
        for i, abbr in enumerate(abbreviations):
            protected = protected.replace(abbr, f'ABBR{i}PLACEHOLDER')

        # Split on .!? followed by space and capital letter or number
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', protected)

        # Restore abbreviations
        for i, abbr in enumerate(abbreviations):
            sentences = [s.replace(f'ABBR{i}PLACEHOLDER', abbr) for s in sentences]

        return [s.strip() for s in sentences if s.strip()]
