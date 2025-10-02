#!/usr/bin/env python3
"""
Lightweight Table Analyzer for Lambda - Uses Shared Parser
Refactored to use shared_table_parser.py for consistent row counting and parsing logic.
"""

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

# Add parent directory to path to import shared modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.shared_table_parser import S3TableParser

class LightweightTableAnalyzer:
    """Lightweight table analyzer using shared_table_parser for consistency"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Note: We don't initialize S3TableParser here since we work with local files

    def analyze_table(self, file_path: str, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze table structure from Excel or CSV file

        Args:
            file_path: Path to Excel or CSV file
            sheet_name: Excel sheet name (optional, uses first sheet if not specified)

        Returns:
            Analysis dictionary with structure information
        """
        try:
            # Read the file content
            with open(file_path, 'rb') as f:
                file_content = f.read()

            filename = os.path.basename(file_path)

            # Use shared parser logic
            parser = S3TableParser()

            # Determine file type
            if filename.endswith('.csv'):
                parsed_data = parser._parse_csv_content(file_content, filename)
            elif filename.endswith(('.xlsx', '.xls')):
                parsed_data = parser._parse_excel_content(file_content, filename, sheet_name, extract_formulas=False)
            else:
                raise ValueError(f"Unsupported file format: {filename}")

            # Convert parsed data to analysis format
            return self._generate_analysis_from_parsed_data(parsed_data)

        except Exception as e:
            self.logger.error(f"Error analyzing table: {e}")
            raise

    def _generate_analysis_from_parsed_data(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert shared_table_parser output to LightweightTableAnalyzer format

        Args:
            parsed_data: Output from S3TableParser (parse_s3_table format)

        Returns:
            Analysis dictionary matching original LightweightTableAnalyzer format
        """
        filename = parsed_data['filename']
        total_rows = parsed_data['total_rows']
        column_names = parsed_data['column_names']
        all_data = parsed_data['data']

        # Use first 100 rows for analysis (like original implementation)
        sample_data = all_data[:100]

        # Basic info
        basic_info = {
            'filename': filename,
            'shape': (total_rows, len(column_names)),
            'column_names': column_names,
            'sample_rows_analyzed': len(sample_data)
        }

        # Add sheet name if Excel
        if parsed_data['metadata']['file_type'] == 'excel':
            basic_info['sheet_name'] = parsed_data['metadata'].get('sheet_name')

        # Column analysis
        column_analysis = {}
        for col_name in column_names:
            # Extract column values from sample data
            column_values = [row.get(col_name, '') for row in sample_data]
            column_analysis[col_name] = self._analyze_column(column_values)

        # Infer domain and groupings
        domain_info = self._infer_domain(column_names, sample_data)
        inferred_groupings = self._infer_groupings(column_names, column_analysis)

        return {
            'basic_info': basic_info,
            'column_analysis': column_analysis,
            'domain_info': domain_info,
            'inferred_groupings': inferred_groupings,
            'analysis_timestamp': datetime.now().isoformat()
        }

    def _analyze_column(self, values: List[str]) -> Dict[str, Any]:
        """Analyze a single column's characteristics"""
        if not values:
            return {
                'data_type': 'Unknown',
                'non_null_count': 0,
                'unique_count': 0,
                'sample_values': []
            }

        non_null_values = [v for v in values if v and str(v).strip()]
        unique_values = list(set(non_null_values))

        # Simple type detection
        data_type = self._detect_data_type(non_null_values)

        return {
            'data_type': data_type,
            'non_null_count': len(non_null_values),
            'unique_count': len(unique_values),
            'sample_values': unique_values[:10],  # First 10 unique values
            'fill_rate': len(non_null_values) / len(values) if values else 0
        }

    def _detect_data_type(self, values: List[str]) -> str:
        """Simple data type detection without pandas"""
        if not values:
            return 'Unknown'

        # Check a sample of values
        sample_size = min(10, len(values))
        sample_values = values[:sample_size]

        numeric_count = 0
        date_like_count = 0

        for value in sample_values:
            if not value or not str(value).strip():
                continue

            str_val = str(value).strip()

            # Check for numeric (int or float)
            try:
                float(str_val.replace(',', ''))  # Handle comma-separated numbers
                numeric_count += 1
                continue
            except (ValueError, TypeError):
                pass

            # Check for date-like patterns
            if self._looks_like_date(str_val):
                date_like_count += 1
                continue

        # Determine type based on majority
        if numeric_count >= sample_size * 0.7:
            return 'Number'
        elif date_like_count >= sample_size * 0.7:
            return 'Date'
        else:
            return 'Text'

    def _looks_like_date(self, value: str) -> bool:
        """Simple date detection"""
        date_indicators = [
            '/', '-', '.',  # Common date separators
            'jan', 'feb', 'mar', 'apr', 'may', 'jun',
            'jul', 'aug', 'sep', 'oct', 'nov', 'dec'
        ]

        value_lower = value.lower()

        # Check for date separators and month names
        return any(indicator in value_lower for indicator in date_indicators)

    def _infer_domain(self, column_names: List[str], data_rows: List[Dict[str, str]]) -> Dict[str, Any]:
        """Infer domain/business context from column names and data"""
        domain_keywords = {
            'biotech': ['drug', 'compound', 'clinical', 'phase', 'trial', 'fda', 'indication', 'target'],
            'finance': ['price', 'cost', 'revenue', 'profit', 'budget', 'financial'],
            'competitive_intelligence': ['competitor', 'company', 'market', 'strategy', 'analysis'],
            'clinical': ['patient', 'dose', 'treatment', 'adverse', 'efficacy', 'safety'],
            'regulatory': ['regulatory', 'approval', 'compliance', 'filing', 'submission']
        }

        column_text = ' '.join(column_names).lower()

        domain_scores = {}
        for domain, keywords in domain_keywords.items():
            score = sum(1 for keyword in keywords if keyword in column_text)
            if score > 0:
                domain_scores[domain] = score

        likely_domain = max(domain_scores.items(), key=lambda x: x[1])[0] if domain_scores else 'general'

        return {
            'likely_domain': likely_domain,
            'domain_scores': domain_scores,
            'confidence': max(domain_scores.values()) / len(domain_keywords.get(likely_domain, ['unknown'])) if domain_scores else 0
        }

    def _infer_groupings(self, column_names: List[str], column_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Infer logical groupings of columns"""
        groupings = []

        # Group by common prefixes/suffixes
        name_groups = {}
        for col_name in column_names:
            # Simple grouping by first word
            first_word = col_name.split()[0].lower() if ' ' in col_name else col_name.lower()
            if first_word not in name_groups:
                name_groups[first_word] = []
            name_groups[first_word].append(col_name)

        for group_name, columns in name_groups.items():
            if len(columns) > 1:  # Only groups with multiple columns
                groupings.append({
                    'name': f"{group_name}_group",
                    'columns': columns,
                    'grouping_reason': 'common_prefix'
                })

        return groupings

# Alias for backward compatibility
TableAnalyzer = LightweightTableAnalyzer
