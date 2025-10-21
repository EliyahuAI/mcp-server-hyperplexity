#!/usr/bin/env python3
"""
Local End-to-End Test for Independent Row Discovery (SEQUENTIAL MODE)

Tests the complete pipeline with real API keys in sequential mode (max_parallel_streams=1).
This allows us to validate each component independently before enabling parallelization.

Requirements:
- ANTHROPIC_API_KEY environment variable set
- PERPLEXITY_API_KEY optional (may use Anthropic's search if not set)

Usage:
    python3 test_local_e2e_sequential.py

Duration: ~2-3 minutes
Estimated Cost: ~$0.10-0.15
"""

import os
import sys
import asyncio
import json
import time
from pathlib import Path
from datetime import datetime

# Set up environment - disable S3 operations for local testing
os.environ['DISABLE_AI_DEBUG_SAVES'] = 'true'
os.environ['DISABLE_S3_CACHE'] = 'true'  # Disable S3 caching for local tests

# Add paths for imports
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))
sys.path.insert(0, str(parent_dir / 'src' / 'shared'))

# Import components
from table_maker.src.column_definition_handler import ColumnDefinitionHandler
from table_maker.src.row_discovery import RowDiscovery
from table_maker.src.prompt_loader import PromptLoader
from table_maker.src.schema_validator import SchemaValidator
from ai_api_client import AIAPIClient


# =============================================================================
# CONFIGURATION
# =============================================================================

# Test parameters - start small for validation
TARGET_ROW_COUNT = 10  # Final number of rows to deliver
DISCOVERY_MULTIPLIER = 1.5  # Find 15, keep best 10
MIN_MATCH_SCORE = 0.6  # Minimum quality threshold

# Models to use
COLUMN_DEFINITION_MODEL = "claude-sonnet-4-5"
WEB_SEARCH_MODEL = "sonar-pro"

# User request for testing
USER_REQUEST = """
I want to create a table tracking AI companies that are actively hiring.

Columns needed:
- Company Name
- Website
- Is hiring for AI roles? (yes/no)
- Team size (approximate)
- Recent funding (last round)

Find about 10 companies across different AI sectors like research, healthcare, and enterprise.
Make sure to include both established companies and startups.
"""


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def print_header(text: str, char: str = "="):
    """Print a formatted header."""
    width = 60
    print("\n" + char * width)
    print(text.center(width))
    print(char * width + "\n")


def print_success(text: str):
    """Print success message."""
    print(f"[SUCCESS] {text}")


def print_info(text: str):
    """Print info message."""
    print(f"[INFO] {text}")


def print_error(text: str):
    """Print error message."""
    print(f"[ERROR] {text}")


def print_step(step_num: int, total_steps: int, description: str):
    """Print step header."""
    print(f"\n[{step_num}/{total_steps}] {description}...")


def format_time(seconds: float) -> str:
    """Format seconds as readable time."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    else:
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}m {secs:.1f}s"


# =============================================================================
# MAIN TEST FUNCTION
# =============================================================================

async def run_sequential_test():
    """Run complete sequential E2E test."""

    print_header("INDEPENDENT ROW DISCOVERY - LOCAL E2E TEST (SEQUENTIAL)")

    overall_start = time.time()
    stats = {
        'column_definition_time': 0,
        'row_discovery_time': 0,
        'total_candidates_found': 0,
        'duplicates_removed': 0,
        'below_threshold': 0,
        'final_row_count': 0,
        'avg_match_score': 0.0,
        'stream_times': []
    }

    # -------------------------------------------------------------------------
    # PRE-FLIGHT CHECKS
    # -------------------------------------------------------------------------

    print_info("Checking environment...")

    # Check for required API key
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print_error("ANTHROPIC_API_KEY not set")
        print_info("Please set it in your environment:")
        print_info("  export ANTHROPIC_API_KEY=sk-ant-...")
        print_info("Or create a .env file (see .env.example)")
        return False

    print_success("API keys found")

    # Check for optional Perplexity key
    if os.environ.get('PERPLEXITY_API_KEY'):
        print_info("Using Perplexity API for web search")
    else:
        print_info("No PERPLEXITY_API_KEY - will use Anthropic's search capabilities")

    # -------------------------------------------------------------------------
    # STEP 1: INITIALIZE COMPONENTS
    # -------------------------------------------------------------------------

    print_step(1, 3, "Initializing components")

    try:
        ai_client = AIAPIClient()
        prompt_loader = PromptLoader('table_maker/prompts')
        schema_validator = SchemaValidator('table_maker/schemas')

        column_handler = ColumnDefinitionHandler(
            ai_client, prompt_loader, schema_validator
        )

        row_discovery = RowDiscovery(
            ai_client, prompt_loader, schema_validator
        )

        print_success("All components initialized")

    except Exception as e:
        print_error(f"Failed to initialize components: {e}")
        import traceback
        traceback.print_exc()
        return False

    # -------------------------------------------------------------------------
    # STEP 2: COLUMN DEFINITION (WITH SUBDOMAINS)
    # -------------------------------------------------------------------------

    print_step(2, 3, "Defining columns and search strategy (with subdomains)")

    col_start = time.time()

    try:
        # Create conversation context
        conversation_context = {
            'user_request': USER_REQUEST,
            'conversation_history': [
                {
                    'role': 'user',
                    'content': USER_REQUEST
                }
            ],
            'approved': True,
            'target_row_count': TARGET_ROW_COUNT
        }

        # Define columns (this should now include subdomains in search_strategy)
        result = await column_handler.define_columns(
            conversation_context=conversation_context,
            model=COLUMN_DEFINITION_MODEL,
            max_tokens=8000
        )

        if not result.get('success'):
            print_error(f"Column definition failed: {result.get('error', 'Unknown error')}")
            return False

        columns = result['columns']
        search_strategy = result['search_strategy']
        table_name = result.get('table_name', 'Unknown Table')

        col_time = time.time() - col_start
        stats['column_definition_time'] = col_time

        print_success(f"Defined {len(columns)} columns in {format_time(col_time)}")
        print_info(f"Table: {table_name}")

        # Display columns
        id_cols = [c for c in columns if c.get('is_identification')]
        data_cols = [c for c in columns if not c.get('is_identification')]
        print_info(f"  ID columns: {len(id_cols)}")
        for col in id_cols:
            print(f"    - {col['name']}")
        print_info(f"  Data columns: {len(data_cols)}")
        for col in data_cols:
            print(f"    - {col['name']}")

        # Check for subdomains in search strategy
        subdomains = search_strategy.get('subdomains', [])

        if not subdomains:
            print_error("No subdomains defined in search_strategy!")
            print_info("This is expected if using OLD architecture.")
            print_info("Please update column_definition.md prompt and schema.")
            return False

        print_success(f"Search strategy with {len(subdomains)} subdomains:")
        total_target = 0
        for subdomain in subdomains:
            target = subdomain.get('target_rows', 0)
            total_target += target
            print(f"  - {subdomain['name']} (target: {target} rows)")
            print(f"    Focus: {subdomain.get('focus', 'N/A')}")

        print_info(f"  Total target: {total_target} rows (will keep best {TARGET_ROW_COUNT})")

    except Exception as e:
        print_error(f"Column definition failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    # -------------------------------------------------------------------------
    # STEP 3: ROW DISCOVERY (SEQUENTIAL)
    # -------------------------------------------------------------------------

    print_step(3, 3, "Discovering rows (SEQUENTIAL mode)")

    discovery_start = time.time()

    try:
        # Run discovery in SEQUENTIAL mode (max_parallel_streams=1)
        print_info("Starting sequential row discovery...")
        print_info("(Processing one subdomain at a time)")

        discovery_result = await row_discovery.discover_rows(
            search_strategy=search_strategy,
            columns=columns,
            target_row_count=TARGET_ROW_COUNT,
            discovery_multiplier=DISCOVERY_MULTIPLIER,
            min_match_score=MIN_MATCH_SCORE,
            max_parallel_streams=1  # SEQUENTIAL MODE
        )

        if not discovery_result.get('success'):
            print_error(f"Row discovery failed: {discovery_result.get('error', 'Unknown error')}")
            return False

        discovery_time = time.time() - discovery_start
        stats['row_discovery_time'] = discovery_time

        # Extract results
        final_rows = discovery_result.get('final_rows', [])
        stream_results = discovery_result.get('stream_results', [])
        consolidation_stats = discovery_result.get('consolidation_stats', {})

        stats['final_row_count'] = len(final_rows)
        stats['total_candidates_found'] = consolidation_stats.get('total_candidates', 0)
        stats['duplicates_removed'] = consolidation_stats.get('duplicates_removed', 0)
        stats['below_threshold'] = consolidation_stats.get('below_threshold', 0)

        # Calculate average score
        if final_rows:
            total_score = sum(row.get('match_score', 0) for row in final_rows)
            stats['avg_match_score'] = total_score / len(final_rows)

        # Display stream results
        print()
        for idx, stream_result in enumerate(stream_results, 1):
            subdomain_name = stream_result.get('subdomain', 'Unknown')
            candidates = stream_result.get('candidates', [])
            stream_time = stream_result.get('processing_time', 0)
            stats['stream_times'].append(stream_time)

            print(f"Stream {idx}/{len(stream_results)}: {subdomain_name}")
            print(f"  [INFO] Executing integrated scoring search...")
            print(f"  [SUCCESS] Found {len(candidates)} candidates in {format_time(stream_time)}")

            if candidates:
                top_candidate = candidates[0]
                id_vals = top_candidate.get('id_values', {})
                # Handle both snake_case and Title Case
                top_name = id_vals.get('company_name') or id_vals.get('Company Name', 'Unknown')
                top_score = top_candidate.get('match_score', 0)
                print(f"  [INFO] Top candidate: {top_name} (score: {top_score:.2f})")
            print()

        # Display consolidation results
        print("[CONSOLIDATION]")
        print(f"  Total candidates: {stats['total_candidates_found']}")
        print(f"  Duplicates removed: {stats['duplicates_removed']}")
        print(f"  Below threshold (<{MIN_MATCH_SCORE}): {stats['below_threshold']}")
        print(f"  Final count: {stats['final_row_count']}")

        print_success(f"Row discovery completed in {format_time(discovery_time)}")

    except Exception as e:
        print_error(f"Row discovery failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    # -------------------------------------------------------------------------
    # DISPLAY RESULTS
    # -------------------------------------------------------------------------

    print_header("RESULTS")

    print(f"[COLUMNS] ({len(columns)} total):")
    for col in columns:
        col_type = "[ID]" if col.get('is_identification') else "[DATA]"
        print(f"  {col_type} {col['name']}")

    print(f"\n[ROWS DISCOVERED] ({len(final_rows)} total, sorted by score):")
    for idx, row in enumerate(final_rows, 1):
        id_values = row.get('id_values', {})
        score = row.get('match_score', 0)
        rationale = row.get('match_rationale', 'N/A')

        # Get company name and website (handle both snake_case and Title Case)
        company_name = id_values.get('company_name') or id_values.get('Company Name', 'Unknown')
        website = id_values.get('website') or id_values.get('Website', 'N/A')

        print(f"\n  {idx}. {company_name} ({score:.2f})")
        print(f"     Website: {website}")

        # Show score breakdown if available
        score_breakdown = row.get('score_breakdown', {})
        if score_breakdown:
            relevancy = score_breakdown.get('relevancy', 0)
            reliability = score_breakdown.get('reliability', 0)
            recency = score_breakdown.get('recency', 0)
            print(f"     Scores: Relevancy={relevancy:.2f}, Reliability={reliability:.2f}, Recency={recency:.2f}")

        # Show rationale (truncate if too long)
        if len(rationale) > 100:
            rationale = rationale[:97] + "..."
        print(f"     Rationale: {rationale}")

    # -------------------------------------------------------------------------
    # STATISTICS
    # -------------------------------------------------------------------------

    total_time = time.time() - overall_start

    print("\n[STATISTICS]")
    print(f"  Total execution time: {format_time(total_time)}")
    print(f"  Column definition: {format_time(stats['column_definition_time'])}")
    print(f"  Row discovery (sequential): {format_time(stats['row_discovery_time'])}")

    if stats['stream_times']:
        print(f"    - Individual streams:")
        for idx, stream_time in enumerate(stats['stream_times'], 1):
            print(f"      Stream {idx}: {format_time(stream_time)}")
        print(f"    - (Note: Sequential = sum of all streams)")

    print(f"  Candidates found: {stats['total_candidates_found']}")
    print(f"  Deduplication: {stats['duplicates_removed']} removed")
    print(f"  Below threshold: {stats['below_threshold']} filtered")
    print(f"  Final rows: {stats['final_row_count']}")
    print(f"  Avg match score: {stats['avg_match_score']:.2f}")

    # -------------------------------------------------------------------------
    # SAVE OUTPUT (OPTIONAL)
    # -------------------------------------------------------------------------

    # Save results to file for inspection
    output_dir = Path('table_maker/output/local_tests')
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_dir / f'sequential_test_{timestamp}.json'

    output_data = {
        'timestamp': timestamp,
        'user_request': USER_REQUEST,
        'configuration': {
            'target_row_count': TARGET_ROW_COUNT,
            'discovery_multiplier': DISCOVERY_MULTIPLIER,
            'min_match_score': MIN_MATCH_SCORE,
            'column_definition_model': COLUMN_DEFINITION_MODEL,
            'web_search_model': WEB_SEARCH_MODEL
        },
        'columns': columns,
        'search_strategy': search_strategy,
        'final_rows': final_rows,
        'statistics': stats,
        'total_time_seconds': total_time
    }

    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n[INFO] Results saved to: {output_file}")

    # -------------------------------------------------------------------------
    # SUCCESS
    # -------------------------------------------------------------------------

    print_header("[SUCCESS] LOCAL E2E TEST COMPLETE")

    print("Next steps:")
    print("  1. Review the results above")
    print("  2. Check match scores and quality")
    print("  3. If quality looks good, test parallel mode (max_parallel_streams=2)")
    print("  4. Then scale up to full parallelization (max_parallel_streams=5)")

    return True


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    print(f"\nStarting sequential E2E test at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    try:
        success = asyncio.run(run_sequential_test())
        exit_code = 0 if success else 1

        if success:
            print("\n" + "="*60)
            print("TEST PASSED".center(60))
            print("="*60 + "\n")
        else:
            print("\n" + "="*60)
            print("TEST FAILED".center(60))
            print("="*60 + "\n")

        sys.exit(exit_code)

    except KeyboardInterrupt:
        print("\n\n[INFO] Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
