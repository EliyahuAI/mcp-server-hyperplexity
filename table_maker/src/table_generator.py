#!/usr/bin/env python3
"""
Table generator for table generation system.
Generates CSV files from table structures and appends rows to existing tables.
"""

import csv
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)


class TableGenerator:
    """Generate and manipulate CSV tables from structured data."""

    def __init__(self):
        """Initialize table generator."""
        logger.info("Initialized TableGenerator")

    def generate_csv(
        self,
        columns: List[Dict[str, Any]],
        rows: List[Dict[str, Any]],
        output_path: str,
        include_metadata: bool = True
    ) -> Dict[str, Any]:
        """
        Generate CSV file from table structure.

        Args:
            columns: List of column definitions with 'name', 'description', etc.
            rows: List of row data as dictionaries
            output_path: Path where CSV file should be saved
            include_metadata: Whether to include metadata comment at top of CSV

        Returns:
            Dictionary with generation results:
            {
                'success': bool,
                'output_path': str,
                'row_count': int,
                'column_count': int,
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'output_path': output_path,
            'row_count': 0,
            'column_count': 0,
            'error': None
        }

        try:
            # Validate inputs
            if not columns:
                raise ValueError("Columns list cannot be empty")

            if not rows:
                logger.warning("No rows provided, generating empty table")

            # Extract column names in order
            column_names = [col['name'] for col in columns]
            result['column_count'] = len(column_names)

            # Ensure output directory exists
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)

            # Write CSV file
            with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=column_names)

                # Write metadata as comment if requested
                if include_metadata:
                    metadata_lines = self._generate_metadata_comment(columns, rows)
                    for line in metadata_lines:
                        csvfile.write(f"# {line}\n")

                # Write header
                writer.writeheader()

                # Write rows
                for row in rows:
                    # Ensure all columns are present (fill missing with empty string)
                    row_data = {col: row.get(col, '') for col in column_names}
                    writer.writerow(row_data)
                    result['row_count'] += 1

            result['success'] = True
            logger.info(
                f"Generated CSV: {output_path} "
                f"({result['row_count']} rows, {result['column_count']} columns)"
            )

        except Exception as e:
            error_msg = f"Error generating CSV: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg

        return result

    def append_rows(
        self,
        csv_path: str,
        new_rows: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Append rows to existing CSV file.

        Args:
            csv_path: Path to existing CSV file
            new_rows: List of new row data to append

        Returns:
            Dictionary with operation results:
            {
                'success': bool,
                'rows_added': int,
                'total_rows': int,
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'rows_added': 0,
            'total_rows': 0,
            'error': None
        }

        try:
            # Validate CSV file exists
            csv_path_obj = Path(csv_path)
            if not csv_path_obj.exists():
                raise FileNotFoundError(f"CSV file not found: {csv_path}")

            # Read existing CSV to get column names and count rows
            with open(csv_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                # Filter out comment lines
                reader = self._filter_comment_lines(csvfile)
                column_names = reader.fieldnames

                if not column_names:
                    raise ValueError("Could not read column names from CSV")

                # Count existing rows
                existing_row_count = sum(1 for _ in reader)

            # Append new rows
            with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=column_names)

                for row in new_rows:
                    # Ensure all columns are present
                    row_data = {col: row.get(col, '') for col in column_names}
                    writer.writerow(row_data)
                    result['rows_added'] += 1

            result['total_rows'] = existing_row_count + result['rows_added']
            result['success'] = True

            logger.info(
                f"Appended {result['rows_added']} row(s) to {csv_path}. "
                f"Total rows: {result['total_rows']}"
            )

        except Exception as e:
            error_msg = f"Error appending rows: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg

        return result

    def read_csv(self, csv_path: str) -> Dict[str, Any]:
        """
        Read CSV file and return structured data.

        Args:
            csv_path: Path to CSV file

        Returns:
            Dictionary with:
            {
                'success': bool,
                'columns': List[str],
                'rows': List[Dict],
                'row_count': int,
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'columns': [],
            'rows': [],
            'row_count': 0,
            'error': None
        }

        try:
            csv_path_obj = Path(csv_path)
            if not csv_path_obj.exists():
                raise FileNotFoundError(f"CSV file not found: {csv_path}")

            with open(csv_path, 'r', encoding='utf-8') as csvfile:
                # Skip comment lines
                lines = [line for line in csvfile if not line.startswith('#')]
                reader = csv.DictReader(lines)

                result['columns'] = list(reader.fieldnames or [])

                for row in reader:
                    result['rows'].append(dict(row))
                    result['row_count'] += 1

            result['success'] = True
            logger.info(f"Read CSV: {csv_path} ({result['row_count']} rows)")

        except Exception as e:
            error_msg = f"Error reading CSV: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg

        return result

    def validate_csv_structure(
        self,
        csv_path: str,
        expected_columns: List[str]
    ) -> Dict[str, Any]:
        """
        Validate that CSV has expected structure.

        Args:
            csv_path: Path to CSV file
            expected_columns: List of expected column names

        Returns:
            Dictionary with validation results:
            {
                'is_valid': bool,
                'missing_columns': List[str],
                'extra_columns': List[str],
                'error': Optional[str]
            }
        """
        result = {
            'is_valid': False,
            'missing_columns': [],
            'extra_columns': [],
            'error': None
        }

        try:
            csv_data = self.read_csv(csv_path)

            if not csv_data['success']:
                result['error'] = csv_data['error']
                return result

            actual_columns = set(csv_data['columns'])
            expected_columns_set = set(expected_columns)

            result['missing_columns'] = list(expected_columns_set - actual_columns)
            result['extra_columns'] = list(actual_columns - expected_columns_set)
            result['is_valid'] = len(result['missing_columns']) == 0

            if result['is_valid']:
                logger.info(f"CSV structure validation passed for {csv_path}")
            else:
                logger.warning(
                    f"CSV structure validation failed for {csv_path}. "
                    f"Missing: {result['missing_columns']}"
                )

        except Exception as e:
            error_msg = f"Error validating CSV structure: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg

        return result

    def _generate_metadata_comment(
        self,
        columns: List[Dict[str, Any]],
        rows: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Generate metadata comment lines for CSV header.

        Args:
            columns: Column definitions
            rows: Row data

        Returns:
            List of comment lines
        """
        lines = []
        lines.append(f"Generated: {datetime.utcnow().isoformat()}Z")
        lines.append(f"Columns: {len(columns)}")
        lines.append(f"Rows: {len(rows)}")
        lines.append("")
        lines.append("Column Definitions:")

        for col in columns:
            importance = col.get('importance', 'N/A')
            format_type = col.get('format', 'String')
            description = col.get('description', 'No description')
            is_id = col.get('is_identification', False)
            id_marker = " [ID]" if is_id else ""

            lines.append(
                f"  - {col['name']}{id_marker}: {description} "
                f"(Format: {format_type}, Importance: {importance})"
            )

        lines.append("")
        return lines

    def _filter_comment_lines(self, file_handle):
        """
        Filter out comment lines from CSV file.

        Args:
            file_handle: Open file handle

        Yields:
            Non-comment lines
        """
        for line in file_handle:
            if not line.startswith('#'):
                yield line

    def export_to_json(
        self,
        csv_path: str,
        json_path: str,
        columns: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Export CSV to JSON format with metadata.

        Args:
            csv_path: Path to CSV file
            json_path: Path for output JSON file
            columns: Optional column definitions to include in metadata

        Returns:
            Dictionary with operation results
        """
        import json

        result = {
            'success': False,
            'output_path': json_path,
            'error': None
        }

        try:
            # Read CSV data
            csv_data = self.read_csv(csv_path)
            if not csv_data['success']:
                result['error'] = csv_data['error']
                return result

            # Build JSON structure
            json_output = {
                'columns': columns if columns else [{'name': col} for col in csv_data['columns']],
                'rows': csv_data['rows'],
                'metadata': {
                    'created_at': datetime.utcnow().isoformat() + 'Z',
                    'row_count': csv_data['row_count'],
                    'column_count': len(csv_data['columns']),
                    'source_csv': str(csv_path)
                }
            }

            # Write JSON file
            json_path_obj = Path(json_path)
            json_path_obj.parent.mkdir(parents=True, exist_ok=True)

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_output, f, indent=2, ensure_ascii=False)

            result['success'] = True
            logger.info(f"Exported CSV to JSON: {json_path}")

        except Exception as e:
            error_msg = f"Error exporting to JSON: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg

        return result
