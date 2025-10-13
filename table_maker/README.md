# Table Maker

A standalone system for generating structured tables from unstructured data using Claude AI.

## Overview

Table Maker is a modular, extensible system that uses Claude's API to convert unstructured text into structured tables based on configurable schemas and prompts.

## Directory Structure

```
table_maker/
├── prompts/          # Prompt templates for table generation
├── schemas/          # JSON schemas defining table structures
├── src/              # Source code for the table maker system
├── tests/            # Unit and integration tests
├── examples/         # Example usage and sample data
├── requirements.txt  # Python dependencies
└── README.md        # This file
```

## Installation

1. Clone or navigate to the table_maker directory
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up your Anthropic API key:

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

## Local Testing

### Running Tests

Execute all tests:

```bash
pytest tests/
```

Run tests with verbose output:

```bash
pytest tests/ -v
```

Run specific test file:

```bash
pytest tests/test_specific.py
```

### Running Examples

Example scripts will be available in the `examples/` directory:

```bash
python examples/basic_usage.py
```

## Usage

Basic usage pattern:

```python
from table_maker.src import TableMaker

# Initialize the table maker
maker = TableMaker(
    schema_path="schemas/your_schema.json",
    prompt_path="prompts/your_prompt.txt"
)

# Generate table from unstructured data
result = maker.generate_table(input_data)
```

## Configuration

- **Prompts**: Store reusable prompt templates in `prompts/`
- **Schemas**: Define table structures in JSON format in `schemas/`
- **Environment Variables**:
  - `ANTHROPIC_API_KEY`: Required for Claude API access
  - `AWS_REGION`: Optional, for AWS services integration

## Development

### Adding New Features

1. Add source code to `src/`
2. Add corresponding tests to `tests/`
3. Update examples in `examples/` if applicable
4. Update this README with usage instructions

### Testing Guidelines

- Write unit tests for all new functions
- Use pytest fixtures for common test data
- Mock external API calls in tests
- Aim for >80% code coverage

## Dependencies

See `requirements.txt` for the full list. Key dependencies:

- `anthropic`: Claude API client
- `aiohttp`: Async HTTP client
- `aioboto3`: Async AWS SDK
- `boto3`: AWS SDK for Python
- `pandas`: Data manipulation and analysis
- `pyyaml`: YAML parsing
- `pytest`: Testing framework
- `pytest-asyncio`: Async testing support

## License

[Specify license here]

## Contributing

[Add contribution guidelines here]

## Support

[Add support contact information here]
