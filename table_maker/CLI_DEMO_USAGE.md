# Table Generation System - CLI Demo Usage Guide

## Overview

The interactive CLI demo demonstrates the conversational table generation system. It allows you to design research tables through natural conversation with AI, expand rows, and generate CSV files with validation configs.

## File Location

```
/mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator/table_maker/cli_demo.py
```

## Prerequisites

1. **Python 3.8+** with asyncio support
2. **ANTHROPIC_API_KEY** environment variable set
3. **Required dependencies** installed (see requirements below)

## Installation & Setup

### 1. Set API Key

```bash
export ANTHROPIC_API_KEY='your-api-key-here'
```

For permanent setup, add to your `~/.bashrc` or `~/.zshrc`:
```bash
echo "export ANTHROPIC_API_KEY='your-api-key-here'" >> ~/.bashrc
source ~/.bashrc
```

### 2. Install Dependencies

The CLI requires these Python packages:

```bash
# Required packages
pip install anthropic jsonschema

# Or install from project requirements
pip install -r requirements.txt
```

**Required packages:**
- `anthropic` - Anthropic API client (for AI calls)
- `jsonschema` - JSON schema validation (for response validation)
- Standard library: `asyncio`, `json`, `logging`, `pathlib` (built-in)

## Running the Demo

### Basic Usage

```bash
# From the table_maker directory
python3.exe cli_demo.py

# Or use as executable
./cli_demo.py
```

### From Project Root

```bash
python3.exe table_maker/cli_demo.py
```

## Features & Commands

### Starting a New Conversation

1. Type `new` at the prompt
2. Describe your research table requirements
3. The AI will propose an initial table structure

**Example prompts:**
```
"I need a table to track scientific papers on machine learning.
Include columns for title, authors, publication year, impact factor,
and key findings."

"Create a table for tracking clinical trials with trial ID,
drug name, phase, start date, participant count, and outcomes."

"Design a table to compare different AI models with their names,
parameters, accuracy, speed, and use cases."
```

### Available Commands

Once a conversation is active:

- **`continue`** - Provide feedback to refine the table
  - Add or remove columns
  - Change column properties (importance, format, etc.)
  - Adjust sample rows
  - Signal when ready to generate

- **`expand`** - Generate additional sample rows
  - Specify expansion criteria
  - Choose number of rows to generate
  - AI generates diverse, relevant samples

- **`generate`** - Create final outputs
  - CSV file with table data
  - JSON validation config
  - Conversation history log

- **`show`** - Display current table structure
  - Shows all columns with properties
  - Lists sample rows
  - Indicates identification columns

- **`history`** - View conversation log
  - Full conversation transcript
  - Timestamps for each turn
  - Both user and AI messages

- **`new`** - Start fresh conversation
  - Discards current work (with confirmation)
  - Resets to clean state

- **`quit`** - Exit the demo
  - Graceful shutdown
  - Ctrl+C also works (with confirmation)

## Workflow Examples

### Example 1: Simple Table Creation

```
> new
Your description: Create a table to track books with title, author,
publication year, genre, and rating.

[AI proposes table structure]

> continue
Your feedback: Add a column for ISBN and make the rating importance HIGH.

[AI updates structure]

> continue
Your feedback: Looks good, ready to generate.

[AI confirms readiness]

> generate

[Files created in output/ directory]
```

### Example 2: Advanced Workflow with Row Expansion

```
> new
Your description: Table for academic conferences with name, location,
dates, focus area, and acceptance rate.

[AI proposes table with 3-5 sample rows]

> expand
Expansion request: Add 10 more conferences covering different CS areas.
Number of rows: 10

[AI generates 10 diverse conference entries]

> show

[Displays full table with all rows]

> continue
Your feedback: Change acceptance rate importance to CRITICAL and
add a column for average attendance.

[AI updates structure]

> generate

[Complete table with ~15 rows exported]
```

### Example 3: Iterative Refinement

```
> new
Your description: Research table for tracking AI research papers.

> continue
Add columns for methodology and dataset used.

> continue
Change the format of publication year to Integer.

> continue
Mark title and DOI as identification columns.

> show

> expand
Add 5 papers about transformers published in 2023.
Number of rows: 5

> continue
Perfect, ready to generate!

> generate
```

## Output Files

All outputs are saved to: `table_maker/output/`

### Generated Files

1. **CSV File** (`table_YYYYMMDD_HHMMSS.csv`)
   - Complete table with headers and data
   - Metadata comments at top
   - Column descriptions in comments
   - Ready for import into analysis tools

2. **Config File** (`config_YYYYMMDD_HHMMSS.json`)
   - AI validation configuration
   - Search groups by importance
   - Validation targets for each column
   - Ready to use with validation system

3. **Conversation Log** (`conversation_YYYYMMDD_HHMMSS.json`)
   - Full conversation history
   - All user inputs and AI responses
   - Table evolution over time
   - Useful for audit and reproduction

4. **Log File** (`logs/cli_demo_YYYYMMDD_HHMMSS.log`)
   - Detailed execution log
   - API call information
   - Error traces if any
   - Token usage statistics

## Tips & Best Practices

### Designing Effective Tables

1. **Be specific in initial description**
   - Mention the research purpose
   - List key data points to track
   - Indicate any special requirements

2. **Use importance levels strategically**
   - CRITICAL: Absolutely must be validated
   - HIGH: Important but not critical
   - MEDIUM: Standard importance (default)
   - LOW: Nice to have, less critical

3. **Mark identification columns**
   - These define what you're researching
   - Not included in validation targets
   - Examples: Paper title, Trial ID, Product name

4. **Iterative refinement**
   - Start simple, add complexity gradually
   - Review AI proposals carefully
   - Use 'show' command frequently

### Row Expansion

1. **Start with good samples**
   - Initial conversation generates 3-5 rows
   - These serve as examples for expansion

2. **Be specific in expansion requests**
   - Good: "Add 10 papers about NLP from 2023-2024"
   - Avoid: "Add more rows"

3. **Use batches for large tables**
   - Expand 10-20 rows at a time
   - Review quality before expanding more

### Generating Outputs

1. **Wait until ready**
   - AI signals when design is complete
   - Can override, but design may be incomplete

2. **Save conversation history**
   - Automatically saved with generate command
   - Useful for understanding decisions

3. **Review CSV structure**
   - Open in spreadsheet tool
   - Verify data quality
   - Check metadata comments

## Troubleshooting

### API Key Issues

```
[ERROR] ANTHROPIC_API_KEY not found
```
**Solution:** Set the environment variable:
```bash
export ANTHROPIC_API_KEY='your-key'
```

### Import Errors

```
ModuleNotFoundError: No module named 'table_maker'
```
**Solution:** Run from correct directory or set PYTHONPATH:
```bash
cd /path/to/perplexityValidator
python3.exe table_maker/cli_demo.py
```

### Long Response Times

- AI calls can take 5-30 seconds
- This is normal for complex table designs
- Check logs for progress

### Validation Warnings

```
[WARNING] Generated config has validation warnings
```
- Usually non-critical
- Check log file for details
- Config still usable in most cases

## Advanced Usage

### Custom Output Directory

Edit `cli_demo.py` line 88:
```python
self.output_dir = Path("/your/custom/path")
```

### Adjust Model Parameters

Edit conversation calls to change:
- `model`: "claude-sonnet-4-5" (default)
- `temperature`: 0.3 for consistency, 0.7 for creativity
- `max_tokens`: 8000 (default)

### Enable Verbose Logging

In `cli_demo.py`, change line 76:
```python
level=logging.DEBUG,  # Instead of INFO
```

## System Architecture

The CLI demo integrates these components:

```
cli_demo.py
├── TableConversationHandler (conversation_handler.py)
│   ├── Manages conversation state
│   ├── Calls AI for proposals
│   └── Tracks conversation history
├── RowExpander (row_expander.py)
│   ├── Generates additional rows
│   ├── Merges with existing data
│   └── Handles deduplication
├── TableGenerator (table_generator.py)
│   ├── Exports to CSV format
│   ├── Adds metadata comments
│   └── Validates structure
├── ConfigGenerator (config_generator.py)
│   ├── Generates validation configs
│   ├── Creates search groups
│   └── Maps columns to targets
└── AIAPIClient (ai_api_client.py)
    └── Handles Anthropic API calls
```

## Color Output

The CLI uses ANSI color codes for better readability:
- **Blue**: Headers and sections
- **Green**: Success messages and commands
- **Yellow**: Warnings and prompts
- **Red**: Errors
- **Cyan**: AI responses and info

If colors don't display properly, your terminal may not support ANSI codes.

## Examples of Generated Configs

The validation configs follow this structure:

```json
{
  "general_notes": "Configuration for research validation...",
  "default_model": "sonar-pro",
  "search_groups": [
    {
      "group_id": 1,
      "group_name": "Critical Validation",
      "model": "claude-sonnet-4-5"
    }
  ],
  "validation_targets": [
    {
      "column": "impact_factor",
      "importance": "CRITICAL",
      "search_group": 1
    }
  ]
}
```

## Support & Documentation

- **Project docs**: `docs/INFRASTRUCTURE_GUIDE.md`
- **Component docs**: Individual source files in `table_maker/src/`
- **Schema docs**: `table_maker/schemas/`
- **Prompt templates**: `table_maker/prompts/`

## Exit & Cleanup

The CLI handles cleanup automatically:
- Saves state before exit
- Logs all operations
- No manual cleanup needed

To force exit: Ctrl+C twice

## Conclusion

This CLI demo provides a hands-on way to explore the table generation system's capabilities. It demonstrates:

1. Natural language table design
2. Iterative refinement through conversation
3. AI-powered row generation
4. Automatic validation config creation
5. Complete data export pipeline

Experiment with different table types and use cases to understand the system's flexibility and power.
