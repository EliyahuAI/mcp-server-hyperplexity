# Schema Separation Guide

This document explains how schemas are properly separated between different use cases in the Perplexity Validator system.

## The Problem

Previously, we had confusion between two different use cases that both need to validate column configurations:

1. **Config Validation** (Interface Lambda) - Validates that user-provided configs are structurally correct
2. **AI Generation** (Config Lambda) - Enforces that AI responses include both valid configs AND required feedback

## The Solution

We now have a clean separation with shared base schema + specific extensions:

### 1. Base Column Config Schema
**File**: `config_lambda/column_config_schema.json`
**Purpose**: Defines the structure of a valid column configuration
**Used by**: 
- Config Lambda (as part of AI generation schema)
- Interface Lambda (via hardcoded validation logic in `config_validation.py`)

**Structure**:
```json
{
  "type": "object",
  "required": ["search_groups", "validation_targets"],
  "properties": {
    "general_notes": {...},
    "default_model": {...},
    "search_groups": {...},
    "validation_targets": {...}
  }
}
```

### 2. AI Generation Schema Extension
**File**: `config_lambda/ai_generation_schema.json`
**Purpose**: Defines additional fields required from AI responses
**Used by**: Config Lambda only

**Structure**:
```json
{
  "required": ["clarifying_questions", "clarification_urgency", "reasoning", "ai_summary"],
  "properties": {
    "clarifying_questions": {...},
    "clarification_urgency": {...},
    "reasoning": {...},
    "ai_summary": {...}
  }
}
```

### 3. Combined AI Generation Schema
**Function**: `config_lambda_function.py::get_unified_generation_schema()`
**Purpose**: Combines base config schema + AI feedback requirements
**Used by**: Config Lambda when calling Claude API

**Structure**:
```json
{
  "type": "object",
  "required": ["updated_config", "clarifying_questions", "clarification_urgency", "reasoning", "ai_summary"],
  "properties": {
    "updated_config": {
      // Full column_config_schema.json here
    },
    "clarifying_questions": {...},
    "clarification_urgency": {...},
    "reasoning": {...},
    "ai_summary": {...}
  }
}
```

## Usage Patterns

### Interface Lambda - Config Validation
**Purpose**: Validate user-uploaded configs for structural correctness
**Location**: `src/interface_lambda/actions/config_validation.py`
**Method**: Hardcoded validation logic (not JSON schema)
**Validates**: Pure column config structure only

```python
def validate_config_structure(config_data):
    # Validates search_groups, validation_targets, etc.
    # Does NOT require AI feedback fields
    return is_valid, errors, warnings
```

### Config Lambda - AI Generation
**Purpose**: Ensure AI responses include valid config + required feedback
**Location**: `config_lambda/config_lambda_function.py`
**Method**: Combined JSON schema enforcement
**Validates**: Column config + AI feedback fields

```python
def get_unified_generation_schema():
    # Loads column_config_schema.json
    # Loads ai_generation_schema.json  
    # Combines them for AI API calls
    return combined_schema
```

## Benefits

1. **Single Source of Truth**: `column_config_schema.json` defines the config structure
2. **Clean Separation**: Interface validation vs AI generation requirements are separate
3. **No Duplication**: AI schema extends base schema rather than duplicating it
4. **Maintainable**: Changes to config structure only need to be made in one place
5. **Flexible**: Each use case can have its own validation approach while sharing the base schema

## File Locations

```
src/
├── column_config_schema.json      # Base config structure (shared)
├── config_validator.py            # Shared validation functions (shared)

config_lambda/
├── ai_generation_schema.json      # AI feedback requirements (config lambda only)
└── config_lambda_function.py      # Combines schemas for AI generation

src/interface_lambda/actions/
└── config_validation.py           # Uses shared config_validator
```

## Deployment

**Shared Resources** (copied to both lambdas):
- `column_config_schema.json` - Base configuration schema
- `config_validator.py` - Validation functions with table matching
- `ai_api_client.py` - AI API client
- `shared_table_parser.py` - Table parsing utilities

**Config Lambda Specific**:
- `ai_generation_schema.json` - AI feedback requirements

**Functions Available**:
- `validate_config_structure()` - Pure structural validation
- `validate_config_table_match()` - Table-config column matching
- `validate_config_complete()` - Combined validation
- `load_and_validate_config()` - Convenience function with JSON parsing