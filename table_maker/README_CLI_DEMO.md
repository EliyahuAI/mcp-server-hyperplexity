# Table Generation CLI Demo - Quick Start

Interactive CLI for designing research tables through natural conversation with AI.

## Quick Start

```bash
# Set API key (required)
export ANTHROPIC_API_KEY='your-api-key-here'

# Run the demo (option 1: use script)
./run_demo.sh

# Run the demo (option 2: direct)
python3.exe cli_demo.py
```

## File Locations

- **Main CLI**: `cli_demo.py`
- **Launch Script**: `run_demo.sh`
- **Full Documentation**: `CLI_DEMO_USAGE.md`
- **Output Directory**: `output/`

## Commands

| Command | Description |
|---------|-------------|
| `new` | Start a new table design conversation |
| `continue` | Provide feedback to refine the table |
| `expand` | Generate additional sample rows |
| `generate` | Create CSV and config files |
| `show` | Display current table structure |
| `history` | View conversation history |
| `quit` | Exit the demo |

## Example Session

```
# Start
> new
Your description: Create a table for tracking AI research papers with
title, authors, year, venue, and impact factor.

# AI proposes table structure

# Refine
> continue
Your feedback: Add a column for methodology and mark title as ID column.

# AI updates structure

# Expand
> expand
Expansion request: Add 10 papers about transformers from 2023-2024.
Number of rows: 10

# AI generates 10 sample rows

# Generate outputs
> generate

# Files created:
# - output/table_20241013_143022.csv
# - output/config_20241013_143022.json
# - output/conversation_20241013_143022.json
```

## Features

- **Conversational Design**: Describe tables in natural language
- **AI-Powered**: Claude generates intelligent table structures
- **Iterative Refinement**: Continuous feedback loop
- **Row Expansion**: AI generates diverse sample data
- **Auto Config Generation**: Creates validation configs automatically
- **Full History**: Saves complete conversation logs
- **Colored Output**: Easy-to-read terminal interface

## Output Files

Generated in `output/` directory:

1. **CSV File**: Complete table with metadata comments
2. **Config File**: AI validation configuration (JSON)
3. **Conversation Log**: Full interaction history (JSON)
4. **Log Files**: Detailed execution logs in `output/logs/`

## Requirements

- Python 3.8+
- ANTHROPIC_API_KEY environment variable
- Required Python packages:
  - `anthropic` - Anthropic API client
  - `jsonschema` - JSON schema validation
  - Standard library modules (asyncio, json, logging, etc.)

### Installing Dependencies

If you encounter import errors:

```bash
# Install required packages
pip install anthropic jsonschema

# Or if using project requirements
pip install -r requirements.txt
```

## Tips

1. **Be specific** in your initial table description
2. **Use importance levels**: CRITICAL, HIGH, MEDIUM, LOW
3. **Mark identification columns** (the subjects being researched)
4. **Expand in batches** (10-20 rows at a time)
5. **Review before generating** with the `show` command

## Troubleshooting

**No API key error?**
```bash
export ANTHROPIC_API_KEY='your-key'
```

**Import errors?**
```bash
# Run from project root
cd /path/to/perplexityValidator
python3.exe table_maker/cli_demo.py
```

**Slow responses?**
- AI calls take 5-30 seconds (normal)
- Check `output/logs/` for progress

## Documentation

- **Detailed Guide**: See `CLI_DEMO_USAGE.md` for complete documentation
- **Architecture**: See `docs/INFRASTRUCTURE_GUIDE.md` for system overview
- **Schemas**: Check `schemas/` for data structures
- **Prompts**: Review `prompts/` for AI templates

## Demo Workflow

```
Start → Design Table → Refine → Expand Rows → Generate Files
  ↑         ↓            ↓         ↓            ↓
  └─────────────────────┴─────────┴────────────┘
         (Iterate as needed)
```

---

**For detailed usage instructions, see `CLI_DEMO_USAGE.md`**
