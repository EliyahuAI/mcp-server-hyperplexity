"""
Text Chunker for Parallel Claim Extraction

Identifies smart boundary positions for chunking large texts while preserving context.
The full text is sent to each extraction call, but with specific character ranges to focus on.
"""

import re
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger()


class TextChunker:
    """Identifies chunk boundaries for parallel claim extraction."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize text chunker with configuration.

        Args:
            config: Reference check configuration dict
        """
        # Get chunking config (with defaults if section missing)
        chunking_config = config.get('chunking', {})

        self.tokens_per_word = config.get('text_limits', {}).get('tokens_per_word', 1.33)
        self.threshold_tokens = chunking_config.get('threshold_tokens', 90000)
        self.chunk_target_tokens = chunking_config.get('chunk_target_tokens', 30000)
        self.chunk_max_tokens = chunking_config.get('chunk_max_tokens', 35000)
        self.max_chunks = chunking_config.get('max_chunks', 4)
        self.max_boundary_distance = chunking_config.get('max_boundary_distance', 2000)

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count using words * tokens_per_word ratio.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        words = len(text.split())
        return int(words * self.tokens_per_word)

    def should_chunk(self, enriched_text: str) -> bool:
        """
        Check if text should be chunked based on token threshold.

        Args:
            enriched_text: Text with CONFIRMED REFERENCES appended

        Returns:
            True if text exceeds threshold and should be chunked
        """
        # Only count the original text portion (not CONFIRMED REFERENCES)
        original_text = self._extract_original_text(enriched_text)
        tokens = self.estimate_tokens(original_text)

        logger.info(f"[CHUNKER] Text size: {len(original_text)} chars, ~{tokens} tokens (threshold: {self.threshold_tokens})")

        return tokens > self.threshold_tokens

    def get_chunk_boundaries(self, enriched_text: str) -> List[Dict[str, Any]]:
        """
        Calculate chunk boundary positions for the original text.

        The full enriched_text will be sent to each extraction call, but each
        call will focus on extracting claims from a specific character range.

        Args:
            enriched_text: Text with CONFIRMED REFERENCES appended

        Returns:
            List of chunk boundary dicts with:
                - chunk_id: Sequential ID (0, 1, 2, ...)
                - start_char: Start position in original text
                - end_char: End position in original text
                - estimated_tokens: Estimated tokens in this range
        """
        # Extract original text (before CONFIRMED REFERENCES section)
        original_text = self._extract_original_text(enriched_text)
        original_text_length = len(original_text)

        # Calculate number of chunks needed
        total_tokens = self.estimate_tokens(original_text)
        num_chunks = min(
            self.max_chunks,
            max(2, (total_tokens // self.chunk_target_tokens) + 1)
        )

        logger.info(
            f"[CHUNKER] Splitting {total_tokens} tokens into {num_chunks} chunks "
            f"(target: {self.chunk_target_tokens} tokens/chunk)"
        )

        # Find smart boundaries
        boundaries = self._find_smart_boundaries(original_text, num_chunks)

        # Build chunk metadata
        chunks = []
        for i in range(len(boundaries) - 1):
            start_char = boundaries[i]
            end_char = boundaries[i + 1]
            chunk_text = original_text[start_char:end_char]

            chunks.append({
                'chunk_id': i,
                'start_char': start_char,
                'end_char': end_char,
                'estimated_tokens': self.estimate_tokens(chunk_text),
                'char_count': len(chunk_text)
            })

        # Log chunk details
        for chunk in chunks:
            logger.info(
                f"[CHUNKER] Chunk {chunk['chunk_id']}: "
                f"chars {chunk['start_char']}-{chunk['end_char']} "
                f"({chunk['char_count']} chars, ~{chunk['estimated_tokens']} tokens)"
            )

        return chunks

    def _extract_original_text(self, enriched_text: str) -> str:
        """
        Extract the original text before CONFIRMED REFERENCES section.

        Args:
            enriched_text: Full enriched text

        Returns:
            Original text without CONFIRMED REFERENCES section
        """
        ref_marker = "--- CONFIRMED REFERENCES"

        if ref_marker in enriched_text:
            split_idx = enriched_text.index(ref_marker)
            return enriched_text[:split_idx].rstrip()

        # No references section, return entire text
        return enriched_text

    def _find_smart_boundaries(self, text: str, num_chunks: int) -> List[int]:
        """
        Find smart chunk boundaries at paragraph/section breaks.

        Args:
            text: Original text to chunk
            num_chunks: Number of chunks to create

        Returns:
            List of boundary positions (includes 0 at start and len(text) at end)
        """
        # Find potential boundary locations in priority order

        # Priority 1: Markdown headers (##, ###, etc.)
        header_positions = self._find_markdown_headers(text)

        # Priority 2: Paragraph breaks (double newlines)
        paragraph_positions = self._find_paragraph_breaks(text)

        # Priority 3: Single newlines
        line_positions = self._find_line_breaks(text)

        # Calculate target positions for splits
        target_chunk_size = len(text) // num_chunks
        split_targets = [i * target_chunk_size for i in range(1, num_chunks)]

        logger.info(
            f"[CHUNKER] Found {len(header_positions)} headers, "
            f"{len(paragraph_positions)} paragraphs, "
            f"{len(line_positions)} line breaks"
        )

        # Find best boundary near each target
        boundaries = [0]  # Start position

        for target_pos in split_targets:
            boundary = self._find_nearest_boundary(
                target_pos,
                header_positions,
                paragraph_positions,
                line_positions
            )
            boundaries.append(boundary)

            # Log what type of boundary was found
            boundary_type = "forced"
            if boundary in header_positions:
                boundary_type = "header"
            elif boundary in paragraph_positions:
                boundary_type = "paragraph"
            elif boundary in line_positions:
                boundary_type = "line"

            logger.info(
                f"[CHUNKER] Boundary at {boundary} (target: {target_pos}, "
                f"offset: {abs(boundary - target_pos)}, type: {boundary_type})"
            )

        boundaries.append(len(text))  # End position

        return boundaries

    def _find_markdown_headers(self, text: str) -> List[int]:
        """Find positions of markdown headers (##, ###, etc.)."""
        positions = []
        # Match markdown headers at start of line
        for match in re.finditer(r'\n#{1,6}\s+.*?\n', text):
            positions.append(match.start())
        return positions

    def _find_paragraph_breaks(self, text: str) -> List[int]:
        """Find positions of paragraph breaks (double newlines)."""
        positions = []
        for match in re.finditer(r'\n\n+', text):
            positions.append(match.start())
        return positions

    def _find_line_breaks(self, text: str) -> List[int]:
        """Find positions of single line breaks."""
        positions = []
        for match in re.finditer(r'\n', text):
            positions.append(match.start())
        return positions

    def _find_nearest_boundary(
        self,
        target: int,
        headers: List[int],
        paragraphs: List[int],
        lines: List[int]
    ) -> int:
        """
        Find nearest boundary to target position, with priority.

        Priority order: headers > paragraphs > lines > target position

        Args:
            target: Target position
            headers: List of header positions
            paragraphs: List of paragraph break positions
            lines: List of line break positions

        Returns:
            Best boundary position
        """
        best_boundary = None
        best_distance = float('inf')

        # Try headers first (highest priority)
        for pos in headers:
            distance = abs(pos - target)
            if distance <= self.max_boundary_distance and distance < best_distance:
                best_boundary = pos
                best_distance = distance

        # If no header found, try paragraphs
        if best_boundary is None:
            for pos in paragraphs:
                distance = abs(pos - target)
                if distance <= self.max_boundary_distance and distance < best_distance:
                    best_boundary = pos
                    best_distance = distance

        # If no paragraph found, try lines
        if best_boundary is None:
            for pos in lines:
                distance = abs(pos - target)
                if distance <= self.max_boundary_distance and distance < best_distance:
                    best_boundary = pos
                    best_distance = distance

        # Fallback: use target position if no good boundary found
        if best_boundary is None:
            logger.warning(
                f"[CHUNKER] No good boundary found near {target}, "
                f"using target position (may split mid-paragraph)"
            )
            best_boundary = target

        return best_boundary
