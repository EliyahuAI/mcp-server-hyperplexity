#!/usr/bin/env python3
"""
Table Cleaning Logger
Tracks all cleaning operations for restoration and debugging purposes
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class TableCleaningLogger:
    """
    Logs all table cleaning operations with enough detail to restore original structure.

    The log captures:
    - Original file metadata
    - Header detection details
    - Rows removed (with content and reasons)
    - Columns removed (with positions and reasons)
    - Sparse row handling
    - Formula adjustments
    - Summary row detection
    """

    def __init__(self, output_dir: str = "results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        self.cleaning_log = {
            'timestamp': datetime.now().isoformat(),
            'version': '1.0',
            'operations': [],
            'summary': {},
            'restoration_info': {}
        }
        self.current_file = None

    def start_file_cleaning(self, filename: str, file_type: str, original_shape: tuple,
                          sheet_name: str = None):
        """Start logging cleaning operations for a new file."""
        self.current_file = filename
        self.cleaning_log['file_info'] = {
            'original_filename': filename,
            'file_type': file_type,
            'original_shape': {
                'rows': original_shape[0],
                'columns': original_shape[1]
            },
            'sheet_name': sheet_name,
            'sheets_available': [],  # Will be populated for Excel files
            'cleaning_started': datetime.now().isoformat()
        }
        self.logger.info(f"Starting cleaning log for {filename}" +
                        (f" (sheet: {sheet_name})" if sheet_name else ""))

    def set_available_sheets(self, sheet_names: List[str]):
        """Set the list of available sheets in the Excel file."""
        if 'file_info' in self.cleaning_log:
            self.cleaning_log['file_info']['sheets_available'] = sheet_names
            self.logger.debug(f"Available sheets: {sheet_names}")

    def log_header_detection(self, method: str, header_row: int, headers: List[str],
                           metadata_rows: List[Dict[str, Any]] = None,
                           id_columns_found: List[str] = None):
        """Log header detection details."""
        operation = {
            'type': 'header_detection',
            'timestamp': datetime.now().isoformat(),
            'details': {
                'detection_method': method,  # 'id_column', 'pattern', 'fallback'
                'header_row_index': header_row,
                'headers_found': headers,
                'id_columns': id_columns_found or [],
                'metadata_rows_skipped': len(metadata_rows) if metadata_rows else 0
            }
        }

        if metadata_rows:
            operation['details']['metadata_rows'] = metadata_rows

        self.cleaning_log['operations'].append(operation)
        self.logger.info(f"Headers detected at row {header_row} using {method}")

    def log_row_removal(self, row_indices: List[int], rows_content: List[List[Any]],
                       removal_reason: str, row_type: str = 'data'):
        """
        Log row removal with content for restoration.

        Args:
            row_indices: 0-based indices of removed rows
            rows_content: Actual content of removed rows
            removal_reason: Why rows were removed
            row_type: 'metadata', 'empty', 'sparse', 'summary'
        """
        operation = {
            'type': 'row_removal',
            'timestamp': datetime.now().isoformat(),
            'details': {
                'row_type': row_type,
                'removal_reason': removal_reason,
                'rows_removed': []
            }
        }

        for idx, content in zip(row_indices, rows_content):
            row_info = {
                'original_index': idx,
                'content': content if isinstance(content, list) else list(content),
                'non_empty_cells': sum(1 for cell in content if cell and str(cell).strip()),
                'fill_percentage': 0
            }

            if len(content) > 0:
                row_info['fill_percentage'] = (row_info['non_empty_cells'] / len(content)) * 100

            operation['details']['rows_removed'].append(row_info)

        operation['details']['total_removed'] = len(row_indices)
        self.cleaning_log['operations'].append(operation)
        self.logger.info(f"Removed {len(row_indices)} {row_type} rows: {removal_reason}")

    def log_column_removal(self, column_indices: List[int], column_headers: List[str],
                          removal_reason: str):
        """
        Log column removal with headers for restoration.

        Args:
            column_indices: 0-based indices of removed columns
            column_headers: Headers of removed columns (if any)
            removal_reason: Why columns were removed
        """
        operation = {
            'type': 'column_removal',
            'timestamp': datetime.now().isoformat(),
            'details': {
                'removal_reason': removal_reason,
                'columns_removed': []
            }
        }

        for idx, header in zip(column_indices, column_headers):
            col_info = {
                'original_index': idx,
                'header': header if header else f"Column_{idx+1}",
                'was_empty_header': not bool(header)
            }
            operation['details']['columns_removed'].append(col_info)

        operation['details']['total_removed'] = len(column_indices)
        self.cleaning_log['operations'].append(operation)
        self.logger.info(f"Removed {len(column_indices)} columns: {removal_reason}")

    def log_sparse_row_handling(self, row_index: int, row_content: List[Any],
                              action: str, fill_percentage: float):
        """
        Log how sparse rows were handled.

        Args:
            row_index: 0-based index
            row_content: Row data
            action: 'kept' or 'removed'
            fill_percentage: Percentage of non-empty cells
        """
        operation = {
            'type': 'sparse_row_handling',
            'timestamp': datetime.now().isoformat(),
            'details': {
                'row_index': row_index,
                'action': action,
                'fill_percentage': fill_percentage,
                'non_empty_cells': sum(1 for cell in row_content if cell and str(cell).strip()),
                'total_cells': len(row_content)
            }
        }

        if action == 'removed':
            operation['details']['content'] = list(row_content)

        self.cleaning_log['operations'].append(operation)

    def log_formula_adjustment(self, formula_type: str, affected_cells: List[Dict[str, Any]]):
        """
        Log formula adjustments due to row/column deletion.

        Args:
            formula_type: 'row_deletion' or 'column_deletion'
            affected_cells: List of dicts with cell info and formula changes
        """
        operation = {
            'type': 'formula_adjustment',
            'timestamp': datetime.now().isoformat(),
            'details': {
                'adjustment_type': formula_type,
                'affected_cells': affected_cells,
                'total_adjusted': len(affected_cells)
            }
        }

        self.cleaning_log['operations'].append(operation)
        self.logger.info(f"Adjusted {len(affected_cells)} formulas due to {formula_type}")

    def log_summary_row_detection(self, row_indices: List[int], summary_type: str = 'total'):
        """Log detection of summary rows."""
        operation = {
            'type': 'summary_row_detection',
            'timestamp': datetime.now().isoformat(),
            'details': {
                'summary_type': summary_type,
                'row_indices': row_indices,
                'count': len(row_indices)
            }
        }

        self.cleaning_log['operations'].append(operation)
        self.logger.info(f"Detected {len(row_indices)} {summary_type} summary rows")

    def finalize_cleaning(self, final_shape: tuple, cleaning_stats: Dict[str, Any] = None):
        """Finalize the cleaning log with summary statistics."""
        self.cleaning_log['file_info']['final_shape'] = {
            'rows': final_shape[0],
            'columns': final_shape[1]
        }
        self.cleaning_log['file_info']['cleaning_completed'] = datetime.now().isoformat()

        # Calculate summary statistics
        summary = {
            'rows_removed': 0,
            'columns_removed': 0,
            'metadata_rows_removed': 0,
            'empty_rows_removed': 0,
            'sparse_rows_removed': 0,
            'summary_rows_detected': 0,
            'formulas_adjusted': 0
        }

        for op in self.cleaning_log['operations']:
            if op['type'] == 'row_removal':
                summary['rows_removed'] += op['details']['total_removed']
                if op['details']['row_type'] == 'metadata':
                    summary['metadata_rows_removed'] += op['details']['total_removed']
                elif op['details']['row_type'] == 'empty':
                    summary['empty_rows_removed'] += op['details']['total_removed']
                elif op['details']['row_type'] == 'sparse':
                    summary['sparse_rows_removed'] += op['details']['total_removed']
            elif op['type'] == 'column_removal':
                summary['columns_removed'] += op['details']['total_removed']
            elif op['type'] == 'summary_row_detection':
                summary['summary_rows_detected'] += op['details']['count']
            elif op['type'] == 'formula_adjustment':
                summary['formulas_adjusted'] += op['details']['total_adjusted']

        if cleaning_stats:
            summary.update(cleaning_stats)

        self.cleaning_log['summary'] = summary

        # Add restoration information
        self.cleaning_log['restoration_info'] = {
            'can_restore': True,
            'instructions': 'Use the operation log to reverse operations in reverse order',
            'removed_content_preserved': True,
            'original_indices_preserved': True
        }

        self.logger.info(f"Cleaning complete: {summary}")

    def save_log(self, log_filename: str = None) -> str:
        """
        Save the cleaning log to a JSON file.

        Args:
            log_filename: Optional custom filename

        Returns:
            Path to saved log file
        """
        if not log_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = Path(self.current_file).stem if self.current_file else "table"
            log_filename = f"{base_name}_cleaning_log_{timestamp}.json"

        log_path = self.output_dir / log_filename

        with open(log_path, 'w') as f:
            json.dump(self.cleaning_log, f, indent=2, default=str)

        self.logger.info(f"Cleaning log saved to {log_path}")
        return str(log_path)

    def save_original_and_cleaned(self, original_content: bytes, cleaned_content: bytes,
                                 base_filename: str, save_original_copy: bool = True) -> Dict[str, str]:
        """
        Save both original and cleaned versions of the file.
        The cleaned version becomes the primary file in the results folder.

        Args:
            original_content: Original file content
            cleaned_content: Cleaned file content
            base_filename: Base name for the files
            save_original_copy: Whether to save a copy of the original (default: True)

        Returns:
            Dictionary with paths to saved files
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = Path(base_filename).stem
        extension = Path(base_filename).suffix

        # Save cleaned version as the primary file in results folder
        # This becomes the main file that will be used
        cleaned_filename = f"{base_name}{extension}"
        cleaned_path = self.output_dir / cleaned_filename
        with open(cleaned_path, 'wb') as f:
            f.write(cleaned_content)

        saved_files = {
            'cleaned': str(cleaned_path),
            'cleaned_primary': str(cleaned_path)  # This is the main file
        }

        # Optionally save original with timestamp for reference
        if save_original_copy:
            original_filename = f"{base_name}_original_{timestamp}{extension}"
            original_path = self.output_dir / "originals" / original_filename
            original_path.parent.mkdir(parents=True, exist_ok=True)
            with open(original_path, 'wb') as f:
                f.write(original_content)
            saved_files['original'] = str(original_path)
            self.logger.info(f"Saved original copy to {original_path}")

        # Also save a timestamped focused version for history
        focused_filename = f"{base_name}_focused_{timestamp}{extension}"
        focused_path = self.output_dir / "history" / focused_filename
        focused_path.parent.mkdir(parents=True, exist_ok=True)
        with open(focused_path, 'wb') as f:
            f.write(cleaned_content)
        saved_files['focused_timestamped'] = str(focused_path)

        # Update log with file paths
        self.cleaning_log['file_info']['saved_files'] = saved_files
        self.cleaning_log['file_info']['primary_cleaned_file'] = str(cleaned_path)

        self.logger.info(f"Saved cleaned version as primary file: {cleaned_path}")
        self.logger.info(f"Saved timestamped focused version to {focused_path}")

        return saved_files

    def get_restoration_script(self) -> str:
        """
        Generate a Python script that can restore the original from cleaned version.

        Returns:
            Python code as string that can restore the original structure
        """
        script = f"""#!/usr/bin/env python3
# Auto-generated restoration script for {self.current_file}
# Generated: {datetime.now().isoformat()}

import pandas as pd
import json

def restore_original(cleaned_file, log_file):
    '''Restore original structure from cleaned file using cleaning log.'''

    # Load cleaning log
    with open(log_file, 'r') as f:
        log = json.load(f)

    # Load cleaned data
    if cleaned_file.endswith('.csv'):
        df = pd.read_csv(cleaned_file)
    else:
        df = pd.read_excel(cleaned_file)

    # Process operations in reverse order
    for operation in reversed(log['operations']):
        if operation['type'] == 'row_removal':
            # Restore removed rows
            for row_info in operation['details']['rows_removed']:
                idx = row_info['original_index']
                content = row_info['content']
                # Insert row at original position
                df = pd.concat([df.iloc[:idx],
                              pd.DataFrame([content], columns=df.columns),
                              df.iloc[idx:]]).reset_index(drop=True)

        elif operation['type'] == 'column_removal':
            # Restore removed columns
            for col_info in operation['details']['columns_removed']:
                idx = col_info['original_index']
                header = col_info['header']
                # Insert empty column at original position
                df.insert(idx, header, '')

    return df

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        print("Usage: restore.py <cleaned_file> <log_file>")
        sys.exit(1)

    restored = restore_original(sys.argv[1], sys.argv[2])
    restored.to_csv('restored.csv', index=False)
    print("Restored file saved as 'restored.csv'")
"""
        return script

    def get_summary_report(self) -> str:
        """Generate a human-readable summary report of cleaning operations."""
        if not self.cleaning_log.get('summary'):
            return "No cleaning operations logged yet."

        summary = self.cleaning_log['summary']
        file_info = self.cleaning_log.get('file_info', {})

        report = f"""
Table Cleaning Report
{'=' * 50}
File: {file_info.get('original_filename', 'Unknown')}
Timestamp: {self.cleaning_log['timestamp']}

Original Shape: {file_info.get('original_shape', {}).get('rows', 0)} rows × {file_info.get('original_shape', {}).get('columns', 0)} columns
Final Shape: {file_info.get('final_shape', {}).get('rows', 0)} rows × {file_info.get('final_shape', {}).get('columns', 0)} columns

Operations Summary:
- Rows Removed: {summary.get('rows_removed', 0)}
  - Metadata: {summary.get('metadata_rows_removed', 0)}
  - Empty: {summary.get('empty_rows_removed', 0)}
  - Sparse: {summary.get('sparse_rows_removed', 0)}
- Columns Removed: {summary.get('columns_removed', 0)}
- Summary Rows Detected: {summary.get('summary_rows_detected', 0)}
- Formulas Adjusted: {summary.get('formulas_adjusted', 0)}

Saved Files:
- Original: {file_info.get('saved_files', {}).get('original', 'Not saved')}
- Cleaned: {file_info.get('saved_files', {}).get('cleaned', 'Not saved')}
- Log: {file_info.get('saved_files', {}).get('log', 'Not saved')}
{'=' * 50}
"""
        return report