#!/usr/bin/env python3
"""
Demo script to showcase the QC Layer functionality.

This demonstrates the QC review process with mock data to show how it works
without requiring API calls.

Run with:
    python table_maker/demo_qc_layer.py
"""

import json
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from prompt_loader import PromptLoader
from schema_validator import SchemaValidator


def demo_qc_schema():
    """Demonstrate QC schema validation."""
    print("\n" + "=" * 80)
    print("DEMO: QC Review Response Schema")
    print("=" * 80)

    # Load schema validator
    schema_validator = SchemaValidator(
        schemas_dir=str(Path(__file__).parent / "schemas")
    )

    # Load QC schema
    schema = schema_validator.load_schema('qc_review_response')

    print("\nQC Review Response Schema loaded successfully!")
    print(f"Required fields: {schema.get('required', [])}")
    print(f"Properties: {list(schema.get('properties', {}).keys())}")

    # Create example QC response
    example_response = {
        "reviewed_rows": [
            {
                "id_values": {"Company Name": "Anthropic", "Website": "https://anthropic.com"},
                "row_score": 0.95,
                "qc_score": 0.98,
                "qc_rationale": "Perfect match - leading AI safety company with active hiring",
                "keep": True,
                "priority_adjustment": "promote"
            },
            {
                "id_values": {"Company Name": "OpenAI", "Website": "https://openai.com"},
                "row_score": 0.92,
                "qc_score": 0.94,
                "qc_rationale": "Excellent match - major AI research organization",
                "keep": True,
                "priority_adjustment": "none"
            },
            {
                "id_values": {"Company Name": "Generic Corp", "Website": "https://generic.com"},
                "row_score": 0.68,
                "qc_score": 0.25,
                "qc_rationale": "Not an AI company, off-topic",
                "keep": False,
                "priority_adjustment": "none"
            }
        ],
        "rejected_rows": [
            {
                "id_values": {"Company Name": "Generic Corp", "Website": "https://generic.com"},
                "rejection_reason": "Not an AI company, off-topic"
            }
        ],
        "qc_summary": {
            "total_reviewed": 3,
            "kept": 2,
            "rejected": 1,
            "promoted": 1,
            "demoted": 0,
            "reasoning": "Rejected 1 off-topic entry, promoted 1 exceptional fit"
        }
    }

    # Validate example response
    validation_result = schema_validator.validate_ai_response(
        example_response,
        'qc_review_response'
    )

    print(f"\nExample response validation: {'[SUCCESS] Valid' if validation_result['is_valid'] else '[ERROR] Invalid'}")
    if not validation_result['is_valid']:
        print(f"Errors: {validation_result['errors']}")

    print("\n" + json.dumps(example_response, indent=2))


def demo_qc_prompt():
    """Demonstrate QC prompt template."""
    print("\n" + "=" * 80)
    print("DEMO: QC Review Prompt Template")
    print("=" * 80)

    # Load prompt loader
    prompt_loader = PromptLoader(
        prompts_dir=str(Path(__file__).parent / "prompts")
    )

    # Define variables
    variables = {
        'TABLE_NAME': 'AI Companies Hiring',
        'USER_REQUIREMENTS': 'Find AI companies that are actively hiring',
        'COLUMN_DEFINITIONS': '''
- **Company Name** (id): Name of the AI company
- **Website** (id): Company website URL
- **Is Hiring** (research): Whether actively hiring
- **Recent Funding** (research): Recent funding rounds
        '''.strip(),
        'ROW_COUNT': '3',
        'DISCOVERED_ROWS': '''
**Row 1:**
- ID: Company Name: Anthropic, Website: https://anthropic.com
- Discovery Score: 0.95
- Rationale: Leading AI safety research company with active job postings
- Found by: sonar-pro(high)
- Source: AI Research Companies

**Row 2:**
- ID: Company Name: OpenAI, Website: https://openai.com
- Discovery Score: 0.92
- Rationale: Major AI company developing GPT models, multiple job openings
- Found by: sonar(high), sonar-pro(high)
- Source: AI Research Companies

**Row 3:**
- ID: Company Name: Generic Corp, Website: https://generic.com
- Discovery Score: 0.68
- Rationale: General consulting firm that mentions AI in blog posts
- Found by: sonar(low)
- Source: General Business
        '''.strip()
    }

    # Load and process prompt
    prompt = prompt_loader.load_prompt('qc_review', variables)

    print("\nQC Review Prompt generated successfully!")
    print(f"Prompt length: {len(prompt)} characters")
    print("\nPrompt preview (first 800 chars):")
    print("-" * 80)
    print(prompt[:800])
    print("-" * 80)
    print("... (truncated)")


def demo_qc_config():
    """Demonstrate QC configuration."""
    print("\n" + "=" * 80)
    print("DEMO: QC Configuration")
    print("=" * 80)

    # Load config
    config_path = Path(__file__).parent / "table_maker_config.json"
    with open(config_path, 'r') as f:
        config = json.load(f)

    qc_config = config.get('qc_review', {})

    print("\nQC Review Configuration:")
    print(f"  Model: {qc_config.get('model')}")
    print(f"  Max Tokens: {qc_config.get('max_tokens')}")
    print(f"  Min QC Score: {qc_config.get('min_qc_score')}")
    print(f"  Min Row Count: {qc_config.get('min_row_count')}")
    print(f"  Max Row Count: {qc_config.get('max_row_count')}")
    print(f"  Enable QC: {qc_config.get('enable_qc')}")

    print("\nConfiguration explanation:")
    print("  - Model: claude-sonnet-4-5 (no web search needed for QC)")
    print("  - Min QC Score: Rows below 0.5 are filtered out")
    print("  - Min/Max Row Count: Flexible range instead of fixed count")
    print("  - Enable QC: Can be toggled on/off for testing")


def demo_qc_workflow():
    """Demonstrate QC workflow process."""
    print("\n" + "=" * 80)
    print("DEMO: QC Workflow Process")
    print("=" * 80)

    print("\nQC Layer Process Flow:")
    print("\n1. INPUT: Discovered Rows from Consolidation")
    print("   - Example: 12 candidates from row discovery")
    print("   - Each has: id_values, match_score, match_rationale, source_urls")

    print("\n2. QC REVIEW: Claude Sonnet 4.5 evaluates each row")
    print("   - Checks relevance to user requirements")
    print("   - Identifies duplicates or low-quality entries")
    print("   - Assigns QC scores (0-1) with rationale")
    print("   - Makes keep/reject decisions")
    print("   - Adjusts priorities (promote/demote/none)")

    print("\n3. FILTERING: Apply QC decisions")
    print("   - Keep only rows with keep=true")
    print("   - Filter by min_qc_score threshold (0.5)")
    print("   - Sort by qc_score descending")

    print("\n4. OUTPUT: Approved Rows")
    print("   - Example: 10 approved rows (not fixed, QC-determined)")
    print("   - Ready for table population step")
    print("   - Enhanced with QC metadata (score, rationale, priority)")

    print("\n5. FLEXIBILITY: Row count determined by quality")
    print("   - If 8 rows meet threshold, return 8")
    print("   - If 25 rows meet threshold, return 25 (up to max_rows)")
    print("   - No forced padding to reach a fixed count")


def main():
    """Run all demos."""
    print("\n" + "=" * 80)
    print("QC LAYER DEMONSTRATION")
    print("=" * 80)

    try:
        # Demo 1: Schema
        demo_qc_schema()

        # Demo 2: Prompt
        demo_qc_prompt()

        # Demo 3: Configuration
        demo_qc_config()

        # Demo 4: Workflow
        demo_qc_workflow()

        print("\n" + "=" * 80)
        print("ALL DEMOS COMPLETED SUCCESSFULLY")
        print("=" * 80)
        print("\nQC Layer Components:")
        print("  [SUCCESS] Schema: table_maker/schemas/qc_review_response.json")
        print("  [SUCCESS] Prompt: table_maker/prompts/qc_review.md")
        print("  [SUCCESS] Handler: table_maker/src/qc_reviewer.py")
        print("  [SUCCESS] Config: Added to table_maker_config.json")
        print("  [SUCCESS] Test: table_maker/tests/test_qc_review.py")

        print("\nTo run integration tests (requires API key):")
        print("  cd /path/to/perplexityValidator")
        print("  export PYTHONPATH=/path/to/perplexityValidator:$PYTHONPATH")
        print("  pytest table_maker/tests/test_qc_review.py -v -m integration")

        print("\n")

    except Exception as e:
        print(f"\n[ERROR] Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
