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
COLUMN_DEFINITION_MODEL = "claude-haiku-4-5"  # Claude Haiku (faster, cheaper)
WEB_SEARCH_MODEL = "sonar-pro"  # sonar-pro for row discovery with web search

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
        'stream_times': [],
        'total_cost': 0.0,
        'column_def_cost': 0.0,
        'row_discovery_cost': 0.0
    }

    # PHASE 1: Track all API calls with enhanced_data
    api_calls_log = []

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
        # Create conversation context (match what handler expects)
        conversation_context = {
            'messages': [  # For simple format
                {'role': 'user', 'content': USER_REQUEST}
            ],
            'conversation_log': [  # What handler actually reads
                {'role': 'user', 'content': USER_REQUEST}
            ],
            'user_request': USER_REQUEST,
            'approved': True,
            'target_row_count': TARGET_ROW_COUNT
        }

        # Define columns (this should now include subdomains in search_strategy)
        # Provide context_web_research for UNKNOWNS that affect column design
        # Only include items that state-of-the-art LLM would NOT know
        context_web_research = [
            "Latest AI hiring trends Q4 2024-Q1 2025",
            "Recent AI funding rounds and valuations October 2024-January 2025"
        ]  # Test with some context items to enable web search

        result = await column_handler.define_columns(
            conversation_context=conversation_context,
            context_web_research=context_web_research,
            model=COLUMN_DEFINITION_MODEL,
            max_tokens=12000  # Increased for comprehensive column definitions
        )

        if not result.get('success'):
            print_error(f"Column definition failed: {result.get('error', 'Unknown error')}")
            return False

        columns = result['columns']
        search_strategy = result['search_strategy']
        table_name = result.get('table_name', 'Unknown Table')

        col_time = time.time() - col_start
        stats['column_definition_time'] = col_time

        # Track cost from enhanced_data
        col_cost = result.get('cost', 0.0)
        stats['column_def_cost'] = col_cost
        stats['total_cost'] += col_cost

        # PHASE 1: Track column definition API call
        api_calls_log.append({
            'call_description': result.get('call_description', 'Creating Columns'),
            'model': result.get('model_used', COLUMN_DEFINITION_MODEL),
            'enhanced_data': result.get('enhanced_data', {}),
            'timestamp': datetime.now().isoformat()
        })

        print_success(f"Defined {len(columns)} columns in {format_time(col_time)} (${col_cost:.4f})")
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
    # STEP 3: ROW DISCOVERY (SEQUENTIAL WITH PROGRESSIVE ESCALATION)
    # -------------------------------------------------------------------------

    print_step(3, 3, "Discovering rows (SEQUENTIAL mode with progressive escalation)")

    discovery_start = time.time()

    try:
        # Load escalation strategy from config
        import json
        config_path = Path('table_maker/table_maker_config.json')
        with open(config_path, 'r') as f:
            config = json.load(f)

        row_discovery_config = config.get('row_discovery', {})
        escalation_strategy = row_discovery_config.get('escalation_strategy', None)
        check_targets_between_subdomains = row_discovery_config.get('check_targets_between_subdomains', False)
        early_stop_threshold_percentage = row_discovery_config.get('early_stop_threshold_percentage', 120)

        # Run discovery in SEQUENTIAL mode (max_parallel_streams=1)
        print_info("Starting sequential row discovery with progressive escalation...")
        print_info("(Processing one subdomain at a time)")

        if escalation_strategy:
            print_info(f"Progressive escalation strategy: {len(escalation_strategy)} rounds")
            for idx, strategy in enumerate(escalation_strategy, 1):
                model = strategy['model']
                context = strategy['search_context_size']
                threshold = strategy.get('min_candidates_percentage')
                print_info(f"  Round {idx}: {model} ({context}) - stop at {threshold}% if set")
        else:
            print_info("No escalation strategy - using legacy mode")

        discovery_result = await row_discovery.discover_rows(
            search_strategy=search_strategy,
            columns=columns,
            target_row_count=TARGET_ROW_COUNT,
            discovery_multiplier=DISCOVERY_MULTIPLIER,
            min_match_score=MIN_MATCH_SCORE,
            max_parallel_streams=1,  # SEQUENTIAL MODE
            escalation_strategy=escalation_strategy,
            check_targets_between_subdomains=check_targets_between_subdomains,
            early_stop_threshold_percentage=early_stop_threshold_percentage
        )

        if not discovery_result.get('success'):
            print_error(f"Row discovery failed: {discovery_result.get('error', 'Unknown error')}")
            return False

        discovery_time = time.time() - discovery_start
        stats['row_discovery_time'] = discovery_time

        # Extract results
        final_rows = discovery_result.get('final_rows', [])
        stream_results = discovery_result.get('stream_results', [])
        discovery_stats = discovery_result.get('stats', {})  # Correct field name

        stats['final_row_count'] = len(final_rows)
        stats['total_candidates_found'] = discovery_stats.get('total_candidates_found', 0)
        stats['duplicates_removed'] = discovery_stats.get('duplicates_removed', 0)
        stats['below_threshold'] = discovery_stats.get('below_threshold', 0)

        # Calculate average score
        if final_rows:
            total_score = sum(row.get('match_score', 0) for row in final_rows)
            stats['avg_match_score'] = total_score / len(final_rows)

        # PHASE 1: Track API calls from row discovery rounds and calculate costs
        row_discovery_total_cost = 0.0

        for idx, stream_result in enumerate(stream_results, 1):
            subdomain_name = stream_result.get('subdomain', f'Subdomain {idx}')
            all_rounds = stream_result.get('all_rounds', [])

            if all_rounds:
                # Progressive escalation mode - has all_rounds
                for round_data in all_rounds:
                    enhanced = round_data.get('enhanced_data', {})
                    round_cost = enhanced.get('costs', {}).get('actual', {}).get('total_cost', 0.0)
                    row_discovery_total_cost += round_cost

                    api_calls_log.append({
                        'call_description': f"Finding Rows - {subdomain_name} - Round {round_data.get('round', '?')} ({round_data.get('model', 'unknown')}-{round_data.get('context', 'unknown')})",
                        'model': round_data.get('model', 'unknown'),
                        'context': round_data.get('context', 'unknown'),
                        'enhanced_data': enhanced,
                        'prompt_used': round_data.get('prompt_used', ''),
                        'timestamp': datetime.now().isoformat(),
                        'cost': round_cost
                    })
            else:
                # Legacy mode or single call - just log the subdomain
                enhanced = stream_result.get('enhanced_data', {})
                round_cost = enhanced.get('costs', {}).get('actual', {}).get('total_cost', 0.0)
                row_discovery_total_cost += round_cost

                api_calls_log.append({
                    'call_description': f"Finding Rows - {subdomain_name}",
                    'model': WEB_SEARCH_MODEL,
                    'enhanced_data': enhanced,
                    'timestamp': datetime.now().isoformat(),
                    'cost': round_cost
                })

        stats['row_discovery_cost'] = row_discovery_total_cost
        stats['total_cost'] += row_discovery_total_cost

        # Display stream results
        print()
        for idx, stream_result in enumerate(stream_results, 1):
            subdomain_name = stream_result.get('subdomain', 'Unknown')
            candidates = stream_result.get('candidates', [])
            stream_time = stream_result.get('processing_time', 0)
            rounds_executed = stream_result.get('rounds_executed', 0)
            rounds_skipped = stream_result.get('rounds_skipped', 0)
            stats['stream_times'].append(stream_time)

            print(f"Stream {idx}/{len(stream_results)}: {subdomain_name}")

            # Show progressive escalation info if available
            if rounds_executed > 0:
                print(f"  [INFO] Progressive escalation: {rounds_executed} round(s) executed, {rounds_skipped} skipped")
                # Count candidates by model
                models_used = {}
                for candidate in candidates:
                    model = candidate.get('model_used', 'unknown')
                    context = candidate.get('context_used', 'unknown')
                    key = f"{model}({context})"
                    models_used[key] = models_used.get(key, 0) + 1

                if models_used:
                    print(f"  [INFO] Candidates by model: {', '.join(f'{k}: {v}' for k, v in models_used.items())}")

            print(f"  [SUCCESS] Found {len(candidates)} candidates in {format_time(stream_time)}")

            if candidates:
                top_candidate = candidates[0]
                id_vals = top_candidate.get('id_values', {})
                # Handle both snake_case and Title Case
                top_name = id_vals.get('company_name') or id_vals.get('Company Name', 'Unknown')
                top_score = top_candidate.get('match_score', 0)
                top_model = top_candidate.get('model_used', 'unknown')
                top_context = top_candidate.get('context_used', 'unknown')
                print(f"  [INFO] Top candidate: {top_name} (score: {top_score:.2f}, from {top_model}({top_context}))")
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
    # QC REVIEW
    # -------------------------------------------------------------------------

    print_step(4, 4, "Quality Control Review")

    qc_start = time.time()

    try:
        from table_maker.src.qc_reviewer import QCReviewer

        qc_reviewer = QCReviewer(ai_client, prompt_loader, schema_validator)

        print_info(f"Reviewing {len(final_rows)} discovered rows with QC layer...")

        qc_result = await qc_reviewer.review_rows(
            discovered_rows=final_rows,
            columns=columns,
            user_context=USER_REQUEST,
            table_name=table_name,
            table_purpose=search_strategy.get('table_purpose', ''),
            tablewide_research=search_strategy.get('tablewide_research', ''),
            model="claude-sonnet-4-5",
            max_tokens=16000,  # Generous tokens for reviewing all rows
            min_qc_score=0.5,
            max_rows=999  # No artificial cutoff - keep all quality rows
        )

        qc_time = time.time() - qc_start
        stats['qc_review_time'] = qc_time

        if not qc_result.get('success'):
            print_error(f"QC review failed: {qc_result.get('error')}")
            # Continue with original rows
            approved_rows = final_rows
        else:
            approved_rows = qc_result.get('approved_rows', final_rows)
            qc_summary = qc_result.get('qc_summary', {})

            # Track QC API call and cost
            qc_cost = qc_result.get('cost', 0.0)
            stats['qc_cost'] = qc_cost
            stats['total_cost'] += qc_cost

            api_calls_log.append({
                'call_description': 'QC Review - Filtering and Prioritizing Rows',
                'model': 'claude-sonnet-4-5',
                'enhanced_data': qc_result.get('enhanced_data', {}),
                'timestamp': datetime.now().isoformat(),
                'cost': qc_cost
            })

            # Update stats
            stats['qc_total_reviewed'] = qc_summary.get('total_reviewed', 0)
            stats['qc_kept'] = qc_summary.get('kept', 0)
            stats['qc_rejected'] = qc_summary.get('rejected', 0)
            stats['qc_promoted'] = qc_summary.get('promoted', 0)
            stats['qc_demoted'] = qc_summary.get('demoted', 0)

            print_success(f"QC review completed in {format_time(qc_time)}")
            print_info(f"Reviewed: {qc_summary.get('total_reviewed', 0)}")
            print_info(f"Kept: {qc_summary.get('kept', 0)}")
            print_info(f"Rejected: {qc_summary.get('rejected', 0)}")
            if qc_summary.get('promoted', 0) > 0:
                print_info(f"Promoted: {qc_summary.get('promoted', 0)}")
            if qc_summary.get('demoted', 0) > 0:
                print_info(f"Demoted: {qc_summary.get('demoted', 0)}")
            print_info(f"QC Reasoning: {qc_summary.get('reasoning', 'N/A')}")

        # Use QC-approved rows for final output
        final_rows = approved_rows

    except Exception as e:
        print_error(f"QC review failed with exception: {e}")
        import traceback
        traceback.print_exc()
        print_info("Continuing with original discovered rows (no QC filtering)")

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

        # Get company name and website (handle various field name formats)
        company_name = (id_values.get('company_name') or
                       id_values.get('Company Name') or
                       id_values.get('Entity Name') or
                       id_values.get('entity_name') or 'Unknown')
        website = (id_values.get('website') or
                  id_values.get('Website') or
                  id_values.get('Website URL') or
                  id_values.get('website_url') or 'N/A')

        # Get model info
        model_used = row.get('model_used', 'unknown')
        context_used = row.get('context_used', 'unknown')
        found_by_models = row.get('found_by_models', [])
        model_quality_rank = row.get('model_quality_rank', 0)

        # Show score breakdown and recalculate if available
        score_breakdown = row.get('score_breakdown', {})
        if score_breakdown:
            relevancy = score_breakdown.get('relevancy', 0)
            reliability = score_breakdown.get('reliability', 0)
            recency = score_breakdown.get('recency', 0)

            # Recalculate correct score using formula
            calculated_score = (relevancy * 0.4) + (reliability * 0.3) + (recency * 0.3)

            # Show both reported and calculated scores
            print(f"\n  {idx}. {company_name} (score: {score:.2f}, quality_rank: {model_quality_rank})")
            print(f"     Website: {website}")
            print(f"     Scores: Relevancy={relevancy:.2f}, Reliability={reliability:.2f}, Recency={recency:.2f}")
            print(f"     Model: {model_used}({context_used})")

            # Show if found by multiple models (deduplication happened)
            if len(found_by_models) > 1:
                print(f"     [MERGED] Found by: {', '.join(found_by_models)}")

            # Warn if mismatch
            if abs(score - calculated_score) > 0.01:
                print(f"     [WARNING] Score mismatch! Formula gives {calculated_score:.2f} but reported {score:.2f}")
        else:
            print(f"\n  {idx}. {company_name} ({score:.2f})")
            print(f"     Website: {website}")
            print(f"     Model: {model_used}({context_used})")

        # Show rationale (truncate if too long)
        if len(rationale) > 100:
            rationale = rationale[:97] + "..."
        print(f"     Rationale: {rationale}")

    # -------------------------------------------------------------------------
    # PHASE 1: API CALLS SUMMARY
    # -------------------------------------------------------------------------

    print("\n[API CALLS SUMMARY]")
    total_api_cost = sum(
        call.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0)
        for call in api_calls_log
    )
    print(f"  Total API calls: {len(api_calls_log)}")
    print(f"  Total cost: ${total_api_cost:.4f}")

    for call in api_calls_log:
        desc = call.get('call_description', 'Unknown')
        model = call.get('model', 'unknown')
        context = call.get('context', '')
        context_str = f" ({context})" if context else ""
        cost = call.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0)
        print(f"    - {desc}: ${cost:.4f} ({model}{context_str})")

    # -------------------------------------------------------------------------
    # STATISTICS
    # -------------------------------------------------------------------------

    total_time = time.time() - overall_start

    # Recalculate total cost from api_calls_log (authoritative source)
    total_api_cost = sum(
        call.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0)
        for call in api_calls_log
    )
    stats['total_cost'] = total_api_cost  # Override with accurate calculation

    # Calculate QC cost if available
    qc_cost = stats.get('qc_cost', 0.0)

    print("\n[STATISTICS]")
    print(f"  Total execution time: {format_time(total_time)}")
    print(f"  Column definition: {format_time(stats['column_definition_time'])} (${stats['column_def_cost']:.4f})")
    print(f"  Row discovery (sequential): {format_time(stats['row_discovery_time'])} (${stats['row_discovery_cost']:.4f})")

    if stats['stream_times']:
        print(f"    - Individual streams:")
        for idx, stream_time in enumerate(stats['stream_times'], 1):
            print(f"      Stream {idx}: {format_time(stream_time)}")
        print(f"    - (Note: Sequential = sum of all streams)")

    if qc_cost > 0:
        qc_time = stats.get('qc_review_time', 0)
        print(f"  QC review: {format_time(qc_time)} (${qc_cost:.4f})")

    print(f"  Candidates found: {stats['total_candidates_found']}")
    print(f"  Deduplication: {stats['duplicates_removed']} removed")
    print(f"  Below threshold: {stats['below_threshold']} filtered")

    if 'qc_total_reviewed' in stats:
        print(f"  QC reviewed: {stats['qc_total_reviewed']}")
        print(f"  QC kept: {stats['qc_kept']}")
        print(f"  QC rejected: {stats['qc_rejected']}")

    print(f"  Final rows: {len(final_rows)} (QC-determined)")
    print(f"  Avg match score: {stats['avg_match_score']:.2f}")
    print(f"  Total cost: ${total_api_cost:.4f}")

    # -------------------------------------------------------------------------
    # SAVE OUTPUT (OPTIONAL)
    # -------------------------------------------------------------------------

    # Save results to file for inspection
    output_dir = Path('table_maker/output/local_tests')
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_dir / f'sequential_test_{timestamp}.json'

    # Final stats update: Recalculate all costs from api_calls_log enhanced_data
    stats['row_discovery_cost'] = sum(
        call.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0)
        for call in api_calls_log
        if 'Finding Rows' in call.get('call_description', '')
    )
    stats['qc_cost'] = sum(
        call.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0)
        for call in api_calls_log
        if 'QC Review' in call.get('call_description', '')
    )
    stats['total_cost'] = sum(
        call.get('enhanced_data', {}).get('costs', {}).get('actual', {}).get('total_cost', 0)
        for call in api_calls_log
    )

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
        'all_candidates_full_list': discovery_result.get('all_candidates', []),  # Full list before filtering
        'api_calls': api_calls_log,  # PHASE 1: Include all API calls with enhanced_data
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
