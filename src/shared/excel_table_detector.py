#!/usr/bin/env python3
"""
Excel Table Detector and Formula Preserver
Handles advanced Excel table detection, boundary identification, and formula preservation
"""

import logging
import re
from typing import List, Dict, Any, Tuple, Optional
from collections import Counter

logger = logging.getLogger(__name__)

class ExcelTableDetector:
    """
    Advanced Excel table detection with formula preservation.

    Features:
    - Detect table boundaries (end of data vs summary rows)
    - Identify multiple tables in the same sheet
    - Preserve formula references when rows are removed
    - Detect summary statistics rows (SUM, AVERAGE, etc.)
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Common summary formula patterns
        self.summary_formula_patterns = [
            r'=SUM\(',
            r'=AVERAGE\(',
            r'=AVG\(',
            r'=COUNT\(',
            r'=COUNTA\(',
            r'=MIN\(',
            r'=MAX\(',
            r'=MEDIAN\(',
            r'=SUBTOTAL\(',
            r'=AGGREGATE\('
        ]

        # Patterns that indicate data rows (not summary)
        self.data_patterns = [
            # Dates in various formats
            r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',
            r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',
            # IDs and codes
            r'^[A-Z]{2,}\d{3,}',
            r'^\d{6,}$',
            # URLs
            r'^https?://',
            # Email addresses
            r'@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        ]

    def detect_table_boundaries(
        self,
        worksheet,
        start_row: int = 0,
        headers: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Detect one or more tables in a worksheet, identifying their boundaries.

        Args:
            worksheet: openpyxl worksheet object
            start_row: Row index to start searching from
            headers: Optional list of known headers

        Returns:
            List of table definitions, each containing:
            {
                'start_row': int,
                'end_row': int,
                'headers': List[str],
                'has_summary': bool,
                'summary_start_row': int (if has_summary),
                'table_type': 'data' | 'summary' | 'pivot'
            }
        """
        tables = []
        current_row = start_row
        max_row = worksheet.max_row

        while current_row < max_row:
            # Skip empty rows
            if self._is_empty_row(worksheet, current_row):
                current_row += 1
                continue

            # Check if this looks like a table start
            if self._looks_like_table_start(worksheet, current_row):
                table_info = self._extract_table_info(worksheet, current_row, headers)
                if table_info:
                    tables.append(table_info)
                    # Move past this table
                    current_row = table_info['end_row'] + 1
                else:
                    current_row += 1
            else:
                current_row += 1

        return tables

    def _extract_table_info(
        self,
        worksheet,
        start_row: int,
        known_headers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Extract detailed information about a table starting at the given row.
        """
        # Get headers - handle both 0-based and 1-based indexing properly
        try:
            headers_row = list(worksheet[start_row + 1])
        except (IndexError, TypeError):
            return None

        # Extract headers with their column indices
        headers = []
        header_column_indices = []
        for i, cell in enumerate(headers_row):
            if cell and cell.value is not None and str(cell.value).strip():
                headers.append(cell.value)
                header_column_indices.append(i)

        if not headers or len(headers) < 2:
            return None

        # Find where the data ends
        data_end_row = start_row + 1
        summary_start_row = None
        consecutive_empty = 0

        for row_idx in range(start_row + 2, worksheet.max_row + 1):
            row = list(worksheet[row_idx])

            # Check if this is an empty row
            if self._is_empty_row_cells(row):
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    # Two consecutive empty rows likely mean end of table
                    break
                continue
            else:
                consecutive_empty = 0

            # Check if this is a summary row
            if self._is_summary_row(row, headers):
                summary_start_row = row_idx
                # The last data row is the row BEFORE the summary row
                data_end_row = row_idx - 1
                # Continue to find the actual end of summary section (for completeness)
                for sum_row_idx in range(row_idx + 1, min(row_idx + 10, worksheet.max_row + 1)):
                    sum_row = list(worksheet[sum_row_idx])
                    if self._is_empty_row_cells(sum_row):
                        break
                break

            # Check if this looks like the start of a new table
            if self._looks_like_new_table(row, headers):
                break

            # This is a data row
            data_end_row = row_idx

        return {
            'start_row': start_row + 1,  # Header row
            'end_row': data_end_row,
            'headers': headers,
            'header_column_indices': header_column_indices,  # Track which columns have headers
            'has_summary': summary_start_row is not None,
            'summary_start_row': summary_start_row,
            'table_type': self._determine_table_type(worksheet, start_row + 1, data_end_row)
        }

    def _is_summary_row(self, row_cells: List, headers: List[str]) -> bool:
        """
        Detect if a row contains summary statistics.

        Indicators:
        - Contains SUM, AVERAGE, or other aggregate formulas
        - Has significantly fewer filled cells than data rows
        - Contains keywords like "Total", "Summary", "Average"
        """
        # Check for summary keywords in first few cells - this is the strongest indicator
        for cell in row_cells[:4]:  # Check first 4 cells
            if cell.value:
                value_str = str(cell.value).strip().upper()
                if any(keyword in value_str for keyword in ['TOTAL', 'SUMMARY', 'AVERAGE', 'SUM', 'SUBTOTAL', 'GRAND TOTAL']):
                    self.logger.debug(f"Found summary keyword: {value_str}")
                    return True

        # Check if this row has ID values (data rows typically have IDs)
        has_id_value = False
        for i, cell in enumerate(row_cells[:4]):
            if cell.value:
                value_str = str(cell.value).strip()
                # Check if it looks like an ID (e.g., "001", "002", etc.)
                if re.match(r'^\d{3,}$', value_str) or re.match(r'^[A-Z]{1,3}\d{3,}$', value_str):
                    has_id_value = True
                    break

        # If row has ID values, it's likely a data row, not a summary
        if has_id_value:
            return False

        # Check for formulas that reference ranges (more sophisticated check)
        formula_count = 0
        range_formula_count = 0
        for cell in row_cells:
            if hasattr(cell, 'data_type') and cell.data_type == 'f':
                formula_str = str(cell.value) if cell.value else ""
                # Check if formula references a range of cells (e.g., A7:A11)
                if re.search(r'[A-Z]+\d+:[A-Z]+\d+', formula_str):
                    # Check if this is a vertical range (summary typically uses vertical ranges)
                    match = re.search(r'([A-Z]+)(\d+):([A-Z]+)(\d+)', formula_str)
                    if match:
                        col1, row1, col2, row2 = match.groups()
                        # Vertical range: same column, different rows, spanning multiple rows
                        if col1 == col2 and abs(int(row2) - int(row1)) > 2:
                            range_formula_count += 1

                if any(re.match(pattern, formula_str, re.IGNORECASE) for pattern in self.summary_formula_patterns):
                    formula_count += 1

        # Summary rows typically have formulas that reference vertical ranges
        non_empty = sum(1 for cell in row_cells if cell.value)
        if non_empty > 0 and range_formula_count > 0 and range_formula_count / non_empty > 0.2:
            self.logger.debug(f"Row has {range_formula_count}/{non_empty} range formulas (likely summary)")
            return True

        return False

    def _looks_like_new_table(self, row_cells: List, current_headers: List[str]) -> bool:
        """
        Detect if this row looks like the start of a new table.

        Indicators:
        - Has multiple text values that look like headers
        - Different structure than current table
        """
        # Count cells with text that could be headers
        potential_headers = 0
        for cell in row_cells:
            if cell.value and isinstance(cell.value, str):
                # Check if it looks like a header (title case, all caps, etc.)
                value = str(cell.value).strip()
                if len(value) > 2 and (value.istitle() or value.isupper()):
                    potential_headers += 1

        # If we have multiple potential headers and they're different from current
        if potential_headers >= len(current_headers) * 0.5:
            # Extract actual values
            new_headers = [cell.value for cell in row_cells if cell.value and isinstance(cell.value, str)]
            # Check if they're significantly different
            overlap = len(set(new_headers) & set(current_headers))
            if overlap < len(current_headers) * 0.3:
                return True

        return False

    def _determine_table_type(self, worksheet, start_row: int, end_row: int) -> str:
        """
        Determine the type of table based on its content.
        """
        # Check for pivot table characteristics
        first_row = list(worksheet[start_row + 1])

        # Pivot tables often have grouped/hierarchical first columns
        if self._has_hierarchical_structure(worksheet, start_row, end_row):
            return 'pivot'

        # Summary tables have mostly formulas
        formula_ratio = self._calculate_formula_ratio(worksheet, start_row, end_row)
        if formula_ratio > 0.5:
            return 'summary'

        return 'data'

    def _has_hierarchical_structure(self, worksheet, start_row: int, end_row: int) -> bool:
        """Check if table has hierarchical/grouped structure typical of pivot tables."""
        # Simple heuristic: check indentation patterns in first column
        first_col_values = []
        for row_idx in range(start_row + 1, min(start_row + 10, end_row + 1)):
            cell = worksheet.cell(row=row_idx, column=1)
            if cell.value:
                first_col_values.append(str(cell.value))

        # Check for indentation patterns (leading spaces)
        indented_count = sum(1 for val in first_col_values if val.startswith('  '))
        return indented_count > len(first_col_values) * 0.3

    def _calculate_formula_ratio(self, worksheet, start_row: int, end_row: int) -> float:
        """Calculate the ratio of formula cells to total non-empty cells."""
        formula_count = 0
        total_count = 0

        for row_idx in range(start_row, min(start_row + 20, end_row + 1)):
            for col_idx in range(1, worksheet.max_column + 1):
                cell = worksheet.cell(row=row_idx, column=col_idx)
                if cell.value:
                    total_count += 1
                    if hasattr(cell, 'data_type') and cell.data_type == 'f':
                        formula_count += 1

        return formula_count / total_count if total_count > 0 else 0

    def _is_empty_row(self, worksheet, row_idx: int) -> bool:
        """Check if a row is empty."""
        row = worksheet[row_idx + 1]  # openpyxl uses 1-based indexing
        return not any(cell.value for cell in row)

    def _is_empty_row_cells(self, row_cells: List) -> bool:
        """Check if a list of cells represents an empty row."""
        return not any(cell.value for cell in row_cells)

    def _looks_like_table_start(self, worksheet, row_idx: int) -> bool:
        """
        Check if this row looks like the start of a table (headers).
        """
        try:
            row = list(worksheet[row_idx + 1])
        except (IndexError, TypeError):
            return False

        # First priority: Check for ID columns - definitive headers
        has_id_column = False
        for cell in row:
            if cell and cell.value:
                value_str = str(cell.value).strip().upper()
                # Look for ID patterns in column names
                if any(pattern in value_str for pattern in ['_ID', ' ID', 'ID ',
                                                            'PRODUCT_ID', 'COMPANY_ID', 'CUSTOMER_ID',
                                                            'ITEM_ID', 'ORDER_ID', 'USER_ID']):
                    has_id_column = True
                    self.logger.debug(f"Found ID column '{value_str}' in row {row_idx + 1}")
                    break

        if has_id_column:
            # This is definitely a header row
            return True

        # Count non-empty cells that look like headers
        header_like_cells = 0
        total_non_empty = 0
        has_metadata_pattern = False

        for cell in row:
            if cell and cell.value:
                value_str = str(cell.value).strip()
                total_non_empty += 1

                # Check for metadata patterns that disqualify this as a header
                value_lower = value_str.lower()
                if any(meta in value_lower for meta in
                      ['generated', 'report', 'confidential', 'page', 'date:',
                       'department:', 'quarter:', 'version', 'internal use']):
                    has_metadata_pattern = True
                    self.logger.debug(f"Found metadata pattern in row {row_idx + 1}: {value_str}")

                # Check if it looks like a header (not a date, not pure numeric, has some text)
                if value_str and not self._is_numeric(value_str):
                    # Only count as header-like if no metadata patterns
                    if not has_metadata_pattern:
                        header_like_cells += 1

        # Reject rows with metadata patterns
        if has_metadata_pattern:
            return False

        # Need at least 2 header-like cells
        if header_like_cells < 2:
            return False

        # Check if next few rows have consistent data
        has_data_rows = False
        for check_idx in range(row_idx + 1, min(row_idx + 4, worksheet.max_row)):
            try:
                check_row = list(worksheet[check_idx + 1])
                # Count non-empty cells in potential data row
                data_cells = sum(1 for cell in check_row if cell and cell.value)
                # Should have similar structure to header row
                if data_cells >= min(2, total_non_empty * 0.5):
                    has_data_rows = True
                    break
            except:
                continue

        return has_data_rows

    def preserve_formulas_on_row_deletion(
        self,
        worksheet,
        rows_to_delete: List[int],
        table_boundaries: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Properly delete rows while preserving formula references.

        This uses openpyxl's delete_rows method which automatically
        adjusts formula references.

        Args:
            worksheet: openpyxl worksheet object
            rows_to_delete: List of row indices to delete (0-based)
            table_boundaries: Optional table boundary information

        Returns:
            Information about the deletion and adjustments made
        """
        if not rows_to_delete:
            return {'deleted_count': 0, 'adjusted_formulas': 0}

        # Convert to 1-based indexing for openpyxl and sort in reverse
        # Delete from bottom to top to maintain row indices
        rows_to_delete_1based = sorted([r + 1 for r in rows_to_delete], reverse=True)

        adjusted_formulas = 0

        # Track formulas before deletion
        formula_cells = []
        for row in worksheet.iter_rows():
            for cell in row:
                if hasattr(cell, 'data_type') and cell.data_type == 'f':
                    formula_cells.append({
                        'row': cell.row,
                        'col': cell.column,
                        'formula': cell.value
                    })

        # Delete rows one by one from bottom to top
        for row_num in rows_to_delete_1based:
            try:
                # Openpyxl's delete_rows automatically adjusts formulas
                worksheet.delete_rows(row_num, 1)
                self.logger.debug(f"Deleted row {row_num}")
            except Exception as e:
                self.logger.warning(f"Failed to delete row {row_num}: {e}")

        # Count adjusted formulas
        for row in worksheet.iter_rows():
            for cell in row:
                if hasattr(cell, 'data_type') and cell.data_type == 'f':
                    # Check if this formula references adjusted rows
                    formula_str = str(cell.value) if cell.value else ""
                    if re.search(r'[A-Z]+\d+', formula_str):
                        adjusted_formulas += 1

        return {
            'deleted_count': len(rows_to_delete),
            'adjusted_formulas': adjusted_formulas,
            'method': 'openpyxl_delete_rows'
        }

    def preserve_formulas_on_column_deletion(
        self,
        worksheet,
        columns_to_delete: List[int]
    ) -> Dict[str, Any]:
        """
        Properly delete columns while preserving formula references.

        This uses openpyxl's delete_cols method which automatically
        adjusts formula references. When a column is deleted, formulas
        that reference columns to the right of it are automatically
        adjusted to reference the correct data.

        Args:
            worksheet: openpyxl worksheet object
            columns_to_delete: List of column indices to delete (0-based)

        Returns:
            Information about the deletion and adjustments made
        """
        if not columns_to_delete:
            return {'deleted_count': 0, 'adjusted_formulas': 0}

        # Convert to 1-based indexing for openpyxl and sort in reverse
        # Delete from right to left to maintain column indices
        cols_to_delete_1based = sorted([c + 1 for c in columns_to_delete], reverse=True)

        adjusted_formulas = 0

        # Track formulas before deletion
        formula_cells = []
        for row in worksheet.iter_rows():
            for cell in row:
                if hasattr(cell, 'data_type') and cell.data_type == 'f':
                    formula_cells.append({
                        'row': cell.row,
                        'col': cell.column,
                        'formula': cell.value
                    })

        # Delete columns one by one from right to left
        for col_num in cols_to_delete_1based:
            try:
                # Openpyxl's delete_cols automatically adjusts formulas
                worksheet.delete_cols(col_num, 1)
                self.logger.debug(f"Deleted column {col_num}")
            except Exception as e:
                self.logger.warning(f"Failed to delete column {col_num}: {e}")

        # Count adjusted formulas
        for row in worksheet.iter_rows():
            for cell in row:
                if hasattr(cell, 'data_type') and cell.data_type == 'f':
                    # Check if this formula references columns
                    formula_str = str(cell.value) if cell.value else ""
                    if re.search(r'[A-Z]+\d+', formula_str):
                        adjusted_formulas += 1

        return {
            'deleted_count': len(columns_to_delete),
            'adjusted_formulas': adjusted_formulas,
            'method': 'openpyxl_delete_cols'
        }

    def filter_data_rows(
        self,
        all_rows: List[Any],
        headers: List[str],
        preserve_summary: bool = False
    ) -> Tuple[List[Any], Dict[str, Any]]:
        """
        Filter data rows to remove only empty rows and detect summary rows.
        NOTE: After headers are found, we should NOT filter sparse data rows.

        Args:
            all_rows: All rows including headers
            headers: Header row
            preserve_summary: Whether to preserve summary rows

        Returns:
            Tuple of (filtered_data_rows, metadata_about_filtering)
        """
        filtered_rows = []
        metadata = {
            'removed_empty': 0,
            'removed_sparse': 0,
            'removed_metadata': 0,
            'summary_rows_found': 0,
            'data_end_row': None
        }

        for row_idx, row in enumerate(all_rows):
            # Skip header row (assumed to be first)
            if row_idx == 0:
                continue

            # Count non-empty cells
            if hasattr(row, '__iter__'):
                non_empty_count = sum(1 for cell in row if cell and str(cell).strip())
            else:
                # Handle openpyxl row objects
                non_empty_count = sum(1 for cell in row if cell.value and str(cell.value).strip())

            # Skip only completely empty rows
            if non_empty_count == 0:
                metadata['removed_empty'] += 1
                continue

            # After headers are found, keep ALL non-empty data rows (even sparse ones)
            # Only check for summary rows if requested
            if preserve_summary and self._is_summary_row_simple(row):
                metadata['summary_rows_found'] += 1
                metadata['data_end_row'] = len(filtered_rows)  # Mark where data ends

            # Keep the row - we don't filter sparse data rows after headers are found
            filtered_rows.append(row)

        return filtered_rows, metadata

    def _looks_like_metadata_row(self, row: Any, headers: List[str]) -> bool:
        """Check if a row looks like metadata rather than data."""
        # Get first few cell values
        values = []
        if hasattr(row, '__iter__'):
            values = [str(cell).strip() if cell else "" for cell in row[:3]]
        else:
            # Handle openpyxl rows
            for cell in row[:3]:
                values.append(str(cell.value).strip() if cell.value else "")

        # Check for metadata patterns
        metadata_keywords = ['generated', 'created', 'updated', 'report', 'date:', 'time:',
                            'page', 'of', 'confidential', 'proprietary']

        for value in values:
            value_lower = value.lower()
            if any(keyword in value_lower for keyword in metadata_keywords):
                return True

        return False

    def _looks_like_data_row(self, row: Any) -> bool:
        """Check if a row looks like actual data."""
        # Get all non-empty values
        values = []
        if hasattr(row, '__iter__'):
            values = [str(cell).strip() for cell in row if cell and str(cell).strip()]
        else:
            # Handle openpyxl rows
            for cell in row:
                if cell.value:
                    values.append(str(cell.value).strip())

        # Check for data patterns
        for value in values:
            for pattern in self.data_patterns:
                if re.search(pattern, value):
                    return True

        # If it has multiple values and they're not all text, probably data
        if len(values) >= 2:
            has_numbers = any(self._is_numeric(v) for v in values)
            has_text = any(not self._is_numeric(v) for v in values)
            return has_numbers or len(values) >= 3

        return False

    def _is_summary_row_simple(self, row: Any) -> bool:
        """Simple check if a row is a summary row."""
        # Get first few values
        values = []
        if hasattr(row, '__iter__'):
            values = [str(cell).strip().upper() if cell else "" for cell in row[:3]]
        else:
            # Handle openpyxl rows
            for cell in row[:3]:
                if cell.value:
                    values.append(str(cell.value).strip().upper())

        # Check for summary keywords
        summary_keywords = ['TOTAL', 'SUMMARY', 'AVERAGE', 'SUM', 'SUBTOTAL', 'GRAND TOTAL']
        return any(keyword in value for keyword in summary_keywords for value in values)

    def _is_numeric(self, value: str) -> bool:
        """Check if a string value is numeric."""
        try:
            float(value.replace(',', '').replace('$', '').replace('%', ''))
            return True
        except (ValueError, AttributeError):
            return False

    def detect_empty_columns(
        self,
        worksheet,
        start_row: int = 1,
        end_row: Optional[int] = None,
        sample_size: int = 100
    ) -> List[int]:
        """
        Detect columns that are completely empty or have negligible data.

        Args:
            worksheet: openpyxl worksheet object
            start_row: Row to start checking from (1-based)
            end_row: Row to stop checking at (1-based), None for all rows
            sample_size: Max rows to sample for large sheets

        Returns:
            List of column indices (1-based) that are empty
        """
        if end_row is None:
            end_row = min(worksheet.max_row, start_row + sample_size)

        empty_columns = []
        max_col = worksheet.max_column

        for col_idx in range(1, max_col + 1):
            # Check if column has any non-empty cells
            has_data = False
            for row_idx in range(start_row, min(end_row + 1, worksheet.max_row + 1)):
                cell = worksheet.cell(row=row_idx, column=col_idx)
                if cell.value is not None and str(cell.value).strip():
                    has_data = True
                    break

            if not has_data:
                empty_columns.append(col_idx)
                self.logger.debug(f"Column {col_idx} is empty")

        return empty_columns

    def remove_empty_columns(
        self,
        data_rows: List[List[Any]],
        headers: List[str],
        threshold: float = 0.95
    ) -> Tuple[List[List[Any]], List[str], List[int]]:
        """
        Remove columns that are mostly empty from data.

        Args:
            data_rows: List of data rows
            headers: List of header names
            threshold: Percentage of empty cells to consider column empty (0.95 = 95%)

        Returns:
            Tuple of (filtered_data_rows, filtered_headers, removed_column_indices)
        """
        if not data_rows or not headers:
            return data_rows, headers, []

        # Count empty cells per column
        num_cols = len(headers)
        num_rows = len(data_rows)
        empty_counts = [0] * num_cols

        for row in data_rows:
            for col_idx in range(min(len(row), num_cols)):
                if col_idx < len(row):
                    value = row[col_idx]
                    if value is None or str(value).strip() == '':
                        empty_counts[col_idx] += 1
                else:
                    empty_counts[col_idx] += 1

        # Identify columns to remove
        columns_to_remove = []
        for col_idx, empty_count in enumerate(empty_counts):
            empty_ratio = empty_count / num_rows if num_rows > 0 else 1.0
            if empty_ratio >= threshold:
                columns_to_remove.append(col_idx)
                self.logger.debug(
                    f"Removing column {col_idx} ({headers[col_idx]}): "
                    f"{empty_ratio:.1%} empty"
                )

        # Filter data and headers
        if columns_to_remove:
            # Create filtered headers
            filtered_headers = [
                headers[i] for i in range(len(headers))
                if i not in columns_to_remove
            ]

            # Filter each data row
            filtered_data = []
            for row in data_rows:
                filtered_row = [
                    row[i] if i < len(row) else ''
                    for i in range(len(headers))
                    if i not in columns_to_remove
                ]
                filtered_data.append(filtered_row)

            self.logger.info(
                f"Removed {len(columns_to_remove)} empty columns, "
                f"keeping {len(filtered_headers)} columns"
            )
            return filtered_data, filtered_headers, columns_to_remove

        return data_rows, headers, []

    def clean_table_data(
        self,
        worksheet,
        remove_empty_rows: bool = True,
        remove_empty_columns: bool = True,
        remove_summary: bool = True,
        preserve_formulas: bool = True
    ) -> Dict[str, Any]:
        """
        Comprehensive table cleaning that handles rows and columns.

        Args:
            worksheet: openpyxl worksheet object
            remove_empty_rows: Whether to remove empty/sparse rows
            remove_empty_columns: Whether to remove empty columns
            remove_summary: Whether to remove summary statistics rows
            preserve_formulas: Whether to preserve Excel formulas

        Returns:
            Dictionary with cleaned data and metadata about changes
        """
        result = {
            'success': False,
            'data': [],
            'headers': [],
            'metadata': {
                'original_shape': None,
                'final_shape': None,
                'removed_rows': 0,
                'removed_columns': 0,
                'summary_rows_found': 0
            }
        }

        try:
            # Detect table boundaries
            tables = self.detect_table_boundaries(worksheet)
            if not tables:
                raise ValueError("No tables found in worksheet")

            # Use first data table
            table_info = None
            for table in tables:
                if table['table_type'] == 'data':
                    table_info = table
                    break
            if not table_info:
                table_info = tables[0]

            # Get all data
            all_rows = list(worksheet.iter_rows(values_only=True))
            headers = table_info['headers']
            data_rows = all_rows[table_info['start_row']:table_info['end_row']]

            result['metadata']['original_shape'] = (len(data_rows), len(headers))

            # Remove empty/sparse rows if requested
            if remove_empty_rows:
                data_rows, filter_meta = self.filter_data_rows(
                    data_rows, headers, preserve_summary=(not remove_summary)
                )
                result['metadata']['removed_rows'] = (
                    filter_meta['removed_empty'] +
                    filter_meta['removed_sparse'] +
                    filter_meta['removed_metadata']
                )
                result['metadata']['summary_rows_found'] = filter_meta['summary_rows_found']

            # Remove empty columns if requested
            if remove_empty_columns:
                data_rows, headers, removed_cols = self.remove_empty_columns(
                    data_rows, headers, threshold=0.95
                )
                result['metadata']['removed_columns'] = len(removed_cols)

            # Store cleaned data
            result['data'] = data_rows
            result['headers'] = headers
            result['metadata']['final_shape'] = (len(data_rows), len(headers))
            result['success'] = True

            self.logger.info(
                f"Table cleaning complete: "
                f"{result['metadata']['original_shape']} -> {result['metadata']['final_shape']}"
            )

        except Exception as e:
            self.logger.error(f"Table cleaning failed: {str(e)}")
            result['error'] = str(e)

        return result