#!/usr/bin/env python3
"""
Debug logging for code-based extraction.
Saves inputs/encoding/outputs/decoding when things don't work correctly.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class CodeExtractionDebugger:
    """
    Logs code extraction pipeline for debugging.
    Saves full context when issues are detected.
    """

    def __init__(self, debug_dir: str = None):
        """
        Initialize debugger.

        Args:
            debug_dir: Directory to save debug files (default: /tmp in Lambda, else test_results/code_extraction_debug)
        """
        if debug_dir is None:
            # Check if we're in Lambda environment (read-only filesystem)
            if os.path.exists('/var/task'):  # Lambda indicator
                debug_dir = '/tmp/code_extraction_debug'
            else:
                debug_dir = os.path.join(
                    os.path.dirname(__file__),
                    'test_results/code_extraction_debug'
                )

        self.debug_dir = debug_dir

        # Try to create directory, but don't fail if we can't
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not create debug directory {self.debug_dir}: {e}")
            # Fallback to /tmp if creation failed
            self.debug_dir = '/tmp/code_extraction_debug'
            try:
                os.makedirs(self.debug_dir, exist_ok=True)
            except Exception:
                logger.error("Could not create debug directory even in /tmp - debug logging disabled")
                self.debug_dir = None

        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.extraction_count = 0

    def log_extraction(
        self,
        source_id: str,
        original_text: str,
        labeled_text: str,
        structure: Dict,
        ai_response: Dict,
        resolved_snippets: List[Dict],
        issues: List[str] = None,
        query: str = None
    ):
        """
        Log a complete extraction pipeline.

        Args:
            source_id: Identifier for the source (e.g., "S1.2.3")
            original_text: Original source text
            labeled_text: Labeled format sent to AI
            structure: Structure dict from labeler
            ai_response: Raw AI response with codes
            resolved_snippets: Final snippets after code resolution
            issues: List of issues detected (empty snippets, failed resolution, etc.)
        """
        self.extraction_count += 1
        timestamp = datetime.now().strftime('%H%M%S')

        # Determine severity
        has_issues = bool(issues)
        severity = "ERROR" if has_issues else "SUCCESS"

        # Create filename
        filename = f"{self.session_id}_{self.extraction_count:03d}_{source_id}_{severity}.json"
        filepath = os.path.join(self.debug_dir, filename)

        # Build debug record
        debug_record = {
            "metadata": {
                "source_id": source_id,
                "timestamp": timestamp,
                "session_id": self.session_id,
                "extraction_number": self.extraction_count,
                "severity": severity,
                "issues": issues or [],
                "query": query or "Unknown"
            },
            "input": {
                "original_text": original_text,
                "original_length": len(original_text),
                "original_word_count": len(original_text.split())
            },
            "encoding": {
                "labeled_text": labeled_text,
                "structure": self._simplify_structure(structure),
                "section_count": len(structure.get('sections', [])),
                "sentence_count": sum(len(s['sentences']) for s in structure.get('sections', []))
            },
            "ai_output": {
                "raw_response": ai_response,
                "codes_returned": self._extract_codes(ai_response)
            },
            "decoding": {
                "resolved_snippets": resolved_snippets,
                "snippet_count": len(resolved_snippets),
                "total_resolved_words": sum(len(s.get('text', '').split()) for s in resolved_snippets)
            },
            "analysis": {
                "compression_ratio": self._calculate_compression(labeled_text, ai_response),
                "resolution_success_rate": self._calculate_resolution_rate(resolved_snippets),
                "empty_snippets": sum(1 for s in resolved_snippets if not s.get('text', '').strip())
            }
        }

        # Save to file (skip if debug disabled)
        if self.debug_dir:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(debug_record, f, indent=2, ensure_ascii=False)

                # Log
                if has_issues:
                    logger.warning(f"[DEBUG] Extraction {source_id} had issues, saved to {filename}")
                    for issue in issues:
                        logger.warning(f"  - {issue}")
                else:
                    logger.debug(f"[DEBUG] Extraction {source_id} successful, logged to {filename}")

                return filepath
            except Exception as e:
                logger.warning(f"[DEBUG] Could not save debug file: {e}")
                return None
        else:
            # Debug disabled - just log issues
            if has_issues:
                logger.warning(f"[DEBUG] Extraction {source_id} had issues (debug logging disabled)")
                for issue in issues:
                    logger.warning(f"  - {issue}")
            return None

    def _simplify_structure(self, structure: Dict) -> Dict:
        """Simplify structure for JSON serialization."""
        simplified = {
            "sections": []
        }

        for section in structure.get('sections', []):
            simplified_section = {
                "id": section.get('id'),
                "heading": section.get('heading'),
                "sentence_ids": list(section.get('sentences', {}).keys())
            }
            simplified['sections'].append(simplified_section)

        return simplified

    def _extract_codes(self, ai_response: Dict) -> List[str]:
        """Extract all location codes from AI response."""
        codes = []

        quotes_by_search = ai_response.get('quotes_by_search', {})
        for search_num, quotes in quotes_by_search.items():
            for quote in quotes:
                if isinstance(quote, dict) and 'c' in quote:
                    codes.append(quote['c'])

        return codes

    def _calculate_compression(self, labeled_text: str, ai_response: Dict) -> float:
        """Calculate output token compression ratio."""
        input_tokens = len(labeled_text.split())
        codes = self._extract_codes(ai_response)
        output_tokens = sum(len(code.split()) for code in codes)

        if input_tokens == 0:
            return 0.0

        return 1.0 - (output_tokens / input_tokens)

    def _calculate_resolution_rate(self, snippets: List[Dict]) -> float:
        """Calculate how many snippets resolved successfully."""
        if not snippets:
            return 0.0

        successful = sum(1 for s in snippets if s.get('text', '').strip())
        return successful / len(snippets)

    def detect_issues(
        self,
        labeled_text: str,
        structure: Dict,
        ai_response: Dict,
        resolved_snippets: List[Dict]
    ) -> List[str]:
        """
        Detect potential issues in the extraction pipeline.

        Returns:
            List of issue descriptions
        """
        issues = []

        # Check for empty response
        quotes_by_search = ai_response.get('quotes_by_search', {})
        if not quotes_by_search:
            issues.append("AI returned no quotes")
            return issues

        # Check for failed resolutions
        empty_count = sum(1 for s in resolved_snippets if not s.get('text', '').strip())
        if empty_count > 0:
            issues.append(f"{empty_count}/{len(resolved_snippets)} codes failed to resolve")

        # Check for malformed codes
        codes = self._extract_codes(ai_response)
        for code in codes:
            if not self._is_valid_code_format(code):
                issues.append(f"Potentially malformed code: '{code}'")

        # Check for unreferenced sections
        max_section = len(structure.get('sections', []))
        for code in codes:
            # Extract H numbers from code
            import re
            h_numbers = re.findall(r'H(\d+)', code)
            for h_num in h_numbers:
                if int(h_num) > max_section:
                    issues.append(f"Code references non-existent section: '{code}' (max: H{max_section})")

        # Check for very low quality scores
        low_quality = [s for s in resolved_snippets if s.get('p', 1.0) <= 0.15]
        if len(low_quality) > len(resolved_snippets) / 2:
            issues.append(f"High proportion of low-quality snippets: {len(low_quality)}/{len(resolved_snippets)}")

        return issues

    def _is_valid_code_format(self, code: str) -> bool:
        """Check if code roughly matches expected patterns."""
        import re

        # Remove brackets and context markers
        clean_code = re.sub(r'\[.*?\]', '', code).strip()

        if not clean_code:
            return False  # Only had brackets, no actual code

        # Strip backtick prefix if present
        if clean_code.startswith('`'):
            clean_code = clean_code[1:].strip()

        if not clean_code:
            return False

        # Check for simple pattern (`1, `1-3, `1.w5-7) or full pattern (H1.2, H1.2-4)
        simple_pattern = r'^\d+(?:\.w\d+(?:-\d+)?)?(?:-\d+)?$'
        full_pattern = r'^H\d+\.\d+'

        if re.match(simple_pattern, clean_code, re.IGNORECASE) or re.search(full_pattern, clean_code):
            return True

        return False

    def create_summary_report(self) -> str:
        """
        Create a summary report of all extractions in this session.

        Returns:
            Path to summary report
        """
        summary_path = os.path.join(self.debug_dir, f"{self.session_id}_SUMMARY.json")

        # Collect all debug files from this session
        debug_files = [
            f for f in os.listdir(self.debug_dir)
            if f.startswith(self.session_id) and f.endswith('.json') and 'SUMMARY' not in f
        ]

        # Analyze
        total = len(debug_files)
        errors = sum(1 for f in debug_files if 'ERROR' in f)
        successes = sum(1 for f in debug_files if 'SUCCESS' in f)

        summary = {
            "session_id": self.session_id,
            "total_extractions": total,
            "successes": successes,
            "errors": errors,
            "error_rate": errors / total if total > 0 else 0,
            "debug_files": sorted(debug_files)
        }

        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)

        logger.info(f"[DEBUG] Session summary: {successes} success, {errors} errors ({total} total)")
        logger.info(f"[DEBUG] Summary saved to: {summary_path}")

        return summary_path
