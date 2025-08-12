#!/usr/bin/env python3
"""
Consolidated S3 Table Parser
Unified parser for CSV/Excel files from S3 used by both interface and validation code
"""

import boto3
import csv
import json
import logging
import os
import tempfile
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Try to import openpyxl
try:
    from openpyxl import load_workbook
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    logger.warning("openpyxl not available - Excel files won't be supported")

class S3TableParser:
    """Unified S3 table-to-JSON parser used by both interface and validation code"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.logger = logging.getLogger(__name__)
    
    def parse_s3_table(self, bucket: str, key: str, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Parse Excel/CSV from S3 into standard JSON format
        
        Args:
            bucket: S3 bucket name
            key: S3 object key
            sheet_name: Excel sheet name (optional, uses first sheet if not specified)
            
        Returns:
            Structured table data with metadata
        """
        try:
            # Download file from S3
            self.logger.info(f"Downloading table from S3: s3://{bucket}/{key}")
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            file_content = response['Body'].read()
            
            # Determine file type from key
            filename = key.split('/')[-1]
            if filename.endswith('.csv'):
                return self._parse_csv_content(file_content, filename)
            elif filename.endswith(('.xlsx', '.xls')):
                if not OPENPYXL_AVAILABLE:
                    raise ImportError("openpyxl is required for Excel file support")
                return self._parse_excel_content(file_content, filename, sheet_name)
            else:
                raise ValueError(f"Unsupported file format: {filename}")
                
        except Exception as e:
            self.logger.error(f"Failed to parse S3 table {bucket}/{key}: {str(e)}")
            raise
    
    def _parse_csv_content(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """Parse CSV content into structured format"""
        try:
            # Try multiple encodings to handle different CSV file encodings (expanded list)
            encodings_to_try = [
                'utf-8', 'utf-8-sig',  # UTF-8 with and without BOM
                'latin-1', 'cp1252', 'iso-8859-1',  # Windows/Western European
                'utf-16', 'utf-16le', 'utf-16be',  # UTF-16 variants
                'cp437', 'cp850',  # DOS/OEM encodings
                'ascii'  # Basic ASCII as last resort
            ]
            text_content = None
            used_encoding = None
            
            for encoding in encodings_to_try:
                try:
                    text_content = file_content.decode(encoding)
                    used_encoding = encoding
                    break
                except UnicodeDecodeError:
                    continue
            
            if text_content is None:
                raise ValueError(f"Could not decode CSV file with any of the tried encodings: {encodings_to_try}")
                
            print(f"Successfully decoded CSV using {used_encoding} encoding")
            
            # Parse CSV with standard method first
            try:
                reader = csv.reader(text_content.splitlines())
                rows = list(reader)
                
                if not rows:
                    raise ValueError("Empty CSV file")
                    
                # Quick validation - check if we got reasonable parsing
                if not self._is_valid_csv_parse(rows):
                    raise ValueError("Standard CSV parsing produced poor results, trying fallback")
                    
            except (csv.Error, ValueError) as e:
                self.logger.warning(f"Standard CSV parsing failed: {e}, trying robust fallback")
                # Fallback to robust parsing with delimiter detection
                rows = self._parse_csv_with_robust_fallback(text_content)
            
            # Find actual table start with robust detection
            table_start_row, headers = self._find_table_start_csv(rows)
            data_rows = rows[table_start_row + 1:]
            
            # Clean data rows
            data_rows = self._clean_data_rows_csv(data_rows, len(headers))
            
            # Clean headers
            clean_headers = [str(header).strip() if header else f"Column_{i+1}" 
                           for i, header in enumerate(headers)]
            
            # Convert to structured format
            structured_data = []
            for row in data_rows:
                if any(cell.strip() for cell in row):  # Skip empty rows
                    row_dict = {}
                    for i, header in enumerate(clean_headers):
                        cell_value = row[i] if i < len(row) else ""
                        row_dict[header] = str(cell_value).strip() if cell_value else ""
                    structured_data.append(row_dict)
            
            return {
                'filename': filename,
                'total_rows': len(structured_data),
                'total_columns': len(clean_headers),
                'column_names': clean_headers,
                'data': structured_data,
                'metadata': {
                    'file_type': 'csv',
                    'source': 's3',
                    'sample_rows': min(5, len(structured_data))
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed to parse CSV content: {str(e)}")
            raise
    
    def _parse_excel_content(self, file_content: bytes, filename: str, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """Parse Excel content into structured format"""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
            
            try:
                # Load workbook
                workbook = load_workbook(temp_file_path, read_only=True)
                
                # Select worksheet
                if sheet_name:
                    if sheet_name not in workbook.sheetnames:
                        raise ValueError(f"Sheet '{sheet_name}' not found. Available sheets: {workbook.sheetnames}")
                    worksheet = workbook[sheet_name]
                else:
                    # Default behavior: try "Results" sheet first, then fall back to first sheet
                    if "Results" in workbook.sheetnames:
                        worksheet = workbook["Results"]
                        sheet_name = "Results"
                        print(f"Using 'Results' sheet by default")
                    else:
                        # Use first sheet (workbook.active might not be the first sheet)
                        worksheet = workbook[workbook.sheetnames[0]]
                        sheet_name = workbook.sheetnames[0]
                        print(f"No 'Results' sheet found, using first sheet: '{sheet_name}'")
                
                # Read data with robust table detection
                all_rows = list(worksheet.iter_rows(values_only=True))
                
                if not all_rows:
                    raise ValueError("Empty Excel worksheet")
                
                # Find actual table start (skip empty rows and detect headers)
                table_start_row, headers = self._find_table_start(all_rows)
                data_rows = all_rows[table_start_row + 1:]
                
                # Clean data rows (remove empty trailing rows and trim columns)
                data_rows = self._clean_data_rows(data_rows, len(headers))
                
                # Clean headers
                clean_headers = [str(header).strip() if header is not None else f"Column_{i+1}" 
                               for i, header in enumerate(headers)]
                
                # Convert to structured format
                structured_data = []
                for row in data_rows:
                    if row and any(cell is not None for cell in row):  # Skip empty rows
                        row_dict = {}
                        for i, header in enumerate(clean_headers):
                            cell_value = row[i] if i < len(row) else None
                            row_dict[header] = str(cell_value).strip() if cell_value is not None else ""
                        structured_data.append(row_dict)
                
                workbook.close()
                
                return {
                    'filename': filename,
                    'total_rows': len(structured_data),
                    'total_columns': len(clean_headers),
                    'column_names': clean_headers,
                    'data': structured_data,
                    'metadata': {
                        'file_type': 'excel',
                        'sheet_name': sheet_name,
                        'source': 's3',
                        'sample_rows': min(5, len(structured_data))
                    }
                }
                
            finally:
                # Clean up temp file
                os.unlink(temp_file_path)
                
        except Exception as e:
            self.logger.error(f"Failed to parse Excel content: {str(e)}")
            raise
    
    def get_table_sample(self, bucket: str, key: str, max_rows: int = 10) -> Dict[str, Any]:
        """Get a sample of the table data without loading the entire file"""
        try:
            full_data = self.parse_s3_table(bucket, key)
            
            # Return sample
            sample_data = full_data['data'][:max_rows]
            
            return {
                'filename': full_data['filename'],
                'total_rows': full_data['total_rows'],
                'total_columns': full_data['total_columns'],
                'column_names': full_data['column_names'],
                'sample_data': sample_data,
                'metadata': full_data['metadata']
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get table sample: {str(e)}")
            raise
    
    def analyze_table_structure(self, bucket: str, key: str) -> Dict[str, Any]:
        """Analyze table structure for AI config generation"""
        try:
            # Get sample data
            sample = self.get_table_sample(bucket, key, max_rows=20)
            
            # Analyze each column
            column_analysis = {}
            for col_name in sample['column_names']:
                # Get values for this column
                values = [row.get(col_name, '') for row in sample['sample_data']]
                non_empty_values = [v for v in values if v.strip()]
                
                column_analysis[col_name] = {
                    'data_type': self._infer_data_type(non_empty_values),
                    'non_null_count': len(non_empty_values),
                    'unique_count': len(set(non_empty_values)),
                    'sample_values': sorted(list(set(non_empty_values)))[:5],  # Up to 5 unique samples, deterministically sorted
                    'fill_rate': len(non_empty_values) / len(values) if values else 0.0
                }
            
            return {
                'basic_info': {
                    'filename': sample['filename'],
                    'shape': [sample['total_rows'], sample['total_columns']],
                    'column_names': sample['column_names'],
                    'sample_rows_analyzed': len(sample['sample_data'])
                },
                'column_analysis': column_analysis,
                'domain_info': self._infer_domain_info(sample),
                'metadata': sample['metadata']
            }
            
        except Exception as e:
            self.logger.error(f"Failed to analyze table structure: {str(e)}")
            raise
    
    def _infer_data_type(self, values: List[str]) -> str:
        """Infer data type from sample values"""
        if not values:
            return "Unknown"
        
        # Check for numbers
        numeric_count = 0
        for value in values:
            try:
                float(value)
                numeric_count += 1
            except ValueError:
                pass
        
        if numeric_count / len(values) > 0.8:
            return "Numeric"
        
        # Check for dates (simple heuristic)
        date_keywords = ['date', 'time', '/', '-', '20', '19']
        date_count = sum(1 for value in values if any(kw in value.lower() for kw in date_keywords))
        
        if date_count / len(values) > 0.5:
            return "Date"
        
        return "Text"
    
    def _infer_domain_info(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        """Infer domain information from table structure"""
        column_names = [name.lower() for name in sample['column_names']]
        
        # Domain keywords
        domain_scores = {}
        
        # Biotech/pharma keywords
        biotech_keywords = ['target', 'indication', 'phase', 'compound', 'drug', 'protein', 'gene']
        biotech_score = sum(1 for col in column_names if any(kw in col for kw in biotech_keywords))
        if biotech_score > 0:
            domain_scores['biotech'] = biotech_score
        
        # Competitive intelligence keywords
        ci_keywords = ['company', 'competitor', 'product', 'market', 'revenue', 'stage']
        ci_score = sum(1 for col in column_names if any(kw in col for kw in ci_keywords))
        if ci_score > 0:
            domain_scores['competitive_intelligence'] = ci_score
        
        # Financial keywords
        financial_keywords = ['price', 'cost', 'revenue', 'profit', 'budget', 'finance']
        financial_score = sum(1 for col in column_names if any(kw in col for kw in financial_keywords))
        if financial_score > 0:
            domain_scores['financial'] = financial_score
        
        # Determine likely domain
        if domain_scores:
            likely_domain = max(domain_scores, key=domain_scores.get)
            confidence = domain_scores[likely_domain] / len(column_names)
        else:
            likely_domain = "general"
            confidence = 0.1
        
        return {
            'likely_domain': likely_domain,
            'domain_scores': domain_scores,
            'confidence': confidence
        }
    
    def _find_table_start(self, all_rows):
        """Find the actual start of the table data by detecting headers intelligently."""
        for row_idx, row in enumerate(all_rows):
            # Skip completely empty rows
            if not any(cell is not None and str(cell).strip() for cell in row):
                continue
            
            # Look for a row that seems like headers (has multiple non-empty values)
            non_empty_count = sum(1 for cell in row if cell is not None and str(cell).strip())
            
            # Consider this a header row if it has at least 2 non-empty cells
            # and the next few rows seem to contain data
            if non_empty_count >= 2:
                # Check if this looks like a data table start
                if self._looks_like_header_row(row, all_rows, row_idx):
                    # Trim trailing empty columns from headers
                    headers = self._trim_trailing_empty(row)
                    return row_idx, headers
        
        # Fallback: use first non-empty row as headers
        for row_idx, row in enumerate(all_rows):
            if any(cell is not None and str(cell).strip() for cell in row):
                headers = self._trim_trailing_empty(row)
                return row_idx, headers
        
        # Ultimate fallback
        return 0, all_rows[0] if all_rows else []
    
    def _looks_like_header_row(self, current_row, all_rows, row_idx):
        """Determine if this row looks like a header by examining following rows."""
        # If this is the last row, it's probably not a header
        if row_idx >= len(all_rows) - 1:
            return False
        
        # Check if there are data rows after this potential header
        data_rows_found = 0
        for check_idx in range(row_idx + 1, min(row_idx + 4, len(all_rows))):
            check_row = all_rows[check_idx]
            if any(cell is not None and str(cell).strip() for cell in check_row):
                data_rows_found += 1
        
        # Consider it a header if there's at least one data row following
        return data_rows_found > 0
    
    def _trim_trailing_empty(self, row):
        """Remove trailing empty cells from a row."""
        # Find the last non-empty cell
        last_content_idx = -1
        for i, cell in enumerate(row):
            if cell is not None and str(cell).strip():
                last_content_idx = i
        
        # Return row up to the last content
        if last_content_idx >= 0:
            return row[:last_content_idx + 1]
        else:
            return row[:1] if row else []  # Keep at least one column
    
    def _clean_data_rows(self, data_rows, header_count):
        """Clean data rows by removing empty trailing rows and trimming to header count."""
        cleaned_rows = []
        
        for row in data_rows:
            # Skip completely empty rows
            if not any(cell is not None and str(cell).strip() for cell in row):
                continue
            
            # Trim row to match header count (or pad if shorter)
            if len(row) < header_count:
                # Pad with empty strings
                cleaned_row = list(row) + [''] * (header_count - len(row))
            else:
                # Trim to header count
                cleaned_row = row[:header_count]
            
            cleaned_rows.append(cleaned_row)
        
        return cleaned_rows
    
    def _find_table_start_csv(self, rows):
        """Find table start for CSV files (similar logic but handles string data)."""
        for row_idx, row in enumerate(rows):
            # Skip completely empty rows
            if not any(str(cell).strip() for cell in row):
                continue
            
            # Look for a row that seems like headers
            non_empty_count = sum(1 for cell in row if str(cell).strip())
            
            # Consider this a header row if it has at least 2 non-empty cells
            if non_empty_count >= 2:
                # Check if this looks like a data table start
                if self._looks_like_header_row_csv(row, rows, row_idx):
                    # Trim trailing empty columns from headers
                    headers = self._trim_trailing_empty_csv(row)
                    return row_idx, headers
        
        # Fallback: use first non-empty row as headers
        for row_idx, row in enumerate(rows):
            if any(str(cell).strip() for cell in row):
                headers = self._trim_trailing_empty_csv(row)
                return row_idx, headers
        
        # Ultimate fallback
        return 0, rows[0] if rows else []
    
    def _looks_like_header_row_csv(self, current_row, rows, row_idx):
        """CSV version of header detection."""
        if row_idx >= len(rows) - 1:
            return False
        
        # Check if there are data rows after this potential header
        data_rows_found = 0
        for check_idx in range(row_idx + 1, min(row_idx + 4, len(rows))):
            check_row = rows[check_idx]
            if any(str(cell).strip() for cell in check_row):
                data_rows_found += 1
        
        return data_rows_found > 0
    
    def _trim_trailing_empty_csv(self, row):
        """CSV version of trailing empty cell removal."""
        last_content_idx = -1
        for i, cell in enumerate(row):
            if str(cell).strip():
                last_content_idx = i
        
        if last_content_idx >= 0:
            return row[:last_content_idx + 1]
        else:
            return row[:1] if row else []
    
    def _clean_data_rows_csv(self, data_rows, header_count):
        """CSV version of data row cleaning."""
        cleaned_rows = []
        
        for row in data_rows:
            # Skip completely empty rows
            if not any(str(cell).strip() for cell in row):
                continue
            
            # Trim or pad to match header count
            if len(row) < header_count:
                cleaned_row = list(row) + [''] * (header_count - len(row))
            else:
                cleaned_row = row[:header_count]
            
            cleaned_rows.append(cleaned_row)
        
        return cleaned_rows
    
    def _is_valid_csv_parse(self, rows):
        """Check if CSV parsing produced reasonable results."""
        if not rows or len(rows) < 2:
            return False
        
        # Check if first few rows have similar column counts
        header_count = len(rows[0])
        if header_count < 2:  # Need at least 2 columns to be useful
            return False
        
        # Check first few data rows
        consistent_rows = 0
        for i in range(1, min(4, len(rows))):
            row_count = len(rows[i])
            # Allow some flexibility (within 1-2 columns)
            if abs(row_count - header_count) <= 2:
                consistent_rows += 1
        
        # If most rows have similar column counts, parsing is probably good
        return consistent_rows >= min(2, len(rows) - 1)
    
    def _parse_csv_with_robust_fallback(self, text_content):
        """Robust CSV parsing with delimiter detection for non-standard files."""
        lines = text_content.splitlines()
        if not lines:
            return []
        
        # Try to detect delimiter
        delimiter = self._detect_delimiter(text_content)
        self.logger.info(f"Detected delimiter: '{delimiter}'")
        
        # Parse with detected delimiter
        try:
            if delimiter:
                reader = csv.reader(lines, delimiter=delimiter)
                rows = list(reader)
                
                # Validate this parsing
                if self._is_valid_csv_parse(rows):
                    return rows
        except csv.Error as e:
            self.logger.warning(f"Failed with detected delimiter '{delimiter}': {e}")
        
        # Fallback to manual splitting if CSV reader fails
        return self._manual_csv_parse(lines)
    
    def _detect_delimiter(self, text_content):
        """Detect the most likely delimiter in the CSV file."""
        # Common delimiters to try (in order of preference)
        delimiters = [',', ';', '\t', '|', ':', ' ']
        
        # Sample first few lines for analysis
        sample_lines = text_content.splitlines()[:10]
        sample_text = '\n'.join(sample_lines)
        
        best_delimiter = None
        best_score = 0
        
        for delimiter in delimiters:
            try:
                # Use csv.Sniffer to help detect
                sniffer = csv.Sniffer()
                if sniffer.sniff(sample_text, delimiters=delimiter):
                    # Count occurrences and consistency
                    score = self._score_delimiter(sample_lines, delimiter)
                    if score > best_score:
                        best_score = score
                        best_delimiter = delimiter
            except csv.Error:
                # If sniffer fails, try manual scoring
                score = self._score_delimiter(sample_lines, delimiter)
                if score > best_score:
                    best_score = score
                    best_delimiter = delimiter
        
        return best_delimiter or ','  # Default to comma
    
    def _score_delimiter(self, lines, delimiter):
        """Score how well a delimiter works for parsing."""
        if not lines:
            return 0
        
        # Count delimiter occurrences per line
        counts = []
        for line in lines[:5]:  # Check first 5 lines
            if line.strip():  # Skip empty lines
                count = line.count(delimiter)
                if count > 0:  # Only count lines that have the delimiter
                    counts.append(count)
        
        if len(counts) < 2:
            return 0
        
        # Score based on consistency of delimiter count
        avg_count = sum(counts) / len(counts)
        variance = sum((count - avg_count) ** 2 for count in counts) / len(counts)
        
        # Good delimiters should have:
        # 1. At least 1 occurrence per line on average
        # 2. Low variance (consistent across lines)
        if avg_count >= 1:
            consistency_score = max(0, 10 - variance)  # Lower variance = higher score
            frequency_score = min(avg_count, 10)  # Cap at 10 to prevent over-weighting
            return consistency_score + frequency_score
        
        return 0
    
    def _manual_csv_parse(self, lines):
        """Manual CSV parsing for really problematic files."""
        rows = []
        
        # Try common delimiters in order
        test_delimiters = [',', ';', '\t', '|', ':', ' ']
        
        for delimiter in test_delimiters:
            test_rows = []
            for line in lines[:5]:  # Test first 5 lines
                if line.strip():
                    parts = [part.strip().strip('"\'') for part in line.split(delimiter)]
                    if len(parts) > 1:  # Must split into multiple parts
                        test_rows.append(parts)
            
            # If we got reasonable results, use this delimiter for all lines
            if len(test_rows) >= 2 and self._check_manual_parse_consistency(test_rows):
                self.logger.info(f"Using manual parsing with delimiter: '{delimiter}'")
                # Parse all lines with this delimiter
                for line in lines:
                    if line.strip():
                        parts = [part.strip().strip('"\'') for part in line.split(delimiter)]
                        rows.append(parts)
                return rows
        
        # Ultimate fallback: split by whitespace
        self.logger.warning("Using whitespace splitting as ultimate fallback")
        for line in lines:
            if line.strip():
                # Split by any whitespace and filter empty parts
                parts = [part for part in line.split() if part]
                if parts:
                    rows.append(parts)
        
        return rows
    
    def _check_manual_parse_consistency(self, rows):
        """Check if manually parsed rows have consistent structure."""
        if len(rows) < 2:
            return False
        
        # Check if column counts are reasonably consistent
        col_counts = [len(row) for row in rows]
        avg_cols = sum(col_counts) / len(col_counts)
        
        # Allow some variance but not too much
        consistent_count = sum(1 for count in col_counts if abs(count - avg_cols) <= 1)
        return consistent_count >= len(rows) * 0.7  # 70% of rows should be consistent

# Global instance for easy imports
s3_table_parser = S3TableParser()