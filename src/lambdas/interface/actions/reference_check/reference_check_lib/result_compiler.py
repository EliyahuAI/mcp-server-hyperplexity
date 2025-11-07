"""
Result Compiler

Compiles validation results into CSV format.
"""

import csv
import io
import logging
from typing import Dict, Any, List
from collections import Counter

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class ResultCompiler:
    """Compiles validation results into CSV."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize result compiler.

        Args:
            config: Reference check configuration dict
        """
        self.config = config
        self.csv_columns = config['output']['csv_columns']

    def compile_to_csv(self, validation_results: List[Dict[str, Any]]) -> str:
        """
        Compile validation results into CSV format.

        Args:
            validation_results: List of validation result dicts

        Returns:
            CSV string
        """
        logger.info(f"[COMPILE] Compiling {len(validation_results)} validation results to CSV")

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(self.csv_columns)

        # Write data rows
        for result in validation_results:
            row = [
                result.get('claim_id', ''),
                result.get('statement', ''),
                result.get('context', ''),
                result.get('reference', ''),
                result.get('reference_description', ''),
                result.get('reference_says', ''),
                result.get('qualified_fact', result.get('statement', '')),
                result.get('support_level', ''),
                result.get('validation_notes', '')
            ]
            writer.writerow(row)

        csv_string = output.getvalue()
        output.close()

        logger.info(f"[COMPILE] Generated CSV with {len(validation_results)} rows")
        return csv_string

    def get_summary_stats(self, validation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate summary statistics from validation results.

        Args:
            validation_results: List of validation result dicts

        Returns:
            Summary stats dict
        """
        total_claims = len(validation_results)

        # Count support levels
        support_levels = [r.get('support_level', 'unknown') for r in validation_results]
        support_counts = Counter(support_levels)

        # Count accessible vs inaccessible
        accessible_count = sum(1 for r in validation_results if r.get('accessible', False))
        inaccessible_count = total_claims - accessible_count

        # Calculate average confidence
        confidences = [r.get('confidence', 0) for r in validation_results]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        # Count by reference type
        with_references = sum(1 for r in validation_results if r.get('reference'))
        without_references = total_claims - with_references

        summary = {
            'total_claims': total_claims,
            'claims_with_references': with_references,
            'claims_without_references': without_references,
            'accessible_count': accessible_count,
            'inaccessible_count': inaccessible_count,
            'average_confidence': round(avg_confidence, 2),
            'support_level_breakdown': dict(support_counts),
            'support_level_percentages': {
                level: round(count / total_claims * 100, 1) if total_claims > 0 else 0
                for level, count in support_counts.items()
            }
        }

        logger.info(f"[COMPILE] Summary: {summary}")
        return summary


def compile_results_to_csv(validation_results: List[Dict[str, Any]], config: Dict[str, Any]) -> str:
    """
    Convenience function to compile results to CSV.

    Args:
        validation_results: List of validation result dicts
        config: Reference check configuration

    Returns:
        CSV string
    """
    compiler = ResultCompiler(config)
    return compiler.compile_to_csv(validation_results)


def get_summary_stats(validation_results: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to get summary stats.

    Args:
        validation_results: List of validation result dicts
        config: Reference check configuration

    Returns:
        Summary stats dict
    """
    compiler = ResultCompiler(config)
    return compiler.get_summary_stats(validation_results)
