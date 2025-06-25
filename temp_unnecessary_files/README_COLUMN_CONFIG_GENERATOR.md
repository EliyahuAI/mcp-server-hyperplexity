# Column Config Generator System

This system helps you generate simplified `column_config.json` files for AI-powered table validation using Perplexity. The generated configurations use our streamlined format that eliminates redundancy while maintaining full functionality.

## 🎯 Purpose

Transform any Excel or CSV table into a properly configured validation system by:
1. **Analyzing** table structure and data patterns
2. **Asking clarifying questions** about business requirements
3. **Generating** a simplified `column_config.json` file

## 📁 Files Overview

### Prompts
- **`prompts/column_config_generator.txt`** - Concise prompt for direct AI use
- **`prompts/generate_column_config_prompt.md`** - Detailed prompt with full instructions
- **`examples/sample_table_analysis.md`** - Complete example walkthrough

### Simplified Configuration Format
- **`tables/RatioCompetitiveIntelligence/column_config_simplified.json`** - Real example
- **`src/schema_validator_simplified.py`** - Validator for simplified format

## 🚀 How to Use

### Option 1: Direct AI Prompt
Copy the content from `prompts/column_config_generator.txt` and use it with any AI assistant:

```
[Paste prompt content]

Here's my table file: [attach Excel/CSV]
```

### Option 2: Detailed Analysis
Use `prompts/generate_column_config_prompt.md` for more comprehensive analysis and guidance.

## 📋 Generated Configuration Structure

The simplified format eliminates redundancy while maintaining all essential features:

```json
{
  "general_notes": "Table purpose, validation guidelines, and preferred sources for information",
  "default_model": "sonar-pro",
  "validation_targets": [
    {
      "column": "Column Name",
      "description": "What this column contains",
      "importance": "ID|CRITICAL|HIGH|MEDIUM|LOW|IGNORED",
      "format": "String|Date|Number|URL|etc.",
      "notes": "Formatting rules and validation guidelines",
      "examples": ["example1", "example2", "example3"],
      "search_group": 0,
      "preferred_model": "model-name" // Optional override
    }
  ]
}
```

## 🔍 Analysis Process

### 1. General Notes & Context Questions
- Primary purpose and domain
- Update frequency
- Main use cases
- Preferred sources for validation

### 2. Unique Identifiers
- Which columns uniquely identify rows
- Priority order for composite identifiers

### 3. Column Classification
For each column:
- **Importance level** (ID, CRITICAL, HIGH, MEDIUM, LOW, IGNORED)
- **Data format** (String, Date, Number, URL, etc.)
- **Formatting rules** and validation requirements
- **Example values** (3-5 realistic examples)

### 4. Search Grouping Strategy
- **Group 0**: ID/identifier fields (not validated, used for context)
- **Groups 1+**: Information typically found together in same sources
- **No upper limit** on group numbers
- **Ungrouped fields**: Validated individually (more expensive, less stable)
- **Processing order**: Ungrouped columns processed in order of entry

### 5. Model Selection
- Default model (sonar-pro)
- Per-field model overrides if needed

## 📊 Example Output

See `examples/sample_table_analysis.md` for a complete walkthrough showing:
- Sample pharmaceutical products table
- Interactive questioning process
- Generated simplified configuration
- Key features demonstration

## 🛠 Validation

The generated config works with `src/schema_validator_simplified.py`:

```python
from src.schema_validator_simplified import SimplifiedSchemaValidator

# Load generated config
validator = SimplifiedSchemaValidator(config)

# Features
print(f"ID fields: {[f.column for f in validator.get_id_fields()]}")
print(f"Default model: {validator.default_model}")
print(f"Search groups: {validator.group_by_search_group()}")
```

## 🎯 Benefits

1. **Eliminates redundancy** - Clean, streamlined structure
2. **Flexible grouping** - No upper limit on search groups
3. **Simplified maintenance** - Fewer fields to manage
4. **Model flexibility** - Default with per-field overrides
5. **Clear structure** - Logical grouping and validation guidance
6. **Source specification** - Preferred sources in general_notes

## 🚀 Getting Started

1. Choose your prompt file based on needs
2. Provide your table file to an AI assistant
3. Answer the clarifying questions about context and preferred sources
4. Specify which columns contain information found together
5. Receive your simplified `column_config.json`
6. Use with the simplified validator system

The system transforms any table into a properly configured AI validation setup with minimal effort and maximum clarity! 