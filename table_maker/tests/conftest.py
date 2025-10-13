#!/usr/bin/env python3
"""
Shared pytest fixtures for table generation system tests.
"""

import pytest
import tempfile
import json
import os
import sys
import logging
from pathlib import Path
from unittest.mock import AsyncMock, Mock

# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)8s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add project paths to sys.path for imports
PROJECT_ROOT = Path(__file__).parent.parent
SRC_ROOT = PROJECT_ROOT.parent / "src"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_ROOT))


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_prompt_template():
    """Sample prompt template with variables."""
    return """You are helping with {{TASK_NAME}}.

## Input
{{USER_INPUT}}

## Instructions
{{INSTRUCTIONS}}

Please proceed with the task."""


@pytest.fixture
def sample_prompt_dir(temp_dir, sample_prompt_template):
    """Create temporary prompts directory with sample template."""
    prompts_dir = temp_dir / "prompts"
    prompts_dir.mkdir()

    # Create test template
    test_template = prompts_dir / "test_template.md"
    test_template.write_text(sample_prompt_template)

    # Create template with multiple variables
    multi_var_template = prompts_dir / "multi_var.md"
    multi_var_template.write_text("{{VAR1}} and {{VAR2}} and {{VAR3}}")

    # Create template with no variables
    no_var_template = prompts_dir / "no_vars.md"
    no_var_template.write_text("This template has no variables.")

    return prompts_dir


@pytest.fixture
def sample_schema():
    """Sample JSON schema for validation."""
    return {
        "type": "object",
        "required": ["name", "age"],
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "number", "minimum": 0},
            "email": {"type": "string"}
        }
    }


@pytest.fixture
def sample_schemas_dir(temp_dir, sample_schema):
    """Create temporary schemas directory with sample schema."""
    schemas_dir = temp_dir / "schemas"
    schemas_dir.mkdir()

    # Create test schema
    test_schema = schemas_dir / "test_schema.json"
    test_schema.write_text(json.dumps(sample_schema, indent=2))

    # Create response schema
    response_schema = schemas_dir / "response_schema.json"
    response_schema.write_text(json.dumps({
        "type": "object",
        "required": ["status", "data"],
        "properties": {
            "status": {"type": "string"},
            "data": {"type": "object"}
        }
    }, indent=2))

    return schemas_dir


@pytest.fixture
def sample_columns():
    """Sample column definitions for table generation."""
    return [
        {
            "name": "company_name",
            "description": "Name of the company",
            "format": "String",
            "importance": "CRITICAL",
            "is_identification": True
        },
        {
            "name": "website",
            "description": "Company website URL",
            "format": "URL",
            "importance": "HIGH",
            "is_identification": False
        },
        {
            "name": "employee_count",
            "description": "Number of employees",
            "format": "Integer",
            "importance": "MEDIUM",
            "is_identification": False
        }
    ]


@pytest.fixture
def sample_rows():
    """Sample row data for table generation."""
    return [
        {
            "company_name": "Acme Corp",
            "website": "https://acme.com",
            "employee_count": "500"
        },
        {
            "company_name": "Tech Innovations",
            "website": "https://techinnovations.io",
            "employee_count": "1200"
        }
    ]


@pytest.fixture
def sample_table_structure(sample_columns, sample_rows):
    """Sample complete table structure."""
    return {
        "columns": sample_columns,
        "rows": sample_rows,
        "metadata": {
            "description": "Company research table",
            "conversation_id": "test_conv_123"
        }
    }


@pytest.fixture
def mock_ai_client():
    """Mock AI API client for testing."""
    client = Mock()
    client.call_structured_api = AsyncMock()
    return client


@pytest.fixture
def sample_ai_response():
    """Sample AI API response."""
    return {
        "success": True,
        "response": {
            "ai_message": "Here is my response.",
            "proposed_rows": {
                "identification_columns": ["company_name"],
                "sample_rows": [
                    {"company_name": "Example Corp"}
                ]
            },
            "proposed_columns": [
                {
                    "name": "company_name",
                    "description": "Company name",
                    "format": "String",
                    "importance": "CRITICAL",
                    "is_identification": True
                }
            ],
            "clarifying_questions": "",
            "confidence": 0.9,
            "ready_to_generate": True,
            "reasoning": "This structure makes sense."
        },
        "token_usage": {
            "input_tokens": 100,
            "output_tokens": 200,
            "total_tokens": 300
        }
    }


@pytest.fixture
def sample_row_expansion_response():
    """Sample AI response for row expansion."""
    return {
        "success": True,
        "response": {
            "expanded_rows": [
                {"company_name": "New Company 1", "website": "https://new1.com"},
                {"company_name": "New Company 2", "website": "https://new2.com"}
            ],
            "reasoning": "Generated diverse company examples."
        },
        "token_usage": {
            "input_tokens": 150,
            "output_tokens": 100,
            "total_tokens": 250
        }
    }


@pytest.fixture
def sample_conversation_log():
    """Sample conversation log."""
    return [
        {
            "timestamp": "2024-01-01T10:00:00Z",
            "role": "user",
            "content": "I want to research tech companies"
        },
        {
            "timestamp": "2024-01-01T10:00:05Z",
            "role": "assistant",
            "content": {
                "ai_message": "Let me help you design a table.",
                "proposed_rows": {"identification_columns": ["company_name"], "sample_rows": []},
                "proposed_columns": [],
                "clarifying_questions": "What specific data points?",
                "confidence": 0.7,
                "ready_to_generate": False,
                "reasoning": "Need more details"
            }
        }
    ]


# ============================================================================
# INTEGRATION TEST FIXTURES (SESSION SCOPE)
# ============================================================================

@pytest.fixture(scope="session")
def api_key():
    """
    Get Anthropic API key from environment.
    Skip integration tests if not available.
    """
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        pytest.skip("ANTHROPIC_API_KEY not set in environment")
    return key


@pytest.fixture(scope="session")
def project_root():
    """Get project root directory."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def ai_client(api_key):
    """
    Create AI API client for real API calls.
    Shared across all integration tests in session.
    """
    from shared.ai_api_client import AIAPIClient

    # Create client without S3 bucket for local testing
    client = AIAPIClient(s3_bucket=None)
    logger.info("Created AI API client for integration tests")
    return client


@pytest.fixture(scope="session")
def prompt_loader(project_root):
    """
    Create prompt loader.
    Shared across all tests in session.
    """
    from src.prompt_loader import PromptLoader

    prompts_dir = project_root / "prompts"
    loader = PromptLoader(str(prompts_dir))
    logger.info(f"Created prompt loader from: {prompts_dir}")
    return loader


@pytest.fixture(scope="session")
def schema_validator(project_root):
    """
    Create schema validator.
    Shared across all tests in session.
    """
    from src.schema_validator import SchemaValidator

    schemas_dir = project_root / "schemas"
    validator = SchemaValidator(str(schemas_dir))
    logger.info(f"Created schema validator from: {schemas_dir}")
    return validator


# ============================================================================
# INTEGRATION TEST FIXTURES (FUNCTION SCOPE)
# ============================================================================

@pytest.fixture
def temp_output_dir():
    """
    Create temporary directory for integration test outputs.
    Automatically cleaned up after test.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)
        logger.info(f"Created temporary directory: {temp_path}")
        yield temp_path
        logger.info(f"Cleaned up temporary directory: {temp_path}")


@pytest.fixture
def conversation_handler(ai_client, prompt_loader, schema_validator):
    """
    Create fresh conversation handler for each test.
    Ensures test isolation.
    """
    from src.conversation_handler import TableConversationHandler

    handler = TableConversationHandler(ai_client, prompt_loader, schema_validator)
    logger.info("Created fresh conversation handler")
    return handler


@pytest.fixture
def table_generator():
    """Create table generator for each test."""
    from src.table_generator import TableGenerator

    generator = TableGenerator()
    logger.info("Created table generator")
    return generator


@pytest.fixture
def row_expander(ai_client, prompt_loader, schema_validator):
    """Create row expander for each test."""
    from src.row_expander import RowExpander

    expander = RowExpander(ai_client, prompt_loader, schema_validator)
    logger.info("Created row expander")
    return expander


@pytest.fixture
def config_generator(ai_client):
    """Create config generator for each test."""
    from src.config_generator import ConfigGenerator

    generator = ConfigGenerator(ai_client)
    logger.info("Created config generator")
    return generator


# ============================================================================
# PYTEST HOOKS
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: Integration tests that make real API calls"
    )
    config.addinivalue_line(
        "markers",
        "unit: Unit tests that don't make external calls"
    )
    config.addinivalue_line(
        "markers",
        "slow: Tests that take a long time to run"
    )


def pytest_runtest_setup(item):
    """Setup before each test."""
    if "integration" in [marker.name for marker in item.iter_markers()]:
        # Check API key for integration tests
        if not os.environ.get('ANTHROPIC_API_KEY'):
            pytest.skip("ANTHROPIC_API_KEY not set - skipping integration test")
