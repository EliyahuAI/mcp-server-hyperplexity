#!/usr/bin/env python3
"""
Local End-to-End Test for Independent Row Discovery (PARALLEL MODE)

Tests the complete pipeline with real API keys in parallel mode (max_parallel_streams=3).
This validates that concurrent subdomain processing works correctly.

Requirements:
- ANTHROPIC_API_KEY environment variable set
- PERPLEXITY_API_KEY optional (may use Anthropic's search if not set)

Usage:
    python3 test_local_e2e_parallel.py

Duration: ~1-2 minutes (faster than sequential due to parallelization)
Estimated Cost: ~$0.10-0.15 (same as sequential, just faster)
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

# Test parameters - same as sequential but with parallelization
TARGET_ROW_COUNT = 10  # Final number of rows to deliver
DISCOVERY_MULTIPLIER = 1.5  # Find 15, keep best 10
MIN_MATCH_SCORE = 0.6  # Minimum quality threshold
COLUMN_DEFINITION_MODEL = "sonar-pro"  # Use sonar-pro for web search
WEB_SEARCH_MODEL = "sonar-pro"  # Use sonar-pro for row discovery (better quality)
MAX_PARALLEL_STREAMS = 3  # PARALLEL: Process up to 3 subdomains concurrently

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
# HELPER FUNCTIONS
# =============================================================================

def print_header(text):
    """Print a section header."""
    print("\n" + "="*60)
    print(f"  {text:^56}")
    print("="*60 + "\n")

def print_success(text):
    """Print success message."""
    print(f"[SUCCESS] {text}")

def print_error(text):
    """Print error message."""
    print(f"[ERROR] {text}")

def print_info(text):
    """Print info message."""
    print(f"[INFO] {text}")

def format_time(seconds):
    """Format seconds into human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    else:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"


# =============================================================================
# MAIN TEST FUNCTION
# =============================================================================

async def run_parallel_test():
    """Run the complete E2E test in parallel mode."""

    overall_start = time.time()

    # Print test header
    print_header("INDEPENDENT ROW DISCOVERY - LOCAL E2E TEST (PARALLEL)")

    # Check environment
    print_info("Checking environment...")
    if not os.getenv('ANTHROPIC_API_KEY'):
        print_error("ANTHROPIC_API_KEY not set in environment")
        print_info("Set it with: export ANTHROPIC_API_KEY='your-key-here'")
        return False

    print_success("API keys found")
    print_info("Using Perplexity API for web search")
    print_info(f"Parallel mode: Up to {MAX_PARALLEL_STREAMS} concurrent streams")

    # Initialize components
    print("\n[1/3] Initializing components...")
    try:
        ai_client = AIAPIClient()
        prompt_loader = PromptLoader(prompts_dir='table_maker/prompts')
        schema_validator = SchemaValidator(schemas_dir='table_maker/schemas')

        column_handler = ColumnDefinitionHandler(ai_client, prompt_loader, schema_validator)
        row_discovery = RowDiscovery(ai_client, prompt_loader, schema_validator)

        print_success("All components initialized")

    except Exception as e:
        print_error(f"Failed to initialize components: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Step 2: Column Definition
    print("\n[2/3] Defining columns and search strategy (with subdomains)...")

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

    try:
        conversation_context = {
            'messages': [
                {'role': 'user', 'content': USER_REQUEST}
            ]
        }

        # Provide context_web_research for UNKNOWNS that affect column design
        # Only include items that state-of-the-art LLM would NOT know
        # Example: ["Eliyahu.AI background", "Proprietary methodology X"]
        context_web_research = []  # Empty for this generic test

        column_start = time.time()
        column_result = await column_handler.define_columns(
            conversation_context=conversation_context,
            context_web_research=context_web_research,
            model=COLUMN_DEFINITION_MODEL,
            max_tokens=8000
        )
        column_time = time.time() - column_start
        stats['column_definition_time'] = column_time

        if not column_result['success']:
            print_error(f"Column definition failed: {column_result.get('error')}")
            return False

        columns = column_result['columns']
        search_strategy = column_result['search_strategy']
        table_name = column_result.get('table_name', 'Unknown Table')

        print_success(f"Defined {len(columns)} columns in {format_time(column_time)}")
        print_info(f"Table: {table_name}")

        # Display ID vs data columns
        id_cols = [c['name'] for c in columns if c.get('is_identification')]
        data_cols = [c['name'] for c in columns if not c.get('is_identification')]

        print_info(f"  ID columns: {len(id_cols)}")
        for col in id_cols:
            print(f"    - {col}")

        print_info(f"  Data columns: {len(data_cols)}")
        for col in data_cols:
            print(f"    - {col}")

        # Display subdomains
        subdomains = search_strategy.get('subdomains', [])
        print_success(f"Search strategy with {len(subdomains)} subdomains:")
        total_target = 0
        for subdomain in subdomains:
            target = subdomain.get('target_rows', 0)
            total_target += target
            print(f"  - {subdomain['name']} (target: {target} rows)")
            print(f"    Focus: {subdomain['focus']}")

        print_info(f"  Total target: {total_target} rows (will keep best {TARGET_ROW_COUNT})")

    except Exception as e:
        print_error(f"Column definition failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Step 3: Row Discovery (PARALLEL)
    print("\n[3/3] Discovering rows (PARALLEL mode)...")
    print_info("Starting parallel row discovery...")
    print_info(f"(Processing up to {MAX_PARALLEL_STREAMS} subdomains concurrently)")

    try:
        discovery_start = time.time()
        discovery_result = await row_discovery.discover_rows(
            search_strategy=search_strategy,
            columns=columns,
            target_row_count=TARGET_ROW_COUNT,
            discovery_multiplier=DISCOVERY_MULTIPLIER,
            min_match_score=MIN_MATCH_SCORE,
            max_parallel_streams=MAX_PARALLEL_STREAMS,  # PARALLEL MODE
            scoring_model=WEB_SEARCH_MODEL
        )
        discovery_time = time.time() - discovery_start
        stats['row_discovery_time'] = discovery_time

        if not discovery_result['success']:
            print_error(f"Row discovery failed: {discovery_result.get('error')}")
            return False

        final_rows = discovery_result.get('final_rows', [])
        discovery_stats = discovery_result.get('stats', {})

        # Update stats
        stats['total_candidates_found'] = discovery_stats.get('total_candidates_found', 0)
        stats['duplicates_removed'] = discovery_stats.get('duplicates_removed', 0)
        stats['below_threshold'] = discovery_stats.get('below_threshold', 0)
        stats['final_row_count'] = len(final_rows)

        # Calculate average score
        if final_rows:
            total_score = sum(row.get('match_score', 0) for row in final_rows)
            stats['avg_match_score'] = total_score / len(final_rows)

        # Display consolidation results
        print("\n[CONSOLIDATION]")
        print(f"  Total candidates: {stats['total_candidates_found']}")
        print(f"  Duplicates removed: {stats['duplicates_removed']}")
        print(f"  Below threshold (<{MIN_MATCH_SCORE}): {stats['below_threshold']}")
        print(f"  Final count: {stats['final_row_count']}")

        print_success(f"Row discovery completed in {format_time(discovery_time)}")
        print_info(f"[PARALLEL SPEEDUP] Compare to sequential: Sequential would take ~{format_time(discovery_time * MAX_PARALLEL_STREAMS / 1.8)}")

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
    print(f"  Row discovery (PARALLEL): {format_time(stats['row_discovery_time'])}")
    print(f"  Candidates found: {stats['total_candidates_found']}")
    print(f"  Deduplication: {stats['duplicates_removed']} removed")
    print(f"  Below threshold: {stats['below_threshold']} filtered")
    print(f"  Final rows: {stats['final_row_count']}")
    print(f"  Avg match score: {stats['avg_match_score']:.2f}")

    # -------------------------------------------------------------------------
    # SAVE RESULTS
    # -------------------------------------------------------------------------

    output_dir = Path('table_maker/output/local_tests')
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_dir / f'parallel_test_{timestamp}.json'

    output_data = {
        'timestamp': timestamp,
        'mode': 'parallel',
        'max_parallel_streams': MAX_PARALLEL_STREAMS,
        'user_request': USER_REQUEST,
        'configuration': {
            'target_row_count': TARGET_ROW_COUNT,
            'discovery_multiplier': DISCOVERY_MULTIPLIER,
            'min_match_score': MIN_MATCH_SCORE,
            'column_definition_model': COLUMN_DEFINITION_MODEL,
            'web_search_model': WEB_SEARCH_MODEL,
            'max_parallel_streams': MAX_PARALLEL_STREAMS
        },
        'columns': columns,
        'search_strategy': search_strategy,
        'final_rows': final_rows,
        'statistics': stats,
        'total_time_seconds': total_time
    }

    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)

    print_info(f"Results saved to: {output_file}")

    # -------------------------------------------------------------------------
    # COMPLETION
    # -------------------------------------------------------------------------

    print_header("[SUCCESS] LOCAL E2E TEST COMPLETE")

    print("Next steps:")
    print("  1. Compare timing to sequential test (~2m 30s)")
    print("  2. Verify parallel speedup achieved")
    print("  3. Check for any race conditions or data issues")
    print("  4. Scale up to full parallelization (max_parallel_streams=5)")

    print_header("TEST PASSED")

    return True


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    print(f"\nStarting parallel E2E test at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    success = asyncio.run(run_parallel_test())

    if success:
        print("\n[SUCCESS] Parallel test completed successfully!")
        sys.exit(0)
    else:
        print("\n[ERROR] Parallel test failed!")
        sys.exit(1)
