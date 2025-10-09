"""
Mock validation results and QC results for testing history handling.

These structures represent the output from validation and QC processing.
"""

from datetime import datetime, timezone


def get_mock_validation_results():
    """
    Get mock validation results structure.

    Structure matches the output from schema_validator_simplified.py
    """
    return {
        'row_hash_abc123': {
            'Company Name': {
                'value': 'ABC Corporation',
                'confidence_level': 'HIGH',
                'original_confidence': 'MEDIUM',
                'reasoning': 'Company name validated from multiple sources including official website and SEC filings',
                'sources': ['https://example.com/about', 'https://sec.gov/filing'],
                'citations': [
                    {
                        'title': 'Company Website',
                        'url': 'https://example.com/about',
                        'cited_text': 'ABC Corporation was founded in 2010 and specializes in...'
                    },
                    {
                        'title': 'SEC Filing',
                        'url': 'https://sec.gov/filing',
                        'cited_text': 'ABC Corporation (formerly ABC Corp) filed their 10-K...'
                    }
                ],
                'explanation': 'Name found consistently across official sources',
                'consistent_with_model_knowledge': 'YES - Company is well known',
                'model': 'sonar-pro'
            },
            'Status': {
                'value': 'Active',
                'confidence_level': 'HIGH',
                'original_confidence': 'LOW',
                'reasoning': 'Current status confirmed via recent press release',
                'sources': ['https://example.com/press'],
                'citations': [
                    {
                        'title': 'Press Release',
                        'url': 'https://example.com/press',
                        'cited_text': 'ABC Corporation announces Q4 results, company remains active...'
                    }
                ],
                'explanation': 'Recent activity confirms active status',
                'consistent_with_model_knowledge': 'YES',
                'model': 'sonar-pro'
            },
            'Revenue': {
                'value': '$500M',
                'confidence_level': 'MEDIUM',
                'original_confidence': 'LOW',
                'reasoning': 'Revenue estimate from industry reports',
                'sources': ['https://industry-report.com/abc'],
                'citations': [
                    {
                        'title': 'Industry Report 2024',
                        'url': 'https://industry-report.com/abc',
                        'cited_text': 'ABC Corporation estimated annual revenue of approximately $500M'
                    }
                ],
                'explanation': 'Revenue not officially disclosed, using industry estimates',
                'consistent_with_model_knowledge': 'PARTIAL - estimate only',
                'model': 'sonar-pro'
            }
        },
        'row_hash_def456': {
            'Company Name': {
                'value': 'DEF Industries',
                'confidence_level': 'HIGH',
                'original_confidence': 'HIGH',
                'reasoning': 'Company name unchanged and well-documented',
                'sources': ['https://def-industries.com'],
                'citations': [
                    {
                        'title': 'DEF Industries Official Site',
                        'url': 'https://def-industries.com',
                        'cited_text': 'DEF Industries - Leading manufacturer since 1995'
                    }
                ],
                'explanation': 'Established company with consistent naming',
                'consistent_with_model_knowledge': 'YES',
                'model': 'sonar-pro'
            },
            'Status': {
                'value': 'Active',
                'confidence_level': 'HIGH',
                'original_confidence': 'MEDIUM',
                'reasoning': 'Company actively trading and reporting',
                'sources': ['https://nasdaq.com/def'],
                'citations': [],
                'explanation': 'Trading status verified',
                'consistent_with_model_knowledge': 'YES',
                'model': 'sonar-pro'
            },
            'Revenue': {
                'value': '$2.3B',
                'confidence_level': 'HIGH',
                'original_confidence': 'MEDIUM',
                'reasoning': 'Official revenue from annual report',
                'sources': ['https://def-industries.com/investor/annual-report'],
                'citations': [
                    {
                        'title': 'DEF Industries Annual Report 2023',
                        'url': 'https://def-industries.com/investor/annual-report',
                        'cited_text': 'Total revenue for FY2023: $2.3 billion'
                    }
                ],
                'explanation': 'Officially reported revenue',
                'consistent_with_model_knowledge': 'YES',
                'model': 'sonar-pro'
            }
        }
    }


def get_mock_qc_results():
    """
    Get mock QC results structure.

    Structure matches the output from QC processing that adjusts validation results.
    """
    return {
        'row_hash_abc123': {
            'Company Name': {
                'qc_applied': True,
                'qc_entry': 'ABC Corporation',  # QC confirmed the value
                'qc_confidence': 'HIGH',
                'qc_original_confidence': 'MEDIUM',  # QC re-assessed original
                'qc_updated_confidence': 'HIGH',
                'qc_reasoning': 'Name confirmed from primary sources',
                'qc_citations': 'Company website (https://example.com) and SEC filing (https://sec.gov/filing)',
                'qc_sources': ['https://example.com/about', 'https://sec.gov/filing'],
                'update_importance': '3'
            },
            'Revenue': {
                'qc_applied': True,
                'qc_entry': '$485M',  # QC corrected the value
                'qc_confidence': 'HIGH',  # QC upgraded confidence
                'qc_original_confidence': 'LOW',
                'qc_updated_confidence': 'MEDIUM',
                'qc_reasoning': 'Found actual reported revenue in recent SEC filing, original estimate was close but not exact',
                'qc_citations': 'SEC 10-K filing dated 2024-03-15 (https://sec.gov/filing-10k)',
                'qc_sources': ['https://sec.gov/filing-10k'],
                'update_importance': '5'  # Higher importance due to correction
            }
        },
        'row_hash_def456': {
            'Status': {
                'qc_applied': True,
                'qc_entry': 'Active',  # QC confirmed
                'qc_confidence': 'HIGH',
                'qc_original_confidence': 'MEDIUM',
                'qc_updated_confidence': 'HIGH',
                'qc_reasoning': 'Verified active trading status',
                'qc_citations': 'NASDAQ listing verified as of 2024-10-09',
                'qc_sources': ['https://nasdaq.com/def'],
                'update_importance': '2'
            }
        }
    }


def get_mock_config_data():
    """
    Get mock configuration data.

    Structure matches the config used by schema_validator_simplified.py
    """
    return {
        'general_notes': 'Test configuration for company validation',
        'default_model': 'sonar-pro',
        'default_search_context_size': 'low',
        'validation_targets': [
            {
                'column': 'Company ID',
                'description': 'Unique identifier for the company',
                'importance': 'ID',
                'format': 'String',
                'examples': ['ABC123', 'DEF456']
            },
            {
                'column': 'Company Name',
                'description': 'Official registered company name',
                'importance': 'CRITICAL',
                'format': 'String',
                'notes': 'Use full legal name',
                'examples': ['ABC Corporation', 'DEF Industries Inc.']
            },
            {
                'column': 'Status',
                'description': 'Current operational status',
                'importance': 'HIGH',
                'format': 'String',
                'examples': ['Active', 'Inactive', 'Acquired']
            },
            {
                'column': 'Revenue',
                'description': 'Annual revenue',
                'importance': 'MEDIUM',
                'format': 'Currency',
                'notes': 'Most recent fiscal year',
                'examples': ['$1M', '$500M', '$2.3B']
            },
            {
                'column': 'Notes',
                'description': 'Additional notes',
                'importance': 'IGNORED',
                'format': 'String'
            }
        ]
    }


def get_mock_excel_data():
    """
    Get mock Excel data structure as returned by shared_table_parser.py
    """
    return {
        'filename': 'test_companies.xlsx',
        'total_rows': 2,
        'total_columns': 5,
        'column_names': ['Company ID', 'Company Name', 'Status', 'Revenue', 'Notes'],
        'data': [
            {
                'Company ID': 'ABC123',
                'Company Name': 'ABC Corp',  # Original value
                'Status': 'Unknown',  # Original value
                'Revenue': '$400M',  # Original value
                'Notes': 'Large corporation'
            },
            {
                'Company ID': 'DEF456',
                'Company Name': 'DEF Industries',
                'Status': 'Active',
                'Revenue': '$2B',  # Original estimate
                'Notes': 'Manufacturing company'
            }
        ],
        'metadata': {
            'file_type': 'excel',
            'sheet_name': 'Companies',
            'source': 's3',
            'sample_rows': 2
        }
    }


def get_mock_session_info():
    """
    Get mock session_info.json structure with validation runs.
    """
    return {
        'session_id': 'test_session_12345',
        'email': 'test@example.com',
        'created_at': '2024-01-15T10:00:00Z',
        'validation_runs': [
            {
                'run_number': 1,
                'run_time': '2024-01-15T10:30:00.000Z',
                'session_id': 'test_session_12345',
                'configuration_id': 's3://hyperplexity-storage/configs/test_config.json',
                'run_key': 'test_session_12345_1705314600',
                'rows': 2,
                'columns': 4,  # Excluding ID and IGNORED columns
                'confidences_original': 'L: 50%, M: 25%, H: 25%',
                'confidences_updated': 'L: 12%, M: 38%, H: 50%',
                'is_preview': True
            }
        ]
    }


def get_mock_cell_comments():
    """
    Get mock cell comments as they would appear in Excel.

    Returns a dictionary mapping (row, column) to comment text.
    """
    return {
        (2, 'Company Name'): """Original Value: ABC Corp (MEDIUM Confidence)

Key Citation: Company website dated 2024-01-15 (https://example.com/about)

Sources:
[1] Company Website (https://example.com/about): "ABC Corp was founded in..."
[2] SEC Filing (https://sec.gov/filing): "ABC Corp (formerly ABC Corporation)..." """,

        (2, 'Revenue'): """Original Value: $400M (LOW Confidence)

Key Citation: Industry estimate from 2023 report (https://industry-report.com)

Sources:
[1] Industry Report (https://industry-report.com): "ABC Corp estimated revenue $400-500M" """,

        (3, 'Company Name'): """Original Value: DEF Industries (HIGH Confidence)

Key Citation: Official company registration (https://def-industries.com)

Sources:
[1] DEF Industries Official Site (https://def-industries.com): "DEF Industries - Leading manufacturer since 1995" """
    }


# For easy import of all mock data
__all__ = [
    'get_mock_validation_results',
    'get_mock_qc_results',
    'get_mock_config_data',
    'get_mock_excel_data',
    'get_mock_session_info',
    'get_mock_cell_comments'
]
