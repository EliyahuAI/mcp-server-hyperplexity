# AI Configuration Generator for Perplexity Validator

An intelligent JSON configuration file generator that creates optimized validation configurations for the Perplexity Validator system, designed for any data validation domain.

## Overview

This system uses AI (Claude 4) to analyze Excel tables and generate comprehensive JSON configuration files with intelligent interview capabilities, conversational optimization, and real-time validation.

## Key Features

- **Table Analysis**: Automatically analyzes Excel files to understand data structure and domain
- **Interview Mode**: AI-generated questions (3-7) for configuration optimization
- **Conversational System**: Sequential conversations for iterative improvements
- **Real-time Validation**: Integrates with existing Perplexity Validator API validation
- **Change Tracking**: Comprehensive audit trails of all modifications
- **Column Matching**: Automatic fuzzy matching and correction of column names
- **Model Optimization**: Intelligent assignment of AI models (sonar-pro default, Claude 4 for complex analysis)

## Architecture

### Core Components

1. **config_generator_conversational.py** - Main conversational system
2. **config_generator_step1.py** - Table analysis and prompt loading
3. **config_generator_step2_enhanced.py** - Enhanced config generation with validation
4. **prompts/conversational_interview_prompt.md** - External prompt template with variables

### Key Technical Features

- **Claude 4 API Integration** with structured tool responses
- **Asyncio/aiohttp** for efficient API calls with token tracking
- **Pandas** for Excel analysis and column inference
- **YAML-based external prompt system** with variable substitution
- **JSON Schema validation** using existing API logic
- **Fuzzy string matching** for column name correction
- **Configuration versioning** with automated file naming

## Usage

### Basic Configuration Generation

```bash
# Start new conversation with table analysis
python config_generator_conversational.py \
    --config example_config.json \
    --excel example_table.xlsx \
    --message "Generate an optimized config for this data validation scenario"

# Continue existing conversation
python config_generator_conversational.py \
    --conversation-id conv_12345678 \
    --message "Change field importance levels and optimize model assignments"
```

### API Key Setup

Create a file named `claude_api_key.txt` with your Claude API key, or set the `ANTHROPIC_API_KEY` environment variable.

### Configuration Structure

Generated configs follow this structure:
1. **General settings** (notes, default model, context size)
2. **Search groups** (organized field groupings with model assignments)
3. **Validation targets** (individual field configurations)
4. **Generation metadata** (timestamps, versions, token usage)
5. **Config change log** (comprehensive audit trail)

## Domain Adaptability

The system automatically adapts to different data domains:

- **Automatic domain detection** from table structure and content
- **Flexible importance assignment** based on data patterns
- **Context-aware model selection** for different field types
- **Customizable validation rules** for various business requirements

### Importance Levels

- **ID**: Primary identifiers for data tracking
- **CRITICAL**: Core business-critical fields requiring highest accuracy
- **HIGH**: Important strategic fields for business decisions
- **MEDIUM**: Supporting context and additional information
- **LOW**: Background information and supplementary data

### Model Assignments

- **sonar-pro**: Default for factual data, structured information
- **claude-sonnet-4-0**: Complex analysis requiring domain expertise

## Advanced Features

### Interview System

The system generates intelligent questions based on table analysis:
- Domain-specific questions based on detected data patterns
- 3-7 questions focused on optimization opportunities
- Sequential conversation support with context preservation

### Change Tracking

Every modification is tracked with:
- Timestamp and user message
- Specific config changes (type, column, old/new values)
- Reasoning for changes
- Validation results
- Version increments

### Validation Integration

Real-time validation using existing Perplexity Validator API:
- Importance level validation
- Search group consistency checks
- Required field verification
- Warning detection for optimization opportunities

### Column Name Matching

Automatic correction of column mismatches:
- Fuzzy string matching with 80% similarity threshold
- Case-insensitive exact matches
- Preservation of original Excel column names
- Warning system for unmatched columns

## File Organization

```
ai_config_generator/
├── README.md                                    # This documentation
├── config_generator_conversational.py          # Main system
├── config_generator_step1.py                   # Table analyzer
├── config_generator_step2_enhanced.py          # Enhanced generator
├── prompts/
│   ├── conversational_interview_prompt.md      # Main prompt template
│   └── generate_column_config_prompt.md        # Column config prompt
├── example_config.json                         # Sample configuration
└── example_table.xlsx                          # Sample Excel file
```

## Technical Requirements

- Python 3.7+
- pandas, aiohttp, pyyaml
- Claude API key (Anthropic)
- Access to Perplexity Validator codebase for validation integration

## Integration with Perplexity Validator

This configurator integrates with the existing Perplexity Validator system:

- Uses validation logic from `src/interface_lambda/actions/config_validation.py`
- Follows established JSON schema patterns
- Compatible with existing search group and model structures
- Maintains compatibility with current validation targets format

## Performance Optimization

- **Token Usage Tracking**: Monitors Claude API usage and costs
- **Model Selection**: Strategic use of Claude 4 only for complex analysis
- **Context Management**: Optimized conversation history for API efficiency
- **Parallel Processing**: Concurrent API calls where applicable
- **Caching**: 15-minute cache for repeated analyses

## Future Enhancements

- Support for additional domains beyond pharmaceutical
- Integration with more data sources (CSV, databases)
- Advanced analytics for configuration optimization
- Automated testing framework for generated configurations
- Integration with CI/CD pipelines for configuration validation

---

Generated with AI Configuration Generator for Perplexity Validator