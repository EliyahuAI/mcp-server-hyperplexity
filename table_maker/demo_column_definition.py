#!/usr/bin/env python3
"""
Demo script for Column Definition Handler.
Shows example usage and output.
"""

import asyncio
import json
from pathlib import Path

# Mock dependencies for demo
from unittest.mock import AsyncMock, Mock


def create_mock_dependencies():
    """Create mocked dependencies for demo."""
    # Mock AI Client
    mock_ai_client = Mock()
    mock_ai_client.call_structured_api = AsyncMock()

    # Sample response
    sample_response = {
        'columns': [
            {
                'name': 'Company Name',
                'description': 'Official name of the AI company',
                'format': 'String',
                'importance': 'ID',
                'is_identification': True
            },
            {
                'name': 'Website',
                'description': 'Company website URL',
                'format': 'URL',
                'importance': 'ID',
                'is_identification': True
            },
            {
                'name': 'Is Hiring for AI',
                'description': 'Whether company has active AI/ML job postings',
                'format': 'Boolean',
                'importance': 'CRITICAL',
                'is_identification': False,
                'validation_strategy': "Check company careers page for job postings containing 'AI', 'ML', 'Machine Learning', or 'Deep Learning' keywords. Look for roles like 'Machine Learning Engineer', 'AI Researcher', etc."
            },
            {
                'name': 'Team Size',
                'description': 'Approximate number of employees at the company',
                'format': 'Number',
                'importance': 'CRITICAL',
                'is_identification': False,
                'validation_strategy': 'Look for team size on LinkedIn company page, About Us section, or Crunchbase profile. Accept ranges like "50-200" and convert to midpoint.'
            },
            {
                'name': 'Recent Funding',
                'description': 'Funding raised in the last 12 months',
                'format': 'String',
                'importance': 'CRITICAL',
                'is_identification': False,
                'validation_strategy': 'Search for recent press releases, Crunchbase entries, or news articles mentioning funding rounds. Look for Series A/B/C announcements or acquisition news.'
            }
        ],
        'search_strategy': {
            'description': 'Find AI companies across research, healthcare, and enterprise sectors with active hiring, focusing on companies with public job postings and visible growth indicators.',
            'subdomain_hints': [
                'AI Research Companies (Academic and research-focused organizations)',
                'Healthcare AI Startups (Medical AI, biotech, diagnostics)',
                'Enterprise AI Solutions (Business automation, analytics)',
                'AI Infrastructure & Tools (MLOps, data platforms)'
            ],
            'search_queries': [
                'top AI companies hiring machine learning engineers 2024',
                'artificial intelligence startups with job openings',
                'AI research labs recruiting',
                'enterprise AI companies hiring',
                'healthcare AI startups with funding'
            ]
        },
        'table_name': 'AI Companies Hiring Status',
        'tablewide_research': 'Research active AI companies to identify hiring trends, growth patterns, and investment activity in the artificial intelligence sector. Focus on companies with public visibility, active job postings, and verifiable team size/funding information.'
    }

    mock_ai_client.call_structured_api.return_value = {
        'response': sample_response,
        'token_usage': {
            'input_tokens': 1250,
            'output_tokens': 680,
            'total_tokens': 1930
        }
    }

    # Mock Prompt Loader
    mock_prompt_loader = Mock()
    mock_prompt_loader.load_prompt = Mock(return_value="[Mock prompt template]")

    # Mock Schema Validator
    mock_schema_validator = Mock()
    mock_schema_validator.load_schema = Mock(return_value={'type': 'object'})
    mock_schema_validator.validate_ai_response = Mock(return_value={
        'is_valid': True,
        'errors': [],
        'warnings': []
    })

    return mock_ai_client, mock_prompt_loader, mock_schema_validator


async def main():
    """Run demo."""
    print("=" * 80)
    print("COLUMN DEFINITION HANDLER - DEMO")
    print("=" * 80)
    print()

    # Import the handler
    from src.column_definition_handler import ColumnDefinitionHandler

    # Create mocked dependencies
    ai_client, prompt_loader, schema_validator = create_mock_dependencies()

    # Create handler
    handler = ColumnDefinitionHandler(ai_client, prompt_loader, schema_validator)
    print("[SUCCESS] Created ColumnDefinitionHandler")
    print()

    # Sample conversation context (what user approved)
    conversation_context = {
        'conversation_id': 'demo_conv_123',
        'conversation_log': [
            {
                'timestamp': '2024-01-01T10:00:00Z',
                'role': 'user',
                'content': 'I want to find AI companies that are actively hiring'
            },
            {
                'timestamp': '2024-01-01T10:00:15Z',
                'role': 'assistant',
                'content': {
                    'ai_message': "I'll create a table to track AI companies and their hiring status.",
                    'proposed_rows': {
                        'identification_columns': ['Company Name', 'Website'],
                        'sample_rows': []
                    },
                    'proposed_columns': [
                        {
                            'name': 'Company Name',
                            'description': 'Company name',
                            'format': 'String',
                            'importance': 'ID',
                            'is_identification': True
                        }
                    ],
                    'clarifying_questions': 'What data points do you want to track?',
                    'confidence': 0.7,
                    'ready_to_generate': False,
                    'reasoning': 'Need more details'
                }
            },
            {
                'timestamp': '2024-01-01T10:01:00Z',
                'role': 'user',
                'content': 'Track if they are hiring for AI, their team size, and recent funding'
            },
            {
                'timestamp': '2024-01-01T10:01:25Z',
                'role': 'assistant',
                'content': {
                    'ai_message': 'Perfect! Ready to generate the table.',
                    'proposed_rows': {
                        'identification_columns': ['Company Name', 'Website'],
                        'sample_rows': [
                            {'Company Name': 'Anthropic', 'Website': 'anthropic.com'}
                        ]
                    },
                    'proposed_columns': [
                        {
                            'name': 'Company Name',
                            'description': 'Company name',
                            'format': 'String',
                            'importance': 'ID',
                            'is_identification': True
                        },
                        {
                            'name': 'Is Hiring for AI',
                            'description': 'Whether hiring for AI roles',
                            'format': 'Boolean',
                            'importance': 'CRITICAL',
                            'is_identification': False
                        }
                    ],
                    'clarifying_questions': '',
                    'confidence': 0.95,
                    'ready_to_generate': True,
                    'reasoning': 'All requirements captured'
                }
            }
        ],
        'current_proposal': {
            'rows': {
                'identification_columns': ['Company Name', 'Website'],
                'sample_rows': [
                    {'Company Name': 'Anthropic', 'Website': 'anthropic.com'}
                ]
            },
            'columns': [
                {
                    'name': 'Company Name',
                    'description': 'Company name',
                    'format': 'String',
                    'importance': 'ID',
                    'is_identification': True
                },
                {
                    'name': 'Is Hiring for AI',
                    'description': 'Whether hiring for AI roles',
                    'format': 'Boolean',
                    'importance': 'CRITICAL',
                    'is_identification': False
                }
            ]
        }
    }

    print("INPUT: Conversation Context")
    print("-" * 80)
    print(f"Conversation ID: {conversation_context['conversation_id']}")
    print(f"Conversation Turns: {len(conversation_context['conversation_log'])}")
    print(f"User's Request: Find AI companies that are actively hiring")
    print(f"Approved Columns: Company Name, Website, Is Hiring for AI, Team Size, Recent Funding")
    print()

    # Run column definition
    print("PROCESSING: Defining columns and search strategy...")
    print("-" * 80)
    result = await handler.define_columns(conversation_context)

    if not result['success']:
        print(f"[ERROR] {result['error']}")
        return

    print(f"[SUCCESS] Completed in {result['processing_time']:.2f}s")
    print()

    # Display results
    print("OUTPUT: Column Definitions")
    print("=" * 80)
    print(f"Table Name: {result['table_name']}")
    print()
    print(f"Research Context:\n{result['tablewide_research']}")
    print()

    # Show columns
    print(f"\nColumns ({len(result['columns'])} total):")
    print("-" * 80)

    for idx, col in enumerate(result['columns'], 1):
        print(f"\n{idx}. {col['name']}")
        print(f"   Description: {col['description']}")
        print(f"   Format: {col['format']}")
        print(f"   Type: {'ID Column' if col['is_identification'] else 'Research Column'}")
        if not col['is_identification']:
            print(f"   Validation Strategy: {col['validation_strategy']}")

    # Show search strategy
    print("\n\nSearch Strategy:")
    print("=" * 80)
    search_strategy = result['search_strategy']

    print(f"\nDescription:\n{search_strategy['description']}")

    print(f"\nSubdomain Hints ({len(search_strategy['subdomain_hints'])}):")
    for idx, hint in enumerate(search_strategy['subdomain_hints'], 1):
        print(f"  {idx}. {hint}")

    print(f"\nSearch Queries ({len(search_strategy['search_queries'])}):")
    for idx, query in enumerate(search_strategy['search_queries'], 1):
        print(f"  {idx}. {query}")

    # Show summary
    print("\n\nSummary:")
    print("=" * 80)
    summary = handler.get_columns_summary(result['columns'])
    print(f"Total Columns: {summary['total_columns']}")
    print(f"ID Columns: {summary['id_columns']} ({', '.join(summary['id_column_names'])})")
    print(f"Research Columns: {summary['research_columns']} ({', '.join(summary['research_column_names'])})")
    print(f"All Research Columns Have Validation Strategies: {summary['all_have_validation_strategies']}")
    print()

    print("=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    asyncio.run(main())
