# Config Lambda - AI-Powered Configuration Generator

## Overview

The Config Lambda is an independent AWS Lambda function that generates optimal column configurations for the Perplexity Validator using AI. It implements a **unified architecture** that provides both configuration generation and clarifying questions in every response, with embedded conversation tracking for iterative improvements.

## Core Architecture

### Unified Generation Model
The system uses a single mode instead of separate automatic/interview modes:
- **Every call** includes table information + optional existing config + instructions
- **Every response** includes updated config + clarifying questions + urgency score
- **Conversation tracking** is embedded directly in config files via `config_change_log`

### Key Components

```
src/
├── config_lambda_function.py          # Main lambda handler with unified generation
├── ai_api_client.py                   # Shared AI API client (Claude + Perplexity)
├── shared_table_parser.py             # Unified S3 table parser (Excel/CSV)
├── column_config_schema.json          # JSON schema for config validation
└── interface_lambda/actions/
    ├── generate_config.py             # Config generation action handler
    └── ...

ai_config_generator/
├── prompts/
│   └── generate_column_config_prompt.md    # Updated prompt with mandatory search groups
└── config_generator_conversational.py     # Legacy conversational system
```

## API Contract

### Input Formats
The lambda accepts multiple table input formats:

1. **Excel S3 Key** (most common):
```json
{
  "excel_s3_key": "uploads/user_folder/table.xlsx",
  "existing_config": {...},  // Optional
  "instructions": "Generate config for pharmaceutical data"
}
```

2. **CSV S3 Key**:
```json
{
  "csv_s3_key": "uploads/user_folder/data.csv",
  "existing_config": {...},
  "instructions": "Optimize config for regulatory compliance"
}
```

3. **Direct Table Analysis** (pre-analyzed):
```json
{
  "table_analysis": {
    "basic_info": {...},
    "column_analysis": {...},
    "domain_info": {...}
  },
  "existing_config": {...},
  "instructions": "Focus on search group optimization"
}
```

### Output Format
**Every response** includes all four components:

```json
{
  "success": true,
  "updated_config": {
    "general_notes": "Configuration description...",
    "default_model": "sonar-pro",
    "default_search_context_size": "low",
    "search_groups": [...],           // MANDATORY - min 1 group
    "validation_targets": [...],      // All columns assigned to groups
    "config_change_log": [            // Embedded conversation history
      {
        "timestamp": "2025-01-17T...",
        "action": "unified_generation",
        "session_id": "config_gen_20250117_...",
        "instructions": "Generate config...",
        "clarifying_questions": "1. Should we prioritize...",
        "clarification_urgency": 0.7,
        "reasoning": "Updated search groups because...",
        "version": 3,
        "model_used": "claude-sonnet-4-5"
      }
    ],
    "generation_metadata": {
      "version": 3,
      "last_updated": "2025-01-17T...",
      "total_interactions": 3,
      "model_used": "claude-sonnet-4-5"
    }
  },
  "clarifying_questions": "1. Should we prioritize regulatory sources over company press releases?\n2. For the Status column, should this include regulatory milestones?\n3. What specific timeframe should we focus on for launch projections?",
  "clarification_urgency": 0.7,      // 0-1 scale
  "reasoning": "Updated search groups to separate regulatory and commercial data sources. Added theranostic-specific validation rules.",
  "config_s3_key": "generated_configs/session_123_20250117_142030.json",
  "session_id": "config_gen_20250117_142030_abc12345"
}
```

## Clarification Urgency Scale

The `clarification_urgency` field uses a 0-1 scale to indicate how critical clarification is:

- **0.0-0.1**: Configuration is solid, minimal clarification needed
- **0.2-0.3**: Minor improvements possible with clarification  
- **0.4-0.6**: Moderate improvements likely with clarification
- **0.7-0.9**: Important columns may have suboptimal settings
- **1.0**: Critical columns will likely be wrong without clarification

## Search Groups - Mandatory Architecture

### Why Search Groups Are Required
Search groups are **mandatory** for every configuration - they cannot be omitted because they are essential for:

- **Performance**: Grouped validation is faster than individual column validation
- **Consistency**: Related fields get validated together using the same sources
- **Cost Optimization**: Reduces API calls by batching related columns
- **Source Strategy**: Ensures fields that appear together in sources are searched together

### Search Group Structure
```json
"search_groups": [
  {
    "group_id": 0,
    "group_name": "Identification", 
    "description": "ID and identifier fields used for context",
    "model": "sonar-pro",
    "search_context": "low"
  },
  {
    "group_id": 1,
    "group_name": "Core Information",
    "description": "Main content fields that appear together in sources",
    "model": "sonar-pro", 
    "search_context": "low"
  }
]
```

### Search Group Assignment
- **Group 0**: Typically ID/identifier fields (not validated, used for context)
- **Group 1+**: Columns whose information appears together in typical sources
- **Every validation target** must be assigned to a search group via `search_group` field
- **No ungrouped fields allowed**: Every column must belong to a search group

## AI API Integration

### Shared AI Client
All Claude API calls use the centralized `ai_api_client.py` with features:
- **Structured responses** via tool calling with JSON schemas
- **S3 caching** for performance and cost optimization
- **Token usage tracking** for both Anthropic and Perplexity APIs
- **Error handling** and retry logic
- **Multiple provider support** (Claude, Perplexity)

### Model Usage
- **Primary model**: `claude-sonnet-4-5` for config generation
- **Alternative models**: `sonar-pro` for simpler validation tasks
- **Model selection**: Can be overridden per search group or validation target

### Structured Response Schema
All config generation uses structured JSON schema responses to ensure consistency:

```python
schema = {
    "type": "object",
    "properties": {
        "updated_config": {...},           # Complete config structure
        "clarifying_questions": {...},     # 2-4 specific questions  
        "clarification_urgency": {...},    # 0-1 scale
        "reasoning": {...}                 # Explanation of changes
    },
    "required": ["updated_config", "clarifying_questions", "clarification_urgency", "reasoning"]
}
```

## Table Processing

### S3 Table Parser
The `shared_table_parser.py` provides unified parsing for:
- **Excel files** (.xlsx, .xls) using openpyxl
- **CSV files** with automatic encoding detection
- **Sample analysis** for large files (first 20 rows)
- **Column type inference** (numeric, date, text)
- **Domain detection** (biotech, competitive intelligence, financial)

### Analysis Output
```json
{
  "basic_info": {
    "filename": "competitive_intelligence.xlsx",
    "shape": [150, 12],
    "column_names": ["Product Name", "Developer", "Target", ...],
    "sample_rows_analyzed": 20
  },
  "column_analysis": {
    "Product Name": {
      "data_type": "Text",
      "non_null_count": 18,
      "unique_count": 18,
      "sample_values": ["FAP-2286", "225Ac-PSMA-617", ...],
      "fill_rate": 0.9
    }
  },
  "domain_info": {
    "likely_domain": "biotech",
    "domain_scores": {"biotech": 8, "competitive_intelligence": 5},
    "confidence": 0.67
  }
}
```

## Conversation Tracking

### Embedded History
Instead of external conversation storage, the system embeds conversation history directly in config files:

```json
"config_change_log": [
  {
    "timestamp": "2025-01-17T14:20:30Z",
    "action": "unified_generation",
    "session_id": "config_gen_20250117_142030_abc12345",
    "instructions": "Generate initial config for radiopharmaceutical data",
    "clarifying_questions": "1. Should we prioritize FDA databases over company press releases?",
    "clarification_urgency": 0.6,
    "reasoning": "Created search groups based on regulatory vs commercial data sources",
    "version": 1,
    "model_used": "claude-sonnet-4-5"
  },
  {
    "timestamp": "2025-01-17T14:25:15Z", 
    "action": "unified_generation",
    "session_id": "config_gen_20250117_142515_def67890",
    "instructions": "Focus more on regulatory milestones and approval timelines",
    "clarifying_questions": "1. Should launch projections include partnership delays?",
    "clarification_urgency": 0.3,
    "reasoning": "Enhanced regulatory search group with FDA milestone tracking",
    "version": 2,
    "model_used": "claude-sonnet-4-5"
  }
]
```

### Metadata Tracking
```json
"generation_metadata": {
  "version": 2,
  "last_updated": "2025-01-17T14:25:15Z",
  "total_interactions": 2,
  "model_used": "claude-sonnet-4-5"
}
```

## Deployment and Testing

### Deployment Structure
```
deployment/
├── create_package.py              # Main lambda package creation
├── config_package/               # Config lambda specific files
│   ├── ai_api_client.py
│   ├── config_lambda_function.py
│   ├── shared_table_parser.py
│   └── requirements.txt
└── requirements-lambda.txt        # Lambda dependencies
```

### Testing
Use the comprehensive test suite:

```bash
# Test all functionality
python test_config_lambda.py --test-all

# Test specific features
python test_config_lambda.py --test-generate     # Basic generation
python test_config_lambda.py --test-interview    # Interview responses  
python test_config_lambda.py --test-modify       # Config modification
python test_config_lambda.py --test-websocket    # WebSocket delivery
```

## Error Handling

### Common Error Scenarios
1. **Missing table data**: Returns 400 with clear error message
2. **Table parsing failures**: Detailed error with file format issues
3. **AI API failures**: Cached responses when possible, structured error reporting
4. **S3 access issues**: Proper IAM permission guidance
5. **Schema validation**: Clear validation error messages

### Error Response Format
```json
{
  "success": false,
  "error": "Table analysis failed: Unsupported file format: example.pdf",
  "session_id": "config_gen_20250117_142030_abc12345"
}
```

## Performance Optimization

### Caching Strategy
- **S3-based caching** for AI API responses
- **Cache keys** include prompt, model, schema, and context
- **Separate cache prefixes** for Claude vs Perplexity responses
- **Token usage tracking** for cost monitoring

### Async Processing
- **SQS queuing** for long-running config generation
- **WebSocket delivery** for real-time progress updates
- **Background processing** prevents timeout issues

## Integration Points

### Interface Lambda
The config lambda integrates with the main interface lambda via:
- **HTTP endpoints** for direct config generation
- **SQS messaging** for async processing
- **WebSocket notifications** for progress updates
- **S3 storage** for config persistence

### WebSocket Flow
1. Client uploads table via interface lambda
2. Interface lambda queues config generation request
3. Config lambda processes request asynchronously  
4. Results delivered via WebSocket to client
5. Config saved to S3 for future access

## Configuration Schema

The system validates all configurations against `column_config_schema.json`:
- **Required fields**: search_groups, validation_targets
- **Search group validation**: Mandatory minimum 1 group
- **Column assignment validation**: All targets must reference valid search groups
- **Format validation**: Proper importance levels, data types, etc.

## Usage Examples

### Basic Generation
```python
# Generate config from Excel file
result = await generate_config_unified(
    table_analysis=None,  # Will be generated from S3 key
    existing_config=None,
    instructions="Generate optimal configuration for pharmaceutical competitive intelligence",
    session_id="config_gen_20250117_142030_abc12345",
    excel_s3_key="uploads/user_folder/pharma_data.xlsx"
)
```

### Iterative Improvement
```python
# Improve existing config
result = await generate_config_unified(
    table_analysis=existing_analysis,
    existing_config=current_config,  # Contains previous conversation history
    instructions="Focus more on regulatory timelines and reduce commercial emphasis",
    session_id="config_gen_20250117_143045_def67890"
)
```

This unified architecture provides a robust, scalable, and user-friendly approach to AI-powered configuration generation with embedded conversation tracking and flexible input/output formats.