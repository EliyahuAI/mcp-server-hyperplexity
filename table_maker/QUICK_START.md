# Table Generation System - Quick Start Guide

## ✅ System is Ready!

The standalone table generation system is complete and working. Here's how to use it:

---

## Prerequisites

1. **Python 3.8+** installed
2. **ANTHROPIC_API_KEY** environment variable set
3. **Dependencies installed** (see below)

---

## Installation

### 1. Install Dependencies

```bash
cd table_maker
pip install aioboto3 jsonschema pandas pytest pytest-asyncio
```

Or install from requirements file:
```bash
pip install -r requirements.txt
```

### 2. Set API Key

```bash
export ANTHROPIC_API_KEY='your-api-key-here'
```

---

## Running the CLI Demo

### From the Project Root

```bash
python table_maker/cli_demo.py
```

### Or From table_maker Directory

```bash
cd table_maker
python cli_demo.py
```

---

## Using the CLI

### 1. Start the Demo

When you run the CLI, you'll see:

```
==============================================================================
    TABLE GENERATION SYSTEM - INTERACTIVE DEMO
==============================================================================
[SUCCESS] ANTHROPIC_API_KEY found
[SUCCESS] System ready!

Start a new conversation to begin designing a table.
Type 'new' to start or 'quit' to exit.

>
```

### 2. Start a Conversation

Type `new` and describe your research table:

```
> new

Describe your research table. What data do you want to collect?

Your description: I want to track AI research papers on transformers,
including citation counts, publication venues, and key findings
```

### 3. Review AI Proposal

The AI will propose a table structure:

```
AI: I'll help you create a research paper tracking table. Here's my proposal:

Current Table Structure:
──────────────────────────────────────────────────────────

Columns (8):
  [ID] Paper Title
    Description: Full title of the research paper
    Format: String | Importance: N/A

  [ID] Authors
    Description: Primary authors of the paper
    Format: String | Importance: N/A

  Publication Year
    Description: Year the paper was published
    Format: Number | Importance: HIGH

  [... more columns ...]

Sample Rows (3):
  Row 1:
    Paper Title: Attention Is All You Need
    Authors: Vaswani et al.
    ...
```

### 4. Refine the Design

Use commands to interact:

**Available Commands:**
- `continue` - Provide feedback to refine
- `expand` - Add more sample rows
- `generate` - Create CSV and config files
- `show` - Display current structure
- `history` - View conversation log
- `new` - Start over
- `quit` - Exit

**Example refinement:**
```
> continue
Your feedback: Add a column for "Key Contribution" with HIGH importance

AI: I've added the "Key Contribution" column...
[Updated table shown]
```

**Example row expansion:**
```
> expand
Expansion request: Add 10 papers about vision transformers
Number of rows to generate: 10

[SUCCESS] Generated 10 new rows
```

### 5. Generate Output Files

When satisfied with the design:

```
> generate

[INFO] Generating CSV file...
[SUCCESS] CSV generated: output/table_20251013_194522.csv
  Rows: 13, Columns: 8

[INFO] Generating validation config...
[SUCCESS] Config generated: output/config_20251013_194522.json

[INFO] Saving conversation history...
[SUCCESS] Conversation saved: output/conversation_20251013_194522.json

Generation Summary
──────────────────────────────────────────────────────────
[SUCCESS] All outputs generated successfully!

Output files:
  CSV:          output/table_20251013_194522.csv
  Config:       output/config_20251013_194522.json
  Conversation: output/conversation_20251013_194522.json
```

---

## Output Files

All generated files are saved to `table_maker/output/`:

### 1. CSV File (`table_YYYYMMDD_HHMMSS.csv`)

Research table with:
- Metadata comments at top
- Column definitions
- All sample rows
- UTF-8 encoded

### 2. Config File (`config_YYYYMMDD_HHMMSS.json`)

Validation configuration with:
- Search groups (by importance)
- Validation targets for each column
- Model assignments
- General notes

### 3. Conversation Log (`conversation_YYYYMMDD_HHMMSS.json`)

Complete conversation history with:
- All user messages
- All AI responses
- Table proposals at each turn
- Timestamps and metadata

### 4. Logs

Execution logs saved to `output/logs/` with:
- API calls and responses
- Token usage
- Errors and warnings
- Timing information

---

## Example Session

```bash
$ python table_maker/cli_demo.py

[System initializes...]

> new
Your description: Track startup funding rounds

AI: I'll create a startup funding tracker...
[Proposes table with Company, Round Type, Amount, Lead Investor, etc.]

> continue
Your feedback: Add valuation column with HIGH importance

AI: I've added the Valuation column...
[Shows updated table]

> expand
Expansion request: Add 5 YC startups from 2024
Number of rows: 5

[SUCCESS] Generated 5 new rows

> show
[Displays full table structure with all 8 rows]

> generate
[SUCCESS] All outputs generated!

> quit
Thank you for using the Table Generation System!
```

---

## Tips

1. **Be Specific** - Clear descriptions lead to better table designs
2. **Iterate** - Use `continue` multiple times to refine
3. **Expand Strategically** - Add diverse rows to improve config quality
4. **Save Often** - Use `generate` periodically to checkpoint progress
5. **Check Logs** - Look in `output/logs/` if something unexpected happens

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'X'"

Install dependencies:
```bash
pip install aioboto3 jsonschema pandas
```

### "ANTHROPIC_API_KEY not found"

Set your API key:
```bash
export ANTHROPIC_API_KEY='sk-ant-...'
```

### "No such file or directory: prompts"

Run from project root or table_maker directory, not from tests/ or src/

### Import errors

Make sure you're running Python 3.8 or higher:
```bash
python --version
```

---

## Running Tests

### Unit Tests (Mocked, No API Calls)

```bash
cd table_maker
pytest tests/ -v -m "not integration"
```

### Integration Tests (Real API Calls, Costs ~$0.65)

```bash
export ANTHROPIC_API_KEY='your-key'
pytest tests/test_integration.py -v -s
```

---

## Next Steps

Once you're familiar with the CLI demo:

1. **Explore the code** in `src/` to understand the architecture
2. **Review generated configs** to see how they map to your needs
3. **Try different research scenarios** to test flexibility
4. **Read the integration docs** for lambda deployment (coming next)

---

## Support

- **Documentation:** See `README.md`, `CLI_DEMO_USAGE.md`, `TESTING.md`
- **Requirements:** See `docs/TABLE_GENERATION_REQUIREMENTS.md`
- **Implementation:** See `IMPLEMENTATION_COMPLETE.md`

---

**Enjoy creating research tables with AI! 🚀**
