"""
Independent Row Discovery Execution Handler for Lambda.

This module orchestrates the 5-step pipeline using LOCAL components directly:
0. Background Research (Internal - finds authoritative sources and starting tables)
1. Column Definition (uses research output)
2. Row Discovery (with progressive escalation)
3. Consolidation (built into row_discovery)
4. QC Review

The LOCAL components (from table_maker_lib/) are the SOURCE OF TRUTH.
This file just adds Lambda infrastructure wrappers (S3, WebSocket, runs DB).

WEBSOCKET MESSAGES FOR FRONTEND:
================================
After Step 1 (Column Definition) completes, a WebSocket message is sent with:
{
    "type": "table_execution_update",
    "conversation_id": str,
    "current_step": 1,
    "total_steps": 4,
    "status": "Column definition complete: {table_name}",
    "progress_percent": 20,
    "columns": [...],
    "table_name": str,
    "requirements": {
        "hard": str,  # Formatted as bullet list, e.g., "- Requirement 1\n- Requirement 2"
        "soft": str   # Formatted as bullet list, e.g., "- Requirement 3\n- Requirement 4"
    }
}

FRONTEND DISPLAY REQUIREMENTS:
================================
The requirements should be displayed in a dedicated info box BEFORE the ID columns box.
Display format:
  1. Show "Hard Requirements" section:
     - Use red/bold styling to indicate these are mandatory
     - Display the bullet list from requirements.hard
     - If requirements.hard is "(None)", show "No hard requirements"

  2. Show "Soft Requirements" section:
     - Use yellow/normal styling to indicate these are nice-to-have
     - Display the bullet list from requirements.soft
     - If requirements.soft is "(None)", show "No soft requirements"

The requirements come from column_definition_handler.py (lines 182-185) and are
formatted as bullet lists with optional rationale in parentheses:
  - Requirement text (rationale if provided)

INFO BOX 3: DISCOVERED ROWS / APPROVED ROWS
============================================
After Step 2 (Row Discovery) completes, send WebSocket message with discovered rows:
{
    "type": "table_execution_update",
    "current_step": 2,
    "status": "Row discovery complete...",
    "discovered_rows": [
        {"id_values": {"Company": "ABC Corp"}, "row_score": 0.95},
        ...  # First 15 rows only
    ],
    "total_discovered": 42  # Total count of all discovered rows
}

After Step 4 (QC Review) completes, UPDATE the same box with approved rows:
{
    "type": "table_execution_update",
    "current_step": 4,
    "status": "QC review complete...",
    "approved_rows": [
        {"id_values": {"Company": "ABC Corp"}, "row_score": 0.95},
        ...  # First 15 approved rows only
    ],
    "total_approved": 38,  # Count of approved rows after QC
    "total_discovered": 42,  # Original discovery count (for context)
    "qc_summary": {
        "promoted": 5,  # Rows upgraded to higher quality
        "demoted": 2,   # Rows downgraded but kept
        "rejected": 4   # Rows removed from final set
    }
}

FRONTEND DISPLAY EXPECTATIONS FOR INFO BOX 3:
----------------------------------------------
Initial State (After Row Discovery):
- Header: "Discovered Rows: X total"
- Button Color: Green (to match success/completion)
- Content: Show first 10-15 rows with ID values in readable format
  * Display format: "{ID Column 1}: {value}, {ID Column 2}: {value}, ..."
  * Example: "Company: ABC Corp, Ticker: ABC"
- Footer: Show "+Y more rows" if total_discovered > 15

Updated State (After QC Review):
- Header: "Approved Rows: X of Y discovered"
- Button Color: Green (consistent with discovery state)
- Content: Show first 10-15 approved rows with ID values
  * Same display format as discovery state
- QC Summary Line (if available): "QC Review: +5 promoted, -4 rejected"
- Footer: Show "+Z more rows" if total_approved > 15

This is the THIRD info box in the UI sequence:
1. Requirements (hard/soft)
2. ID Columns (identification columns)
3. Research Columns (columns to research)
4. Discovered/Approved Rows (THIS BOX) - dynamically updated
"""

import logging
import json
import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

# Lambda infrastructure imports
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from interface_lambda.utils.helpers import create_response
from dynamodb_schemas import update_run_status

# WebSocket client for real-time updates
try:
    from websocket_client import WebSocketClient
    websocket_client = WebSocketClient()
except ImportError:
    websocket_client = None
    logger = logging.getLogger()
    logger.warning("WebSocket client not available")

# Import LOCAL components (no modifications)
from .table_maker_lib.background_research_handler import BackgroundResearchHandler
from .table_maker_lib.table_extraction_handler import TableExtractionHandler
from .table_maker_lib.column_definition_handler import ColumnDefinitionHandler
from .table_maker_lib.row_discovery import RowDiscovery
from .table_maker_lib.qc_reviewer import QCReviewer
from .table_maker_lib.prompt_loader import PromptLoader
from .table_maker_lib.schema_validator import SchemaValidator
from shared.ai_api_client import ai_client  # Use singleton, not class

# Import config generation
from .config_bridge import build_table_analysis_from_conversation
from ..generate_config_unified import handle_generate_config_unified
from .table_maker_lib.config_generator import ConfigGenerator

# Import MemoryCache for storing extracted tables to agent_memory (RAM-based, flushed at batch end)
try:
    from the_clone.search_memory_cache import MemoryCache
    SEARCH_MEMORY_AVAILABLE = True
except ImportError:
    SEARCH_MEMORY_AVAILABLE = False
    logger = logging.getLogger()
    logger.warning("[EXECUTION] MemoryCache not available - extracted tables won't be stored to agent_memory")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Row discovery constants
FIND_ALL_SAFETY_CAP = 200  # Maximum rows when user requests "find all"
DISCOVERY_AMPLIFICATION = 1.5  # Amplify target for discovery, QC will trim back

# Timeout constants
LAMBDA_MAX_SECONDS = 900  # Lambda 15-minute timeout
TIMEOUT_SAFETY_BUFFER = 120  # 2-minute safety buffer
MIN_TIME_FOR_DISCOVERY_QC = 360  # 6 minutes minimum for row discovery + QC cycle


class TimeoutGuard:
    """
    Track elapsed time and provide timeout-aware decisions.

    Used to ensure graceful completion before Lambda timeout.
    """

    def __init__(self, max_seconds: int = LAMBDA_MAX_SECONDS, safety_buffer: int = TIMEOUT_SAFETY_BUFFER):
        self.start_time = time.time()
        self.max_seconds = max_seconds
        self.safety_buffer = safety_buffer
        self.deadline = self.start_time + max_seconds - safety_buffer

    def elapsed(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self.start_time

    def remaining(self) -> float:
        """Get remaining time before deadline in seconds."""
        return self.deadline - time.time()

    def has_time_for(self, estimated_seconds: int) -> bool:
        """Check if there's enough time for an operation."""
        return self.remaining() > estimated_seconds

    def should_stop(self) -> bool:
        """Check if we've exceeded the deadline."""
        return self.remaining() <= 0

    def can_do_discovery_qc_cycle(self) -> bool:
        """Check if there's enough time for a full discovery + QC cycle."""
        return self.remaining() > MIN_TIME_FOR_DISCOVERY_QC


def send_execution_progress(
    session_id: str,
    conversation_id: str,
    current_step: int,
    total_steps: int,
    status: str,
    progress_percent: int,
    **kwargs
) -> None:
    """
    Send execution progress update via WebSocket.

    Args:
        session_id: Session identifier
        conversation_id: Conversation identifier
        current_step: Current step number (1-4)
        total_steps: Total number of steps (4)
        status: Human-readable status message
        progress_percent: Progress percentage (0-100)
        **kwargs: Additional fields to include in message
    """
    if not websocket_client or not session_id:
        return

    try:
        message = {
            'type': 'table_execution_update',
            'conversation_id': conversation_id,
            'current_step': current_step,
            'total_steps': total_steps,
            'status': status,
            'progress_percent': progress_percent,
            'phase': 'execution',
            **kwargs
        }

        # DEBUG: Log if discovered_rows is in the message
        if 'discovered_rows' in kwargs:
            logger.info(
                f"[DEBUG] WebSocket message includes discovered_rows: "
                f"{len(kwargs['discovered_rows'])} rows, total_discovered: {kwargs.get('total_discovered', 'N/A')}"
            )

        # Use table-maker-{conversation_id} as card_id for message persistence
        card_id = f"table-maker-{conversation_id}" if conversation_id else "table-maker"
        websocket_client.send_to_session(session_id, message, card_id=card_id)
        logger.info(
            f"[EXECUTION] Progress {progress_percent}% (Step {current_step}/{total_steps}): {status}"
        )
    except Exception as e:
        logger.warning(f"[EXECUTION] Failed to send WebSocket update: {e}")


def send_warning(
    session_id: str,
    conversation_id: str,
    warning_type: str,
    title: str,
    message: str,
    **kwargs
) -> None:
    """
    Send a general warning message to frontend via WebSocket.
    Frontend should display this as an info/warning box at any point in the flow.

    Args:
        session_id: Session identifier
        conversation_id: Conversation identifier (optional, can be None for general warnings)
        warning_type: Type of warning (e.g., 'qc_refused', 'insufficient_rows', 'api_error')
        title: Warning title/heading
        message: Warning message body
        **kwargs: Additional fields (e.g., rows_included, reason, severity)
    """
    if not websocket_client or not session_id:
        return

    try:
        warning_message = {
            'type': 'warning',  # General warning type
            'warning_type': warning_type,  # Specific warning category
            'title': title,
            'message': message,
            **kwargs
        }

        # Add conversation_id if provided
        if conversation_id:
            warning_message['conversation_id'] = conversation_id

        # Use table-maker-{conversation_id} as card_id for message persistence
        card_id = f"table-maker-{conversation_id}" if conversation_id else "table-maker"
        websocket_client.send_to_session(session_id, warning_message, card_id=card_id)
        logger.info(f"[WARNING] Sent {warning_type} warning to frontend: {title}")
    except Exception as e:
        logger.warning(f"[WARNING] Failed to send warning: {e}")


def _parse_markdown_table_with_citations(
    markdown_table: str,
    citations: Dict[str, str],
    columns: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Parse markdown table with citations into rows format.

    Args:
        markdown_table: Markdown table with citations like "| Walmart[1] | $680B[2] |"
        citations: Map of citation numbers to URLs
        columns: Column definitions

    Returns:
        List of row dicts with id_values, research_values, source_urls
    """
    import re

    rows = []

    if not markdown_table:
        return rows

    lines = markdown_table.strip().split('\n')
    if len(lines) < 3:  # Need header, separator, at least 1 data row
        return rows

    # Parse header
    header_line = lines[0].strip()
    headers = [h.strip() for h in header_line.split('|')[1:-1]]  # Skip first/last empty

    # Get ID column names
    id_columns = {col['name'] for col in columns if col.get('importance') == 'ID'}

    # Parse data rows (skip header and separator)
    for line in lines[2:]:
        if not line.strip():
            continue

        cells = [c.strip() for c in line.split('|')[1:-1]]  # Skip first/last empty

        if len(cells) != len(headers):
            continue

        # Extract values and citations from each cell
        row_data = {}
        row_citations = set()
        cell_citations = {}  # NEW: Track which citations belong to which cells

        for header, cell in zip(headers, cells):
            if not cell:
                continue

            # Extract citation numbers [1] [2]
            citation_pattern = r'\[(\d+)\]'
            citations_found = re.findall(citation_pattern, cell)

            # Remove citations from value
            value = re.sub(citation_pattern, '', cell).strip()

            # Add to row data
            if value:
                row_data[header] = value

            # Track citations for this specific cell
            cell_source_urls = []
            for cite_num in citations_found:
                if cite_num in citations:
                    url = citations[cite_num]
                    row_citations.add(url)
                    cell_source_urls.append(url)

            # Store cell-level citations for Excel generation
            if cell_source_urls:
                cell_citations[header] = cell_source_urls

        # Build row in expected format
        if row_data:
            id_values = {k: v for k, v in row_data.items() if k in id_columns}
            research_values = {k: v for k, v in row_data.items() if k not in id_columns}

            rows.append({
                'id_values': id_values,
                'research_values': research_values,
                'source': 'Column Definition (from extracted tables)',
                'source_urls': sorted(list(row_citations)),
                'cell_citations': cell_citations,  # NEW: Per-cell citation URLs
                'populated_columns': list(row_data.keys()),
                'missing_columns': [col['name'] for col in columns if col['name'] not in row_data],
                'match_score': 1.0,
                'model_used': 'column_definition'
            })

    return rows


def _add_api_call_to_runs(
    session_id: str,
    run_key: Optional[str],
    api_response: Dict[str, Any],
    model: str,
    processing_time: float,
    call_type: str,
    status: str = 'IN_PROGRESS',
    verbose_status: str = None,
    percent_complete: int = None
) -> None:
    """
    Add a single API call's metrics to the runs database, aggregating with existing calls.

    This uses the SAME pattern as conversation.py to ensure consistent metrics tracking.

    Flow:
    1. READ existing run record
    2. Extract existing call_metrics_list and models list
    3. Add new call metrics (tagged with call_type)
    4. Build model entry (extracts max_web_searches from enhanced_data)
    5. Re-aggregate ALL calls
    6. WRITE back to database

    Args:
        session_id: Session identifier
        run_key: Run tracking key
        api_response: API response dict from handler with structure:
            {'enhanced_data': {...}, 'model_used': str, 'processing_time': float, ...}
        model: Model name used
        processing_time: Processing time in seconds
        call_type: Type of call (e.g., 'column_definition', 'row_discovery', 'qc_review')
        status: Run status (default: IN_PROGRESS)
        verbose_status: Human-readable status
        percent_complete: Progress percentage (optional)
    """
    if not run_key:
        logger.warning("[EXECUTION] No run_key provided, skipping metrics update")
        return

    try:
        from dynamodb_schemas import get_run_status

        # Step 1: READ existing run record
        existing_run = get_run_status(session_id, run_key)

        # Step 2: Extract existing call_metrics_list and models list (if any)
        existing_call_metrics = []
        existing_models_list = []
        logger.info(f"[EXECUTION] Read existing run: exists={existing_run is not None}")
        if existing_run:
            if 'call_metrics_list' in existing_run:
                existing_call_metrics = existing_run.get('call_metrics_list', [])
                logger.info(f"[EXECUTION] Found {len(existing_call_metrics)} existing API calls in runs database")
            if 'models' in existing_run and isinstance(existing_run['models'], list):
                existing_models_list = existing_run['models']
        else:
            logger.warning(f"[EXECUTION] No existing run found for session_id={session_id}, run_key={run_key}")

        # Step 3: Add NEW call metrics with call_type tag
        # Use enhanced_data directly from API response (already computed by handlers)
        if 'enhanced_data' in api_response and api_response['enhanced_data']:
            new_call_metrics = api_response['enhanced_data']
            logger.debug(f"[EXECUTION] Using pre-computed enhanced_data from API response")
        else:
            # Fallback: regenerate enhanced metrics if not present
            logger.warning(f"[EXECUTION] enhanced_data not found in api_response, regenerating...")
            new_call_metrics = ai_client.get_enhanced_call_metrics(
                response=api_response.get('response', api_response),
                model=model,
                processing_time=processing_time,
                pre_extracted_token_usage=api_response.get('token_usage'),
                is_cached=api_response.get('is_cached', False)
            )

        # Tag with call type for tracking
        new_call_metrics['call_type'] = call_type
        existing_call_metrics.append(new_call_metrics)

        # Extract max_web_searches from enhanced data
        max_web_searches_value = new_call_metrics.get('call_info', {}).get('max_web_searches', 0)

        # Build model entry with web search info
        model_entry = {
            'model': model,
            'call_type': call_type,
            'max_web_searches': max_web_searches_value,
            'is_cached': api_response.get('is_cached', False)
        }
        existing_models_list.append(model_entry)

        logger.info(f"[EXECUTION] Added new {call_type} call metrics for {model}, total calls: {len(existing_call_metrics)}")

        # Step 4: Re-aggregate ALL calls
        aggregated = ai_client.aggregate_provider_metrics(existing_call_metrics)
        providers = aggregated.get('providers', {})
        totals = aggregated.get('totals', {})

        # Step 5: WRITE back to database with aggregated metrics
        total_actual_cost = totals.get('total_cost_actual', 0.0)
        total_estimated_cost = totals.get('total_cost_estimated', 0.0)
        total_actual_time = totals.get('total_actual_processing_time', 0.0)
        total_calls = totals.get('total_calls', 0)

        # Build run_type with operation details
        call_type_names = {
            'interview': 'Interview',
            'background_research': 'Background Research',
            'table_extraction': 'Table Extraction',
            'column_definition': 'Column Definition',
            'row_discovery': 'Row Discovery',
            'qc_review': 'QC Review',
            'config_generation': 'Config Generation'
        }
        operation_sequence = ', '.join([call_type_names.get(c.get('call_type'), c.get('call_type', 'Unknown'))
                                       for c in existing_call_metrics])
        run_type = f"Table Generation ({operation_sequence})" if operation_sequence else "Table Generation"

        update_params = {
            'session_id': session_id,
            'run_key': run_key,
            'status': status,
            'run_type': run_type,
            'verbose_status': verbose_status or f"Completed {total_calls} API calls",
            'models': existing_models_list,
            'eliyahu_cost': total_actual_cost,
            'provider_metrics': providers,
            'total_provider_cost_actual': total_actual_cost,
            'total_provider_cost_estimated': total_estimated_cost,
            'total_provider_tokens': totals.get('total_tokens', 0),
            'total_provider_calls': total_calls,
            'overall_cache_efficiency_percent': totals.get('overall_cache_efficiency', 0.0),
            'actual_processing_time_seconds': total_actual_time,
            'run_time_s': total_actual_time,
            'time_per_row_seconds': total_actual_time / max(total_calls, 1),
            'call_metrics_list': existing_call_metrics,
            'enhanced_metrics_aggregated': aggregated,
            'table_maker_breakdown': {
                'interview_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'interview']),
                'background_research_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'background_research']),
                'table_extraction_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'table_extraction']),
                'column_definition_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'column_definition']),
                'row_discovery_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'row_discovery']),
                'qc_review_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'qc_review']),
                'config_generation_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'config_generation']),
                'total_calls': len(existing_call_metrics)
            }
        }

        if percent_complete is not None:
            update_params['percent_complete'] = percent_complete

        update_run_status(**update_params)

        logger.info(f"[EXECUTION] Updated runs database: {total_calls} total calls, ${total_actual_cost:.6f} total cost")
        logger.info(f"[EXECUTION] Stored enhanced metrics: {len(existing_call_metrics)} call details, {len(providers)} providers")

    except Exception as e:
        logger.error(f"[EXECUTION] Failed to add API call to runs: {e}")
        import traceback
        logger.error(f"[EXECUTION] Traceback: {traceback.format_exc()}")


def _load_conversation_state(
    storage_manager: UnifiedS3Manager,
    email: str,
    session_id: str,
    conversation_id: str
) -> Optional[Dict]:
    """Load conversation state from S3."""
    try:
        s3_key = storage_manager.get_table_maker_path(
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            file_name='conversation_state.json'
        )

        response = storage_manager.s3_client.get_object(
            Bucket=storage_manager.bucket_name,
            Key=s3_key
        )

        conversation_state = json.loads(response['Body'].read().decode('utf-8'))
        logger.info(f"[EXECUTION] Loaded conversation state from S3: {s3_key}")
        return conversation_state

    except Exception as e:
        logger.error(f"[EXECUTION] Error loading conversation state: {e}")
        return None


def _save_to_s3(
    storage_manager: UnifiedS3Manager,
    email: str,
    session_id: str,
    conversation_id: str,
    file_name: str,
    data: Dict
) -> None:
    """Save data to S3."""
    try:
        s3_key = storage_manager.get_table_maker_path(
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            file_name=file_name
        )

        storage_manager.s3_client.put_object(
            Bucket=storage_manager.bucket_name,
            Key=s3_key,
            Body=json.dumps(data, indent=2),
            ContentType='application/json'
        )

        logger.info(f"[EXECUTION] Saved to S3: {s3_key}")

    except Exception as e:
        logger.error(f"[EXECUTION] Failed to save to S3: {e}")


def _save_text_to_s3(
    storage_manager: UnifiedS3Manager,
    email: str,
    session_id: str,
    conversation_id: str,
    file_name: str,
    content: str,
    content_type: str = 'text/markdown'
) -> None:
    """Save text content to S3."""
    try:
        s3_key = storage_manager.get_table_maker_path(
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            file_name=file_name
        )

        storage_manager.s3_client.put_object(
            Bucket=storage_manager.bucket_name,
            Key=s3_key,
            Body=content,
            ContentType=content_type
        )

        logger.info(f"[EXECUTION] Saved text to S3: {s3_key}")

    except Exception as e:
        logger.error(f"[EXECUTION] Failed to save text to S3: {e}")


def _format_citations_section(citations: Dict[str, str]) -> str:
    """Format citations as a markdown section below a table."""
    if not citations:
        return ""

    lines = ["\n**Citations:**"]
    # Sort by numeric key if possible
    sorted_keys = sorted(citations.keys(), key=lambda x: int(x) if x.isdigit() else float('inf'))
    for key in sorted_keys:
        url = citations[key]
        lines.append(f"- [{key}] {url}")
    return "\n".join(lines) + "\n"


def _init_md_tables(
    storage_manager,
    email: str,
    session_id: str,
    conversation_id: str
) -> None:
    """Initialize md_tables.md with header."""
    content = "# Table Maker - Pipeline Tables\n\n"
    content += f"Generated: {__import__('datetime').datetime.now().isoformat()}\n"
    content += "\n*This file is updated continuously as each pipeline stage completes.*\n"

    _save_text_to_s3(
        storage_manager, email, session_id, conversation_id,
        'md_tables.md', content
    )
    logger.info("[MD_TABLES] Initialized md_tables.md")


def _append_md_tables(
    storage_manager,
    email: str,
    session_id: str,
    conversation_id: str,
    new_content: str
) -> None:
    """Append content to md_tables.md."""
    try:
        # Read existing content
        s3_key = storage_manager.get_table_maker_path(
            email=email,
            session_id=session_id,
            conversation_id=conversation_id,
            file_name='md_tables.md'
        )

        existing_content = ""
        try:
            response = storage_manager.s3_client.get_object(
                Bucket=storage_manager.bucket_name,
                Key=s3_key
            )
            existing_content = response['Body'].read().decode('utf-8')
        except Exception:
            # File doesn't exist yet, initialize it
            existing_content = "# Table Maker - Pipeline Tables\n\n"
            existing_content += f"Generated: {__import__('datetime').datetime.now().isoformat()}\n"

        # Append new content
        updated_content = existing_content + "\n" + new_content

        storage_manager.s3_client.put_object(
            Bucket=storage_manager.bucket_name,
            Key=s3_key,
            Body=updated_content,
            ContentType='text/markdown'
        )

        logger.info(f"[MD_TABLES] Appended to md_tables.md")

    except Exception as e:
        logger.warning(f"[MD_TABLES] Failed to append to md_tables.md: {e}")


def _write_background_research_section(
    storage_manager,
    email: str,
    session_id: str,
    conversation_id: str,
    background_research_result: Dict
) -> None:
    """Write Section 0: Background Research to md_tables.md."""
    sections = []
    sections.append("\n---\n")
    sections.append("## 0. Background Research\n")

    if background_research_result:
        # Tablewide Research Summary
        tablewide_research = background_research_result.get('tablewide_research', '')
        if tablewide_research:
            sections.append("### Tablewide Research Summary\n")
            sections.append(tablewide_research)
            sections.append("\n")

        # Authoritative Sources
        sources = background_research_result.get('authoritative_sources', [])
        if sources:
            sections.append("\n### Authoritative Sources\n")
            for src in sources:
                name = src.get('name', 'Unknown')
                url = src.get('url', '')
                description = src.get('description', '')
                sections.append(f"- **{name}**: {description}")
                if url:
                    sections.append(f"  - URL: {url}")
            sections.append("\n")

        # Starting Tables (from background research)
        starting_markdown = background_research_result.get('starting_tables_markdown', '')
        starting_citations = background_research_result.get('citations', {})
        if starting_markdown:
            sections.append("\n### Starting Tables (from Background Research)\n")
            sections.append(starting_markdown)
            sections.append(_format_citations_section(starting_citations))
        else:
            sections.append("\n*No starting tables from background research*\n")
    else:
        sections.append("*No background research performed*\n")

    _append_md_tables(storage_manager, email, session_id, conversation_id, "\n".join(sections))


def _write_extracted_tables_section(
    storage_manager,
    email: str,
    session_id: str,
    conversation_id: str,
    extracted_tables: List[Dict]
) -> None:
    """Write extracted tables (Step 0b) to md_tables.md."""
    sections = []
    sections.append("\n### Extracted Tables (Step 0b)\n")

    if extracted_tables:
        for idx, table in enumerate(extracted_tables, 1):
            table_name = table.get('table_name', f'Table {idx}')
            source_url = table.get('source_url', '')
            rows_count = table.get('rows_extracted', len(table.get('rows', [])))

            sections.append(f"\n#### {idx}. {table_name}\n")
            sections.append(f"- Source: {source_url}")
            sections.append(f"- Rows extracted: {rows_count}\n")

            # If there's markdown table data
            if table.get('markdown_table'):
                sections.append(table['markdown_table'])
            elif table.get('rows'):
                # Convert rows to markdown
                rows_data = table['rows']
                if rows_data:
                    headers = list(rows_data[0].keys())
                    header_line = "| " + " | ".join(headers) + " |"
                    sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
                    data_lines = []
                    for row in rows_data[:20]:  # Limit to 20 rows
                        data_lines.append("| " + " | ".join(str(row.get(h, '')) for h in headers) + " |")
                    sections.append(header_line)
                    sections.append(sep_line)
                    sections.append("\n".join(data_lines))
                    if len(rows_data) > 20:
                        sections.append(f"\n*... and {len(rows_data) - 20} more rows*\n")
            sections.append("\n")
    else:
        sections.append("*No tables extracted*\n")

    _append_md_tables(storage_manager, email, session_id, conversation_id, "\n".join(sections))


def _write_column_definition_section(
    storage_manager,
    email: str,
    session_id: str,
    conversation_id: str,
    column_definition_result: Dict
) -> None:
    """Write Section 1: Column Definition to md_tables.md."""
    sections = []
    sections.append("\n---\n")
    sections.append("## 1. Column Definition (Prepopulated Rows)\n")

    col_def_markdown = column_definition_result.get('prepopulated_rows_markdown', '')
    col_def_citations = column_definition_result.get('citations', {})

    if col_def_markdown:
        sections.append(col_def_markdown)
        sections.append(_format_citations_section(col_def_citations))
    else:
        sections.append("*No prepopulated rows from column definition*\n")

    _append_md_tables(storage_manager, email, session_id, conversation_id, "\n".join(sections))


def _write_discovery_subdomain_header(
    storage_manager,
    email: str,
    session_id: str,
    conversation_id: str,
    subdomain_name: str,
    subdomain_idx: int,
    is_first: bool = False
) -> None:
    """Write subdomain header for discovery section."""
    sections = []

    if is_first:
        sections.append("\n---\n")
        sections.append("## 2. Row Discovery\n")

    sections.append(f"\n### 2.{subdomain_idx}. {subdomain_name}\n")

    _append_md_tables(storage_manager, email, session_id, conversation_id, "\n".join(sections))


def _write_discovery_round_section(
    storage_manager,
    email: str,
    session_id: str,
    conversation_id: str,
    subdomain_name: str,
    round_data: Dict
) -> None:
    """Write a single discovery round to md_tables.md."""
    sections = []

    round_num = round_data.get('round', '?')
    model = round_data.get('model', 'unknown')
    context = round_data.get('context', '')
    count = round_data.get('count', 0)

    sections.append(f"\n#### Round {round_num} ({model}, {context}) - {count} candidates\n")

    round_markdown = round_data.get('candidates_markdown', '')
    round_citations = round_data.get('citations', {})

    if round_markdown:
        sections.append(round_markdown)
        sections.append(_format_citations_section(round_citations))
    else:
        sections.append("*No markdown table for this round*\n")

    _append_md_tables(storage_manager, email, session_id, conversation_id, "\n".join(sections))


def _write_qc_section(
    storage_manager,
    email: str,
    session_id: str,
    conversation_id: str,
    qc_result: Dict,
    approved_rows: List[Dict],
    columns: List[Dict]
) -> None:
    """Write Section 3: Final Approved Table to md_tables.md."""
    sections = []
    sections.append("\n---\n")
    sections.append("## 3. Final Approved Table (Post-QC)\n")

    if approved_rows:
        # Get column names
        id_columns = [col.get('name', '') for col in columns if col.get('importance', '').upper() == 'ID']
        research_columns = [col.get('name', '') for col in columns if col.get('importance', '').upper() != 'ID']
        all_columns = id_columns + research_columns

        # Build markdown table
        header = "| " + " | ".join(all_columns) + " |"
        separator = "| " + " | ".join(["---"] * len(all_columns)) + " |"

        rows = []
        all_citations = {}
        citation_counter = 1

        for row in approved_rows:
            id_values = row.get('id_values', {})
            research_values = row.get('research_values', {})
            cell_citations = row.get('cell_citations', {})

            cells = []
            for col in all_columns:
                value = id_values.get(col, research_values.get(col, ''))
                # Add citation references if available
                col_citations = cell_citations.get(col, [])
                if col_citations:
                    cite_refs = []
                    for url in col_citations:
                        # Find or create citation number
                        found = False
                        for num, existing_url in all_citations.items():
                            if existing_url == url:
                                cite_refs.append(f"[{num}]")
                                found = True
                                break
                        if not found:
                            all_citations[str(citation_counter)] = url
                            cite_refs.append(f"[{citation_counter}]")
                            citation_counter += 1
                    value = f"{value}{''.join(cite_refs)}"
                cells.append(str(value) if value else '')

            rows.append("| " + " | ".join(cells) + " |")

        sections.append(header)
        sections.append(separator)
        sections.append("\n".join(rows))
        sections.append(_format_citations_section(all_citations))

        sections.append(f"\n**Total Approved Rows: {len(approved_rows)}**\n")
    else:
        sections.append("*No rows approved after QC*\n")

    # QC Summary
    if qc_result:
        qc_summary = qc_result.get('qc_summary', {})
        sections.append("\n### QC Summary\n")
        sections.append(f"- Promoted: {qc_summary.get('promoted', 0)}")
        sections.append(f"- Demoted: {qc_summary.get('demoted', 0)}")
        sections.append(f"- Rejected: {qc_summary.get('rejected', 0)}")
        sections.append(f"- Overall Score: {qc_summary.get('overall_score', 'N/A')}\n")

    _append_md_tables(storage_manager, email, session_id, conversation_id, "\n".join(sections))


def _generate_md_tables_content(
    background_research_result: Dict,
    column_definition_result: Dict,
    discovery_result: Dict,
    qc_result: Dict,
    approved_rows: List[Dict],
    columns: List[Dict]
) -> str:
    """
    Generate combined markdown file with all tables from the pipeline.

    Sections:
    0. Background Research (starting tables, extracted tables)
    1. Column Definition (prepopulated rows) + citations
    2. Row Discovery (per round/subdomain) + citations
    3. Final Approved Table (post-QC) + citations
    """
    sections = []

    # Header
    sections.append("# Table Maker - Pipeline Tables\n")
    sections.append(f"Generated: {__import__('datetime').datetime.now().isoformat()}\n")

    # ================================================================
    # SECTION 0: Background Research
    # ================================================================
    sections.append("\n---\n")
    sections.append("## 0. Background Research\n")

    if background_research_result:
        # Tablewide Research Summary
        tablewide_research = background_research_result.get('tablewide_research', '')
        if tablewide_research:
            sections.append("### Tablewide Research Summary\n")
            sections.append(tablewide_research)
            sections.append("\n")

        # Authoritative Sources
        sources = background_research_result.get('authoritative_sources', [])
        if sources:
            sections.append("\n### Authoritative Sources\n")
            for src in sources:
                name = src.get('name', 'Unknown')
                url = src.get('url', '')
                description = src.get('description', '')
                sections.append(f"- **{name}**: {description}")
                if url:
                    sections.append(f"  - URL: {url}")
            sections.append("\n")

        # Starting Tables (from background research)
        starting_markdown = background_research_result.get('starting_tables_markdown', '')
        starting_citations = background_research_result.get('citations', {})
        if starting_markdown:
            sections.append("\n### Starting Tables (from Background Research)\n")
            sections.append(starting_markdown)
            sections.append(_format_citations_section(starting_citations))
        else:
            sections.append("\n*No starting tables from background research*\n")

        # Extracted Tables (from Step 0b)
        extracted_tables = background_research_result.get('extracted_tables', [])
        if extracted_tables:
            sections.append("\n### Extracted Tables (Step 0b)\n")
            for idx, table in enumerate(extracted_tables, 1):
                table_name = table.get('table_name', f'Table {idx}')
                source_url = table.get('source_url', '')
                rows_count = table.get('rows_extracted', len(table.get('rows', [])))

                sections.append(f"\n#### {idx}. {table_name}\n")
                sections.append(f"- Source: {source_url}")
                sections.append(f"- Rows extracted: {rows_count}\n")

                # If there's markdown table data
                if table.get('markdown_table'):
                    sections.append(table['markdown_table'])
                elif table.get('rows'):
                    # Convert rows to markdown
                    rows_data = table['rows']
                    if rows_data:
                        headers = list(rows_data[0].keys())
                        header_line = "| " + " | ".join(headers) + " |"
                        sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
                        data_lines = []
                        for row in rows_data[:20]:  # Limit to 20 rows
                            data_lines.append("| " + " | ".join(str(row.get(h, '')) for h in headers) + " |")
                        sections.append(header_line)
                        sections.append(sep_line)
                        sections.append("\n".join(data_lines))
                        if len(rows_data) > 20:
                            sections.append(f"\n*... and {len(rows_data) - 20} more rows*\n")
                sections.append("\n")
    else:
        sections.append("*No background research performed*\n")

    # ================================================================
    # SECTION 1: Column Definition (Prepopulated Rows)
    # ================================================================
    sections.append("\n---\n")
    sections.append("## 1. Column Definition (Prepopulated Rows)\n")

    col_def_markdown = column_definition_result.get('prepopulated_rows_markdown', '')
    col_def_citations = column_definition_result.get('citations', {})

    if col_def_markdown:
        sections.append(col_def_markdown)
        sections.append(_format_citations_section(col_def_citations))
    else:
        sections.append("*No prepopulated rows from column definition*\n")

    # ================================================================
    # SECTION 2: Row Discovery (Per Round/Subdomain)
    # ================================================================
    sections.append("\n---\n")
    sections.append("## 2. Row Discovery\n")

    stream_results = discovery_result.get('stream_results', [])

    if stream_results:
        for stream_idx, stream in enumerate(stream_results, 1):
            subdomain_name = stream.get('subdomain', f'Subdomain {stream_idx}')
            sections.append(f"\n### 2.{stream_idx}. {subdomain_name}\n")

            all_rounds = stream.get('all_rounds', [])

            if all_rounds:
                for round_data in all_rounds:
                    round_num = round_data.get('round', '?')
                    model = round_data.get('model', 'unknown')
                    context = round_data.get('context', '')
                    count = round_data.get('count', 0)

                    sections.append(f"\n#### Round {round_num} ({model}, {context}) - {count} candidates\n")

                    round_markdown = round_data.get('candidates_markdown', '')
                    round_citations = round_data.get('citations', {})

                    if round_markdown:
                        sections.append(round_markdown)
                        sections.append(_format_citations_section(round_citations))
                    else:
                        sections.append("*No markdown table for this round*\n")
            else:
                # Fallback to stream-level markdown
                stream_markdown = stream.get('candidates_markdown', '')
                stream_citations = stream.get('citations', {})

                if stream_markdown:
                    sections.append(stream_markdown)
                    sections.append(_format_citations_section(stream_citations))
                else:
                    sections.append("*No rows discovered in this subdomain*\n")
    else:
        sections.append("*No row discovery performed*\n")

    # ================================================================
    # SECTION 3: Final Approved Table (Post-QC)
    # ================================================================
    sections.append("\n---\n")
    sections.append("## 3. Final Approved Table (Post-QC)\n")

    if approved_rows:
        # Get column names
        id_columns = [col.get('name', '') for col in columns if col.get('importance', '').upper() == 'ID']
        research_columns = [col.get('name', '') for col in columns if col.get('importance', '').upper() != 'ID']
        all_columns = id_columns + research_columns

        # Build markdown table
        header = "| " + " | ".join(all_columns) + " |"
        separator = "| " + " | ".join(["---"] * len(all_columns)) + " |"

        rows = []
        all_citations = {}
        citation_counter = 1

        for row in approved_rows:
            id_values = row.get('id_values', {})
            research_values = row.get('research_values', {})
            cell_citations = row.get('cell_citations', {})

            cells = []
            for col in all_columns:
                value = id_values.get(col, research_values.get(col, ''))
                # Add citation references if available
                col_citations = cell_citations.get(col, [])
                if col_citations:
                    cite_refs = []
                    for url in col_citations:
                        # Find or create citation number
                        found = False
                        for num, existing_url in all_citations.items():
                            if existing_url == url:
                                cite_refs.append(f"[{num}]")
                                found = True
                                break
                        if not found:
                            all_citations[str(citation_counter)] = url
                            cite_refs.append(f"[{citation_counter}]")
                            citation_counter += 1
                    value = f"{value}{''.join(cite_refs)}"
                cells.append(str(value) if value else '')

            rows.append("| " + " | ".join(cells) + " |")

        sections.append(header)
        sections.append(separator)
        sections.append("\n".join(rows))
        sections.append(_format_citations_section(all_citations))

        sections.append(f"\n**Total Approved Rows: {len(approved_rows)}**\n")
    else:
        sections.append("*No rows approved after QC*\n")

    # QC Summary
    if qc_result:
        qc_summary = qc_result.get('qc_summary', {})
        sections.append("\n### QC Summary\n")
        sections.append(f"- Promoted: {qc_summary.get('promoted', 0)}")
        sections.append(f"- Demoted: {qc_summary.get('demoted', 0)}")
        sections.append(f"- Rejected: {qc_summary.get('rejected', 0)}")
        sections.append(f"- Overall Score: {qc_summary.get('overall_score', 'N/A')}\n")

    return "\n".join(sections)


def _load_config() -> Dict:
    """Load table_maker_config.json."""
    try:
        # Config is in the same directory as this file
        config_path = Path(__file__).parent / 'table_maker_config.json'
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[EXECUTION] Failed to load config: {e}")
        return {}


async def _generate_validation_config(
    email: str,
    session_id: str,
    conversation_id: str,
    conversation_state: Dict,
    columns: list,
    table_name: str
) -> Dict[str, Any]:
    """
    Generate validation config in parallel with row discovery.

    Args:
        email: User email
        session_id: Session identifier
        conversation_id: Conversation identifier
        conversation_state: Conversation state
        columns: Column definitions from column_definition step
        table_name: Table name

    Returns:
        {
            'success': bool,
            'config': Dict (if successful),
            'error': str (if failed)
        }
    """
    try:
        logger.info(f"[CONFIG_GEN] Starting validation config generation for {conversation_id}")

        # Build preview_data structure for config_bridge
        preview_data = {
            'columns': columns,
            'sample_rows': [],  # No rows yet - config is based on columns
            'table_name': table_name
        }

        # Build table_analysis using config_bridge
        table_analysis = build_table_analysis_from_conversation(
            conversation_state=conversation_state,
            preview_data=preview_data,
            table_rows=None  # No rows yet
        )

        logger.info(f"[CONFIG_GEN] Built table_analysis with {len(columns)} columns")

        # Call config generation handler
        config_event = {
            'email': email,
            'session_id': session_id,
            'table_analysis': table_analysis,
            'instructions': f'Generate validation configuration for table: {table_name}'
        }

        config_result = await handle_generate_config_unified(
            config_event,
            websocket_callback=None,
            table_maker_mode=True  # Use Table Maker mode - skip CSV parsing
        )

        if config_result.get('success'):
            logger.info(f"[CONFIG_GEN] Config generation succeeded")
            return {
                'success': True,
                'config': config_result.get('updated_config'),
                'config_s3_key': config_result.get('config_s3_key'),
                'config_version': config_result.get('config_version')
            }
        else:
            error_msg = config_result.get('error', 'Unknown config generation error')
            logger.warning(f"[CONFIG_GEN] Config generation failed: {error_msg}")
            return {
                'success': False,
                'error': error_msg
            }

    except Exception as e:
        logger.error(f"[CONFIG_GEN] Config generation error: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }


def _merge_rows_with_preference(
    initial_rows: list,
    discovered_rows: list,
    id_column_names: list
) -> list:
    """
    Merge initial rows from column definition with discovered rows from discovery phase.
    Discovery rows take precedence for duplicates (newer/better data).

    Args:
        initial_rows: Rows generated by column definition (from any source)
        discovered_rows: Rows from discovery phase (from web search)
        id_column_names: Names of ID columns for deduplication

    Returns:
        Merged list of rows with duplicates removed (discovered rows preferred)
    """
    if not initial_rows:
        return discovered_rows

    if not discovered_rows:
        return initial_rows

    # Build lookup of discovered rows by ID values
    discovered_lookup = {}
    for row in discovered_rows:
        id_values = row.get('id_values', {})
        # Create key from ID column values (normalized)
        id_key = tuple(sorted([
            (col, str(id_values.get(col, '')).lower().strip())
            for col in id_column_names
        ]))
        discovered_lookup[id_key] = row

    # Add initial rows that aren't duplicates
    merged = list(discovered_rows)  # Start with all discovered rows
    added_from_initial = 0

    for initial_row in initial_rows:
        id_values = initial_row.get('id_values', {})
        id_key = tuple(sorted([
            (col, str(id_values.get(col, '')).lower().strip())
            for col in id_column_names
        ]))

        if id_key not in discovered_lookup:
            # Not a duplicate - add it
            merged.append(initial_row)
            added_from_initial += 1

    logger.info(
        f"[MERGE] Final result: {len(discovered_rows)} from discovery + "
        f"{added_from_initial} unique from column_definition = {len(merged)} total"
    )

    return merged


async def execute_full_table_generation(
    email: str,
    session_id: str,
    conversation_id: str,
    run_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute the complete Independent Row Discovery pipeline with parallel config generation.

    This function uses LOCAL components (from table_maker/src/) directly.
    It only adds Lambda infrastructure wrappers (S3, WebSocket, runs DB).

    Pipeline Flow:
        Step 0: Background Research (~30-60s, internal)
            - Find authoritative sources and starting tables
            - Extract sample entities
            - On restructure: Use cached research (skip this step)
            ↓
        Step 0b: Table Extraction (OPTIONAL, ~20-40s, sequential after Step 0)
            - Triggered if Step 0 identified extractable tables
            - Extracts complete tables from URLs
            - Uses site-specific search
            ↓
        Step 1: Column Definition (~10-20s)
            - Use research output to design table structure
            - Generate rows from: extracted_tables, starting_tables, conversation, or model knowledge
            - Populate all columns with reliable data (ID + research columns)
            - Decide: trigger_row_discovery (true/false)
            ↓
        Step 2: Row Discovery + Config Generation (CONDITIONAL - only if trigger_row_discovery=true)
            ├─→ Row Discovery (60-120s) - progressive escalation
            │   - Merge initial_rows (from column_definition) with discovered rows
            └─→ Config Generation (20-40s) - runs in background
            ↓
        [Row Discovery + Merge completes, OR skipped if trigger_row_discovery=false]
            ↓
        Step 3: QC Review starts immediately (~8-15s) - doesn't wait for config
            - Reviews merged rows (initial + discovered, OR just initial rows)
            ↓
        [QC Review completes]
            ↓
        MUTUAL COMPLETION: Wait for Config Generation to finish
            ↓
        Generate CSV: ID columns filled, other columns empty
            ↓
        Complete

    Total Duration: ~2-3.5 minutes (research adds ~30-60s, but cached on restructure)
    Total Cost: ~$0.07-0.25 (includes research + config generation)

    Args:
        email: User email
        session_id: Session identifier
        conversation_id: Conversation identifier
        run_key: Run tracking key (optional)

    Returns:
        {
            'success': bool,
            'conversation_id': str,
            'table_name': str,
            'row_count': int,
            'approved_rows': List[Dict],
            'config_generated': bool,
            'config_s3_key': str (if config succeeded),
            'config_version': int (if config succeeded),
            'csv_s3_key': str,
            'csv_filename': str,
            'error': Optional[str]
        }
    """
    result = {
        'success': False,
        'conversation_id': conversation_id,
        'table_name': None,
        'row_count': 0,
        'approved_rows': [],
        'error': None
    }

    # Initialize variables that may be skipped in complete enumeration mode
    original_discovered_count = 0

    try:
        logger.info(f"[EXECUTION] Starting Independent Row Discovery pipeline for {conversation_id}")

        # Initialize timeout guard to track elapsed time
        timeout_guard = TimeoutGuard()
        logger.info(f"[TIMEOUT] Initialized timeout guard. Deadline in {timeout_guard.remaining():.0f}s")

        # Initialize storage manager
        storage_manager = UnifiedS3Manager()

        # Load conversation state from S3
        conversation_state = _load_conversation_state(
            storage_manager, email, session_id, conversation_id
        )

        if not conversation_state:
            result['error'] = f'Conversation {conversation_id} not found'
            logger.error(f"[EXECUTION] {result['error']}")
            return result

        # Get or create run_key
        if not run_key:
            run_key = conversation_state.get('run_key')
            if not run_key:
                logger.warning("[EXECUTION] No run_key available, metrics tracking disabled")

        # Load config
        config = _load_config()

        # Initialize LOCAL components (same as local test)
        # Use module-level singleton

        # Prompts and schemas are in subdirectories
        prompts_dir = str(Path(__file__).parent / 'prompts')
        schemas_dir = str(Path(__file__).parent / 'schemas')

        prompt_loader = PromptLoader(prompts_dir)
        schema_validator = SchemaValidator(schemas_dir)

        background_research_handler = BackgroundResearchHandler(ai_client, prompt_loader, schema_validator)
        table_extraction_handler = TableExtractionHandler(ai_client, prompt_loader, schema_validator)
        column_handler = ColumnDefinitionHandler(ai_client, prompt_loader, schema_validator)
        row_discovery = RowDiscovery(ai_client, prompt_loader, schema_validator)
        qc_reviewer = QCReviewer(ai_client, prompt_loader, schema_validator)

        # Send initial progress
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=0,
            total_steps=4,
            status='Starting table generation pipeline',
            progress_percent=0
        )

        # Update runs database
        if run_key:
            try:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='IN_PROGRESS',
                    run_type='Table Generation (Background Research + Row Discovery)',
                    verbose_status='Starting 5-step pipeline (Step 0 internal)',
                    percent_complete=0
                )
            except Exception as e:
                logger.warning(f"[EXECUTION] Failed to update run status: {e}")

        # ======================================================================
        # STEP 0: Background Research (Internal - Always runs or uses cache)
        # ======================================================================
        logger.info("[EXECUTION] Step 0 (Internal): Background Research")

        # Check for cached research (restructure mode)
        cached_research = conversation_state.get('cached_background_research')

        if cached_research:
            logger.info("[STEP 0] Using cached background research (restructure mode - skipping research)")
            background_research_result = cached_research

            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=0,
                total_steps=4,
                status='Using cached domain research (restructure mode)',
                progress_percent=10
            )
        else:
            logger.info("[STEP 0] Running background research (finding authoritative sources and starting tables)")

            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=0,
                total_steps=4,
                status='Researching domain and finding authoritative sources...',
                progress_percent=5
            )

            # Get research config
            research_config = config.get('background_research', {})

            # Run background research
            background_research_result = await background_research_handler.conduct_research(
                conversation_context=conversation_state,
                context_research_items=conversation_state.get('context_web_research', []),
                model=research_config.get('model', 'sonar-pro'),
                max_tokens=research_config.get('max_tokens', 8000),
                search_context_size=research_config.get('search_context_size', 'high'),
                max_web_searches=research_config.get('max_web_searches', 5)
            )

            # Validate success
            if not background_research_result.get('success'):
                error_msg = background_research_result.get('error', 'Background research failed')
                logger.error(f"[STEP 0] Background research failed: {error_msg}")
                result['error'] = f'Background research failed: {error_msg}'
                return result

            # Save to S3
            _save_to_s3(
                storage_manager, email, session_id, conversation_id,
                'background_research_result.json', background_research_result
            )

            # Initialize and write to md_tables.md
            _init_md_tables(storage_manager, email, session_id, conversation_id)
            _write_background_research_section(
                storage_manager, email, session_id, conversation_id,
                background_research_result
            )

            # NOTE: We intentionally do NOT store background research sources to agent_memory here.
            # authoritative_sources contains brief descriptions, not actual URL content.
            # Storing them would pollute memory with snippets that pass keyword validation
            # but don't contain actual data. Table extractions (Step 0b) store full content.

            # Track API call
            _add_api_call_to_runs(
                session_id=session_id,
                run_key=run_key,
                api_response=background_research_result,
                model=research_config.get('model', 'claude-haiku-4-5'),
                processing_time=background_research_result.get('processing_time', 0.0),
                call_type='background_research',
                status='IN_PROGRESS',
                verbose_status='Background research complete'
            )

            # Send completion update
            sources_count = len(background_research_result.get('authoritative_sources', []))
            # Count rows from markdown table (exclude header and separator lines)
            starting_markdown = background_research_result.get('starting_tables_markdown', '')
            rows_count = len([line for line in starting_markdown.split('\n')
                            if line.strip().startswith('|') and not line.strip().startswith('|-')]) - 1  # -1 for header
            rows_count = max(0, rows_count)  # Ensure non-negative

            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=0,
                total_steps=4,
                status=f'Background research complete ({sources_count} sources, {rows_count} starting entities)',
                progress_percent=25,
                research_sources_count=sources_count,
                starting_tables_count=rows_count
            )

            logger.info(
                f"[STEP 0] Background research complete: "
                f"{sources_count} authoritative sources, "
                f"{rows_count} starting entities, "
                f"time: {background_research_result.get('processing_time', 0):.2f}s"
            )

        # ======================================================================
        # STEP 0b: Table Extraction (Optional - Sequential after background research)
        # ======================================================================
        # Only runs if background research identified extractable tables
        if background_research_result.get('success') and not cached_research:
            identified_tables = background_research_result.get('identified_tables', [])
            tables_to_extract = [t for t in identified_tables if t.get('extract_table')]

            # Validate table URLs against citations to prevent hallucinated URLs
            if tables_to_extract:
                # Extract citations from background research
                enhanced_data = background_research_result.get('enhanced_data', {})
                citations = enhanced_data.get('citations', []) if enhanced_data else []

                if citations:
                    # Create set of citation URLs for fast lookup (normalized)
                    from urllib.parse import urlparse
                    import re

                    def normalize_url(url):
                        """Normalize URL for comparison (remove protocol, www, trailing /)."""
                        if not url:
                            return ''
                        normalized = url.lower()
                        normalized = re.sub(r'^https?://', '', normalized)
                        normalized = re.sub(r'^www\.', '', normalized)
                        normalized = re.sub(r'/$', '', normalized)
                        return normalized

                    citation_urls = {normalize_url(c.get('url', '')) for c in citations if c.get('url')}

                    # Filter tables to only those with URLs in citations
                    validated_tables = []
                    filtered_tables = []

                    for table in tables_to_extract:
                        table_url = table.get('url', '')
                        normalized_table_url = normalize_url(table_url)

                        # Check if table URL is in citations (exact match after normalization)
                        if normalized_table_url in citation_urls:
                            validated_tables.append(table)
                        else:
                            filtered_tables.append(table)
                            logger.warning(
                                f"[TABLE_URL_VALIDATION] Filtered table '{table.get('table_name')}' - "
                                f"URL not in citations: {table_url}"
                            )

                    # Update tables_to_extract to only validated tables
                    tables_to_extract = validated_tables

                    if filtered_tables:
                        logger.info(
                            f"[TABLE_URL_VALIDATION] Filtered {len(filtered_tables)}/{len(validated_tables) + len(filtered_tables)} tables. "
                            f"Proceeding with {len(validated_tables)} validated tables."
                        )
                else:
                    logger.warning("[TABLE_URL_VALIDATION] No citations available - skipping URL validation")

            if tables_to_extract:
                logger.info(f"[STEP 0b] Extracting {len(tables_to_extract)} identified tables")

                # Get config for table extraction
                extraction_config = config.get('table_extraction', {})
                extraction_model = extraction_config.get('model', 'sonar')
                extraction_max_tokens = extraction_config.get('max_tokens', 16000)
                extraction_context_size = extraction_config.get('search_context_size', 'high')
                extraction_max_web_searches = extraction_config.get('max_web_searches', 3)
                extraction_timeout = extraction_config.get('timeout', 120)

                try:
                    table_extraction_result = await table_extraction_handler.extract_tables(
                        identified_tables=tables_to_extract,
                        conversation_context=conversation_state,
                        model=extraction_model,
                        max_tokens=extraction_max_tokens,
                        search_context_size=extraction_context_size,
                        max_web_searches=extraction_max_web_searches,
                        timeout=extraction_timeout
                    )

                    if table_extraction_result.get('success'):
                        extracted_tables = table_extraction_result.get('extracted_tables', [])
                        total_rows = table_extraction_result.get('total_rows_extracted', 0)

                        # Merge extracted tables into background_research_result
                        background_research_result['extracted_tables'] = extracted_tables

                        logger.info(
                            f"[STEP 0b] Table extraction complete: "
                            f"{len(extracted_tables)}/{len(tables_to_extract)} tables, "
                            f"{total_rows} total rows, "
                            f"time: {table_extraction_result.get('processing_time', 0):.2f}s"
                        )

                        # Save extraction result to S3
                        _save_to_s3(
                            storage_manager, email, session_id, conversation_id,
                            'table_extraction_result.json', table_extraction_result
                        )

                        # CRITICAL: Update background_research_result in S3 with extracted_tables
                        # This ensures restructure can access the extracted tables
                        _save_to_s3(
                            storage_manager, email, session_id, conversation_id,
                            'background_research_result.json', background_research_result
                        )
                        logger.info("[STEP 0b] Updated background_research_result in S3 with extracted_tables")

                        # Write extracted tables to md_tables.md
                        _write_extracted_tables_section(
                            storage_manager, email, session_id, conversation_id,
                            extracted_tables
                        )

                        # CRITICAL: Store extracted tables to agent_memory for validation
                        # This makes the full table content available when validation looks up source URLs
                        # Uses MemoryCache for RAM-based storage (flushed to S3 at batch end)
                        if SEARCH_MEMORY_AVAILABLE and extracted_tables:
                            try:
                                # First ensure memory is loaded into cache (loads from S3 if not cached)
                                MemoryCache.get(session_id, email, storage_manager, ai_client)

                                tables_stored = 0

                                for table_data in extracted_tables:
                                    source_url = table_data.get('source_url', '')
                                    markdown_table = table_data.get('markdown_table', '')
                                    table_name = table_data.get('table_name', 'Extracted Table')

                                    if source_url and markdown_table:
                                        # Store the markdown table content with metadata (RAM only, no S3 write)
                                        MemoryCache.store_url_content(
                                            session_id=session_id,
                                            url=source_url,
                                            content=markdown_table,
                                            title=table_name,
                                            source_type='table_extraction',
                                            metadata={
                                                'rows_count': table_data.get('rows_count', 0),
                                                'columns_found': table_data.get('columns_found', []),
                                                'extraction_method': table_data.get('extraction_method', 'unknown'),
                                                'session_id': session_id,
                                                'conversation_id': conversation_id
                                            }
                                        )
                                        tables_stored += 1

                                        # Also store for each source_url in source_urls (multi-source extractions)
                                        for alt_url in table_data.get('source_urls', []):
                                            if alt_url and alt_url != source_url:
                                                MemoryCache.store_url_content(
                                                    session_id=session_id,
                                                    url=alt_url,
                                                    content=markdown_table,
                                                    title=f"{table_name} (via {alt_url})",
                                                    source_type='table_extraction_alt',
                                                    metadata={
                                                        'primary_url': source_url,
                                                        'rows_count': table_data.get('rows_count', 0),
                                                        'columns_found': table_data.get('columns_found', [])
                                                    }
                                                )

                                logger.info(
                                    f"[STEP 0b] Stored {tables_stored} extracted tables to agent_memory "
                                    f"(RAM cache, will flush at batch end)"
                                )
                            except Exception as mem_error:
                                logger.warning(
                                    f"[STEP 0b] Failed to store tables to memory (non-fatal): {mem_error}"
                                )
                                # Continue anyway - memory storage is enhancement, not critical path

                        # Track API calls from table extraction
                        # enhanced_data is a list of API call metadata from all extractions
                        for enhanced_data_item in table_extraction_result.get('enhanced_data', []):
                            _add_api_call_to_runs(
                                session_id=session_id,
                                run_key=run_key,
                                api_response={'enhanced_data': enhanced_data_item},
                                model=extraction_model,
                                processing_time=table_extraction_result.get('processing_time', 0.0),
                                call_type='table_extraction'
                            )
                    else:
                        logger.warning(
                            f"[STEP 0b] Table extraction failed: {table_extraction_result.get('error')}"
                        )
                        # Continue anyway - extraction is optional

                except Exception as e:
                    logger.error(f"[STEP 0b] Table extraction error: {str(e)}", exc_info=True)
                    # Continue anyway - extraction is optional
            else:
                logger.info("[STEP 0b] No tables identified for extraction, skipping")

        # No checkpoint needed - interview ensures document text is pasted upfront
        # Background research and column definition extract from conversation

        # ======================================================================
        # STEP 1: Column Definition
        # ======================================================================
        logger.info("[EXECUTION] Step 1/4: Column Definition (using background research)")

        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=1,
            total_steps=4,
            status='Step 1/4: Defining columns and search strategy using background research',
            progress_percent=30
        )

        try:
            # Get config for column definition
            col_config = config.get('column_definition', {})
            col_model = col_config.get('model', 'claude-sonnet-4-5')
            col_max_tokens = col_config.get('max_tokens', 8000)

            # Call column definition handler with background research
            column_result = await column_handler.define_columns(
                conversation_context=conversation_state,
                background_research_result=background_research_result,  # NEW - from Step 0
                model=col_model,
                max_tokens=col_max_tokens
            )

            if not column_result.get('success'):
                result['error'] = f"Column definition failed: {column_result.get('error')}"
                logger.error(f"[EXECUTION] {result['error']}")
                return result

            columns = column_result['columns']
            search_strategy = column_result['search_strategy']
            table_name = column_result.get('table_name', 'Unknown Table')

            # Handle NEW markdown format or OLD rows array format
            if 'prepopulated_rows_markdown' in column_result:
                # NEW: Parse markdown table with citations
                markdown_table = column_result.get('prepopulated_rows_markdown', '')
                citations = column_result.get('citations', {})
                initial_rows = _parse_markdown_table_with_citations(markdown_table, citations, columns)
                logger.info(f"[STEP 1] Parsed {len(initial_rows)} rows from markdown table with {len(citations)} citations")

                # Store citations dictionary in conversation_state for Excel generation
                conversation_state['citations'] = citations
                logger.info(f"[STEP 1] Stored {len(citations)} citations in conversation_state for Excel generation")
            else:
                # OLD: Use rows array directly (backward compatibility)
                initial_rows = column_result.get('rows', [])
                logger.info(f"[STEP 1] Using {len(initial_rows)} rows from legacy format")

            result['table_name'] = table_name

            if initial_rows:
                rows_with_research = sum(1 for row in initial_rows if row.get('research_values'))
                logger.info(
                    f"[STEP 1] Column definition generated {len(initial_rows)} rows "
                    f"({rows_with_research} with research columns populated)"
                )

            # Track API call
            _add_api_call_to_runs(
                session_id=session_id,
                run_key=run_key,
                api_response=column_result,
                model=column_result.get('model_used', col_model),
                processing_time=column_result.get('processing_time', 0.0),
                call_type='column_definition',
                status='IN_PROGRESS',
                verbose_status='Column definition complete',
                percent_complete=20
            )

            # Save to S3
            _save_to_s3(
                storage_manager, email, session_id, conversation_id,
                'column_definition_result.json', column_result
            )

            # Write column definition section to md_tables.md
            _write_column_definition_section(
                storage_manager, email, session_id, conversation_id,
                column_result
            )

            logger.info(f"[EXECUTION] Step 1 complete: {len(columns)} columns, table: {table_name}")

            # Add tablewide_research to conversation_state for config generation
            # tablewide_research comes from background research (Step 0), not column definition
            conversation_state['tablewide_research'] = background_research_result.get('tablewide_research', '')
            if conversation_state.get('tablewide_research'):
                logger.info(f"[EXECUTION] Stored tablewide_research from background research in conversation_state for config generation")

            # Create minimal CSV with column headers for config generation
            import csv
            import io
            csv_buffer = io.StringIO()
            csv_writer = csv.writer(csv_buffer, quoting=csv.QUOTE_ALL)  # Quote all fields to handle commas

            # Write column headers
            column_names = [col['name'] for col in columns]
            csv_writer.writerow(column_names)

            csv_content = csv_buffer.getvalue()

            # Save minimal CSV directly in session folder so config generation can find it
            # Session path already includes results/{domain}/{email}/{session_id}/
            csv_filename = f"{table_name.replace(' ', '_')}_template.csv"
            session_path = storage_manager.get_session_path(email, session_id)
            csv_s3_key = f"{session_path}{csv_filename}"

            storage_manager.s3_client.put_object(
                Bucket=storage_manager.bucket_name,
                Key=csv_s3_key,
                Body=csv_content,
                ContentType='text/csv'
            )
            logger.info(f"[EXECUTION] Created minimal CSV for config generation: {csv_s3_key}")

            # Extract requirements for frontend display
            # These are formatted in column_definition_handler.py (lines 182-185)
            formatted_hard_requirements = column_result.get('formatted_hard_requirements', '')
            formatted_soft_requirements = column_result.get('formatted_soft_requirements', '')

            logger.info(
                f"[DEBUG] Requirements extracted: "
                f"hard={repr(formatted_hard_requirements)}, "
                f"soft={repr(formatted_soft_requirements)}"
            )

            # Send progress update with columns, table_name, and requirements
            # FRONTEND IMPLEMENTATION NOTE:
            # The 'requirements' object should be displayed BEFORE the ID columns box.
            # Display format:
            #   - Show "Hard Requirements" section with formatted_hard_requirements (red/bold styling)
            #   - Show "Soft Requirements" section with formatted_soft_requirements (yellow/normal styling)
            #   - Requirements are formatted as bullet lists from column_definition_handler.py
            logger.info(
                f"[DEBUG] Sending WebSocket with requirements to frontend: "
                f"has_requirements={bool(formatted_hard_requirements or formatted_soft_requirements)}"
            )

            logger.info(
                f"[DEBUG] Sending WebSocket with columns and requirements"
            )

            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=1,
                total_steps=4,
                status=f'Column definition complete: {table_name}',
                progress_percent=20,
                columns=columns,
                table_name=table_name,
                requirements={
                    'hard': formatted_hard_requirements,
                    'soft': formatted_soft_requirements
                }
            )

        except Exception as e:
            result['error'] = f"Column definition error: {str(e)}"
            logger.error(f"[EXECUTION] {result['error']}", exc_info=True)
            return result

        # ======================================================================
        # CHECK: Should We Skip Row Discovery?
        # ======================================================================
        # Column definition generates rows and decides if discovery is needed
        # initial_rows already extracted above at line 949
        trigger_row_discovery = column_result.get('trigger_row_discovery', True)
        skip_rationale = column_result.get('skip_rationale')
        discovery_guidance = column_result.get('discovery_guidance')

        if not trigger_row_discovery:
            # Column definition provided complete set - skip discovery and QC
            logger.info(f"[EXECUTION] SKIP MODE: Column definition generated {len(initial_rows)} rows, row discovery not needed")
            logger.info(f"[EXECUTION] Skip rationale: {skip_rationale}")

            # Check how many columns are populated
            rows_with_research = sum(1 for row in initial_rows if row.get('research_values'))
            logger.info(f"[EXECUTION] {rows_with_research}/{len(initial_rows)} rows have research columns populated")

            # Use initial_rows as final_rows
            final_rows = initial_rows

            # Add model_used field if not present
            for row in final_rows:
                if 'model_used' not in row:
                    row['model_used'] = 'column_definition'
                if 'match_score' not in row:
                    row['match_score'] = 1.0

            # Send progress update
            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=2,
                total_steps=4,
                status=f'Using {len(final_rows)} rows from column definition (row discovery skipped)',
                progress_percent=50
            )

            # Use rows as approved_rows (no QC needed)
            approved_rows = final_rows
            original_discovered_count = len(final_rows)
            qc_result = {
                'success': True,
                'approved_rows': approved_rows,
                'skipped': True,
                'skip_rationale': skip_rationale
            }

            # Save placeholder discovery result
            discovery_result = {
                'success': True,
                'final_rows': final_rows,
                'stream_results': [],
                'stats': {
                    'total_candidates_found': len(final_rows),
                    'duplicates_removed': 0,
                    'below_threshold': 0
                },
                'skipped': True,
                'skip_rationale': skip_rationale
            }
            _save_to_s3(
                storage_manager, email, session_id, conversation_id,
                'discovery_result.json', discovery_result
            )

            # Save placeholder QC result
            _save_to_s3(
                storage_manager, email, session_id, conversation_id,
                'qc_result.json', qc_result
            )

            logger.info(f"[EXECUTION] Steps 2-4 skipped. Proceeding to config generation and CSV.")

            # Jump to config generation and CSV creation (after the QC section)
            # We'll set a flag and let the code flow continue
            skip_to_csv_generation = True
            retry_count = 0  # No retries in skip path
        else:
            skip_to_csv_generation = False

        # ======================================================================
        # STEP 2: Row Discovery + Config Generation (PARALLEL)
        # ======================================================================
        # Extract subdomains count (needed for validation and parallel config)
        num_subdomains = len(search_strategy.get('subdomains', []))

        if not skip_to_csv_generation:
            logger.info("[EXECUTION] Step 2/4: Row Discovery + Config Generation (parallel)")

            # Validate that subdomains exist if row discovery triggered
            if trigger_row_discovery and num_subdomains == 0:
                error_msg = (
                    "COLUMN DEFINITION ERROR: trigger_row_discovery=true but no subdomains provided in search_strategy. "
                    f"Column definition generated {len(initial_rows)} rows. "
                    "This likely means the AI should have set trigger_row_discovery=false (rows are complete enough) "
                    "OR it forgot to include the mandatory 'subdomains' array in search_strategy. "
                    "Check column_definition_result.json for the AI's output."
                )
                logger.error(f"[EXECUTION] {error_msg}")
                logger.error(f"[EXECUTION] Initial rows count: {len(initial_rows)}")
                logger.error(f"[EXECUTION] Discovery guidance: {discovery_guidance}")
                logger.error(f"[EXECUTION] Skip rationale: {skip_rationale}")
                result['error'] = error_msg
                return result

            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=2,
                total_steps=4,
                status='Finding and checking candidate rows...',
                progress_percent=25
            )

        # Start config generation as background task (runs in parallel)
        # NOTE: Config generation runs regardless of skip_to_csv_generation
        config_generation_task = None

        # Skip row discovery if we already have complete rows from column definition
        if skip_to_csv_generation:
            logger.info("[EXECUTION] Skipping row discovery (using rows from column definition)")
            # final_rows and approved_rows were already set above
            # Just need to initialize discovery_result for later use
            discovery_result = {
                'success': True,
                'final_rows': final_rows,
                'stream_results': [],
                'stats': {'source': 'column_definition_skip'}
            }
            total_discovered_count = len(final_rows)
            original_discovered_count = total_discovered_count

        # Row discovery path (when trigger_row_discovery=true)
        if not skip_to_csv_generation:
            try:
                # Get config for row discovery
                discovery_config = config.get('row_discovery', {})
                escalation_strategy = discovery_config.get('escalation_strategy', [])
                min_match_score = discovery_config.get('min_match_score', 0.6)
                check_targets_between_subdomains = discovery_config.get('check_targets_between_subdomains', False)
                early_stop_threshold_percentage = discovery_config.get('early_stop_threshold_percentage', 120)
                soft_schema = discovery_config.get('soft_schema', True)
                config_max_parallel = discovery_config.get('max_parallel_streams')
                if config_max_parallel is None:
                    max_parallel_streams = min(num_subdomains, 5)
                    logger.info(
                        f"[EXECUTION] Dynamic max_parallel_streams: {max_parallel_streams} "
                        f"(min of {num_subdomains} subdomains and 5)"
                    )
                else:
                    max_parallel_streams = config_max_parallel
                    logger.info(
                        f"[EXECUTION] Using config max_parallel_streams: {max_parallel_streams}"
                    )

                # Create WebSocket callback for row discovery
                def websocket_callback(**kwargs):
                    """Wrapper to send row discovery progress updates via WebSocket."""
                    # Extract required positional args from kwargs
                    progress_percent = kwargs.pop('progress_percent', 25)
                    status = kwargs.pop('status', 'Discovering rows...')

                    # If discovered_rows are included, format them with rounded scores
                    if 'discovered_rows' in kwargs:
                        raw_rows = kwargs.pop('discovered_rows')
                        kwargs['discovered_rows'] = [
                            {
                                "id_values": row.get("id_values", {}),
                                "row_score": round(row.get("match_score", 0), 2)
                            }
                            for row in raw_rows[:15]  # First 15 rows only
                        ]

                    send_execution_progress(
                        session_id=session_id,
                        conversation_id=conversation_id,
                        current_step=2,
                        total_steps=4,
                        status=status,
                        progress_percent=progress_percent,
                        **kwargs  # Now kwargs doesn't have 'status' or 'progress_percent'
                    )

                # Start config generation in background (don't wait for it)
                logger.info("[EXECUTION] Starting config generation in background")
                config_generation_task = asyncio.create_task(
                    _generate_validation_config(
                        email=email,
                        session_id=session_id,
                        conversation_id=conversation_id,
                        conversation_state=conversation_state,
                        columns=columns,
                        table_name=table_name
                    )
                )

                # Check timeout before starting row discovery
                if not timeout_guard.can_do_discovery_qc_cycle():
                    logger.warning(
                        f"[TIMEOUT] Insufficient time for discovery+QC cycle. "
                        f"Remaining: {timeout_guard.remaining():.0f}s, needed: {MIN_TIME_FOR_DISCOVERY_QC}s. "
                        f"Skipping row discovery and using initial rows only."
                    )
                    # Skip row discovery, use initial rows only
                    final_rows = initial_rows if initial_rows else []
                    discovery_result = {'success': True, 'final_rows': [], 'stream_results': [], 'timeout_skip': True}
                    stream_results = []
                    discovery_only_rows = []
                    # Send WebSocket update about timeout
                    send_execution_progress(
                        session_id=session_id,
                        conversation_id=conversation_id,
                        current_step=2,
                        total_steps=4,
                        status='Time constraints - using initial rows only',
                        progress_percent=60
                    )
                else:
                    # Run row discovery (wait for completion before starting QC)
                    logger.info(f"[EXECUTION] Starting row discovery (time remaining: {timeout_guard.remaining():.0f}s)")

                    # Handle target_row_count: -1 = find all, positive = specific count
                    user_target = conversation_state.get('target_row_count', -1)
                    if user_target == -1:
                        # Find all mode - capped at safety limit
                        target_row_count = FIND_ALL_SAFETY_CAP
                        logger.info(f"[EXECUTION] Find-all mode: targeting up to {FIND_ALL_SAFETY_CAP} rows")
                    else:
                        # Amplify for discovery, QC will trim back
                        target_row_count = int(user_target * DISCOVERY_AMPLIFICATION)
                        logger.info(f"[EXECUTION] User requested {user_target} rows, discovery targeting {target_row_count} (1.5x)")

                    discovery_result = await row_discovery.discover_rows(
                        search_strategy=search_strategy,
                        columns=columns,
                        target_row_count=target_row_count,
                        discovery_multiplier=1.5,
                        min_match_score=min_match_score,
                        max_parallel_streams=max_parallel_streams,
                        escalation_strategy=escalation_strategy,
                        check_targets_between_subdomains=check_targets_between_subdomains,
                        early_stop_threshold_percentage=early_stop_threshold_percentage,
                        websocket_callback=websocket_callback,
                        soft_schema=soft_schema
                    )

                    # Check if row discovery succeeded (critical)
                    if not discovery_result.get('success'):
                        result['error'] = f"Row discovery failed: {discovery_result.get('error')}"
                        logger.error(f"[EXECUTION] {result['error']}")
                        return result

                    # Get rows from discovery (BEFORE merging with initial_rows)
                    # This is what QC should review as "discovered" rows
                    discovery_only_rows = discovery_result.get('final_rows', [])
                    stream_results = discovery_result.get('stream_results', [])

                    logger.info(f"[DISCOVERY] Row discovery found {len(discovery_only_rows)} new rows")

                    # Merge initial_rows from column definition with discovered rows for final output
                    if initial_rows:
                        logger.info(f"[MERGE] Merging {len(initial_rows)} initial rows with {len(discovery_only_rows)} discovered rows")
                        final_rows = _merge_rows_with_preference(
                            initial_rows=initial_rows,
                            discovered_rows=discovery_only_rows,
                            id_column_names=[col['name'] for col in columns if col.get('importance') == 'ID']
                        )
                        logger.info(f"[MERGE] After merge: {len(final_rows)} total rows")
                    else:
                        final_rows = discovery_only_rows

                # Track each subdomain's API calls and write to md_tables.md
                for subdomain_idx, stream_result in enumerate(stream_results, 1):
                    subdomain_name = stream_result.get('subdomain', 'Unknown')
                    all_rounds = stream_result.get('all_rounds', [])

                    # Write subdomain header to md_tables.md
                    _write_discovery_subdomain_header(
                        storage_manager, email, session_id, conversation_id,
                        subdomain_name, subdomain_idx, is_first=(subdomain_idx == 1)
                    )

                    for round_data in all_rounds:
                        round_num = round_data.get('round', '?')
                        model = round_data.get('model', 'unknown')
                        context = round_data.get('context', 'unknown')
                        processing_time = round_data.get('processing_time', 0.0)

                        _add_api_call_to_runs(
                            session_id=session_id,
                            run_key=run_key,
                            api_response=round_data,
                            model=model,
                            processing_time=processing_time,
                            call_type='row_discovery',
                            status='IN_PROGRESS',
                            verbose_status=f'Row discovery: {subdomain_name} round {round_num}'
                        )

                        # Write round to md_tables.md
                        _write_discovery_round_section(
                            storage_manager, email, session_id, conversation_id,
                            subdomain_name, round_data
                        )

                # Save discovery results to S3
                _save_to_s3(
                    storage_manager, email, session_id, conversation_id,
                    'discovery_result.json', discovery_result
                )

                logger.info(f"[EXECUTION] Step 2 complete: {len(final_rows)} consolidated rows")
                logger.info(f"[EXECUTION] Config generation still running in background...")

                # Update template CSV with discovered candidate rows (all rows, not just first 15)
                try:
                    import csv
                    import io

                    csv_buffer = io.StringIO()

                    # Get ID columns and all column names
                    id_columns_list = [col['name'] for col in columns if col.get('importance', '').upper() == 'ID']
                    all_column_names = [col['name'] for col in columns]

                    writer = csv.DictWriter(csv_buffer, fieldnames=all_column_names)
                    writer.writeheader()

                    # Write all discovered rows with ID columns and research_values filled
                    for row in final_rows:
                        csv_row = {}
                        research_values = row.get('research_values', {})

                        for col_name in all_column_names:
                            if col_name in id_columns_list:
                                # Fill ID columns from id_values
                                csv_row[col_name] = row.get('id_values', {}).get(col_name, '')
                            elif col_name in research_values:
                                # Fill research columns if populated during discovery
                                csv_row[col_name] = research_values.get(col_name, '')
                            else:
                                # Leave other columns empty
                                csv_row[col_name] = ''

                        writer.writerow(csv_row)

                    csv_content = csv_buffer.getvalue()

                    # Update the template CSV in session folder (overwrite the header-only version)
                    csv_filename = f"{table_name.replace(' ', '_')}_template.csv"
                    session_path = storage_manager.get_session_path(email, session_id)
                    csv_s3_key = f"{session_path}{csv_filename}"

                    storage_manager.s3_client.put_object(
                        Bucket=storage_manager.bucket_name,
                        Key=csv_s3_key,
                        Body=csv_content,
                        ContentType='text/csv'
                    )
                    logger.info(
                        f"[EXECUTION] Updated template CSV with {len(final_rows)} discovered candidate rows: {csv_s3_key}"
                    )
                except Exception as e:
                    logger.error(f"[EXECUTION] Failed to update template CSV: {e}", exc_info=True)

                # Track original discovered count for later (before retrigger modifies final_rows)
                # Note: Discovered rows are now sent in real-time from row_discovery.py
                total_discovered_count = len(final_rows)
                original_discovered_count = total_discovered_count

                logger.info(
                    f"[DISCOVERY] Discovery complete: {total_discovered_count} rows found"
                )

            except Exception as e:
                result['error'] = f"Row discovery error: {str(e)}"
                logger.error(f"[EXECUTION] {result['error']}", exc_info=True)
                return result

        # ======================================================================
        # STEP 3: Consolidation (already done in row_discovery)
        # ======================================================================
        # Consolidation is built into row_discovery.discover_rows()
        # final_rows are already deduplicated, scored, and filtered

        # Skip Steps 3-4 if we already have approved rows from column definition
        if skip_to_csv_generation:
            logger.info("[EXECUTION] Steps 3-4 skipped (using rows from column definition as approved_rows)")
            # approved_rows was already set above in the skip path (line ~1163)
            # Set original_discovered_count if not already set
            if 'original_discovered_count' not in dir():
                original_discovered_count = len(approved_rows)

        # Only run QC if we didn't skip to CSV generation
        if not skip_to_csv_generation:
            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=3,
                total_steps=4,
                status=f'Step 3/4: Row discovery complete, starting QC review ({len(final_rows)} rows)',
                progress_percent=60
            )

            # ======================================================================
            # STEP 4: QC Review (starts immediately, doesn't wait for config)
            # ======================================================================
            logger.info("[EXECUTION] Step 4/4: QC Review (config still running in background)")

            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=4,
                total_steps=4,
                status=f'Finding and checking candidate rows... (reviewing {len(final_rows)} candidates)',
                progress_percent=75
            )

            # Initialize retry tracking for QC retriggers
            retry_count = 0
            max_retriggers = 1
            # TODO: Pass retrigger_allowed to QC reviewer when parameter is supported
            # This flag will be used to disable retrigger after first attempt (prevent loops)
            retrigger_allowed = True

            # QC Review Loop (supports up to 1 retrigger)
            while True:
                try:
                    # Get config for QC review
                    qc_config = config.get('qc_review', {})
                    qc_model = qc_config.get('model', 'claude-sonnet-4-5')
                    qc_max_tokens = qc_config.get('max_tokens', 16000)
                    min_qc_score = qc_config.get('min_qc_score', 0.5)
                    min_row_count = qc_config.get('min_row_count', 4)
                    min_row_count_for_frontend = qc_config.get('min_row_count_for_frontend', 4)

                    # Call QC reviewer
                    # IMPORTANT: Pass discovery_only_rows (not merged final_rows) to avoid
                    # duplicating prepopulated rows which are already shown in PREPOPULATED_ROWS_MARKDOWN
                    qc_result = await qc_reviewer.review_rows(
                        discovered_rows=discovery_only_rows,  # Only rows from discovery, not prepopulated
                        columns=columns,
                        user_context=conversation_state.get('user_request', ''),
                        table_name=table_name,
                        table_purpose=search_strategy.get('table_purpose', ''),
                        tablewide_research=conversation_state.get('tablewide_research', ''),
                        model=qc_model,
                        max_tokens=qc_max_tokens,
                        min_qc_score=min_qc_score,
                        max_rows=999,  # No artificial cutoff
                        min_row_count=min_row_count,
                        search_strategy=search_strategy,
                        discovery_result=discovery_result,
                        retrigger_allowed=retrigger_allowed,
                        column_result=column_result  # Pass column_definition result for prepopulated rows
                    )

                    if not qc_result.get('success'):
                        logger.warning(f"[EXECUTION] QC review failed: {qc_result.get('error')}")
                        # Use original rows if QC fails
                        approved_rows = final_rows
                        break
                    else:
                        # QC approved rows are from discovery only
                        # Combine prepopulated rows (initial_rows) with QC-approved discovered rows
                        qc_approved_discovered = qc_result.get('approved_rows', [])

                        if initial_rows:
                            # Merge: prepopulated rows + QC-approved discovered rows
                            approved_rows = _merge_rows_with_preference(
                                initial_rows=initial_rows,
                                discovered_rows=qc_approved_discovered,
                                id_column_names=[col['name'] for col in columns if col.get('importance') == 'ID']
                            )
                            logger.info(
                                f"[QC_MERGE] Combined {len(initial_rows)} prepopulated + "
                                f"{len(qc_approved_discovered)} QC-approved = {len(approved_rows)} total rows"
                            )
                        else:
                            approved_rows = qc_approved_discovered

                        # Track API call
                        _add_api_call_to_runs(
                            session_id=session_id,
                            run_key=run_key,
                            api_response=qc_result,
                            model=qc_model,
                            processing_time=qc_result.get('processing_time', 0.0),
                            call_type='qc_review',
                            status='IN_PROGRESS',
                            verbose_status=f'QC review complete: {len(approved_rows)} rows approved',
                            percent_complete=80
                        )

                        # Save to S3
                        _save_to_s3(
                            storage_manager, email, session_id, conversation_id,
                            'qc_result.json', qc_result
                        )

                    # ======================================================================
                    # Phase 1, Item 5: Check for insufficient rows
                    # ======================================================================
                    insufficient_rows_flag = qc_result.get('qc_summary', {}).get('insufficient_rows', False)
                    if insufficient_rows_flag and len(approved_rows) < min_row_count_for_frontend:
                        logger.warning(
                            f"[INSUFFICIENT_ROWS] Only {len(approved_rows)} approved rows (< {min_row_count_for_frontend}). "
                            "Frontend will show restart button with recommendations."
                        )

                        # Include insufficient rows info in result for WebSocket message
                        result['insufficient_rows'] = True
                        result['insufficient_rows_statement'] = qc_result.get('insufficient_rows_statement', '')
                        result['insufficient_rows_recommendations'] = qc_result.get('insufficient_rows_recommendations', [])

                        # If we have 0 total rows (including prepopulated), check QC's autonomous recovery decision
                        # Note: approved_rows now includes prepopulated rows merged with QC-approved discovery rows
                        if len(approved_rows) == 0:
                            logger.warning(
                                f"[ZERO_ROWS] No approved rows after {retry_count} retrigger(s). "
                                "Checking QC's autonomous recovery decision..."
                            )

                            # Save QC result to S3 for debugging
                            _save_to_s3(
                                storage_manager, email, session_id, conversation_id,
                                'qc_result.json', qc_result
                            )

                            # Get QC's autonomous decision
                            recovery_decision = qc_result.get('recovery_decision', {})
                            decision = recovery_decision.get('decision', 'give_up')  # Default to give_up if not provided
                            reasoning = recovery_decision.get('reasoning', '')

                            logger.info(f"[RECOVERY_DECISION] QC decided: {decision} - {reasoning}")

                            if decision == 'restructure':
                                # RECOVERABLE: AI will restructure and retry automatically
                                logger.info("[AUTONOMOUS_RESTRUCTURE] QC determined this is recoverable. Restructuring table...")

                                restructuring_guidance = recovery_decision.get('restructuring_guidance', {})
                                user_facing_message = recovery_decision.get('user_facing_message',
                                    'Restructuring the table with simpler columns and broader criteria. Retrying discovery...')

                                # IMPORTANT: Cancel config generation task if still running
                                # We're going back to Step 1, so config is no longer relevant
                                if config_generation_task and not config_generation_task.done():
                                    logger.info("[RESTRUCTURE] Canceling parallel config generation (no longer needed)")
                                    config_generation_task.cancel()
                                    try:
                                        await config_generation_task
                                    except asyncio.CancelledError:
                                        logger.info("[RESTRUCTURE] Config generation cancelled successfully")
                                    except Exception as e:
                                        logger.warning(f"[RESTRUCTURE] Error canceling config task: {e}")

                                # Get discovery context for transparency
                                discovery_result = result.get('discovery_result', {})
                                search_improvements = []
                                for stream in discovery_result.get('stream_results', []):
                                    improvements = stream.get('search_improvements', [])
                                    search_improvements.extend(improvements)

                                # Send frontend message to clear state and show restructure notice
                                send_execution_progress(
                                    session_id=session_id,
                                    conversation_id=conversation_id,
                                    current_step=0,  # Back to beginning
                                    total_steps=4,
                                    status='Restructuring table...',
                                    progress_percent=0,
                                    clear_previous_state=True,  # Tell frontend to clear displayed columns/rows
                                    restructure_notice=user_facing_message,
                                    autonomous_restructure=True,
                                    restructuring_guidance=restructuring_guidance,  # Full guidance for transparency
                                    search_improvements=search_improvements[:10],  # Top 10 improvements
                                    qc_reasoning=reasoning  # Why QC decided to restructure
                                )

                                # Update run status
                                if run_key:
                                    try:
                                        update_run_status(
                                            session_id=session_id,
                                            run_key=run_key,
                                            status='IN_PROGRESS',
                                            verbose_status='Restructuring table - restarting from column definition',
                                            percent_complete=0  # Back to start
                                        )
                                    except Exception as e:
                                        logger.warning(f"[EXECUTION] Failed to update run status: {e}")

                                # Set result to trigger restructure
                                result['success'] = False
                                result['restructure_needed'] = True
                                result['restructuring_guidance'] = restructuring_guidance
                                result['user_facing_message'] = user_facing_message
                                result['conversation_state'] = conversation_state  # Pass full state for context
                                result['original_user_request'] = conversation_state.get('interview_context', {}).get('user_goal', '')
                                result['row_count'] = 0
                                result['approved_rows'] = []

                                # Return early - conversation.py will restart from column definition
                                return result

                            else:
                                # UNRECOVERABLE: Give up and show apology
                                logger.error("[GIVE_UP] QC determined this request is fundamentally impossible")

                                fundamental_problem = recovery_decision.get('fundamental_problem',
                                    'This type of information is not discoverable via web searches.')
                                user_facing_apology = recovery_decision.get('user_facing_apology',
                                    'I apologize, but I wasn\'t able to find any rows for this table. ' +
                                    'This type of information isn\'t discoverable through web searches.')

                                # Send failure message with apology
                                send_execution_progress(
                                    session_id=session_id,
                                    conversation_id=conversation_id,
                                    current_step=4,
                                    total_steps=4,
                                    status='Unable to discover rows',
                                    progress_percent=100,
                                    execution_failed=True,
                                    fundamental_problem=fundamental_problem,
                                    user_facing_apology=user_facing_apology,
                                    show_new_table_card=True  # Signal frontend to show "Get Started" card
                                )

                                # Update run status to FAILED
                                if run_key:
                                    try:
                                        update_run_status(
                                            session_id=session_id,
                                            run_key=run_key,
                                            status='FAILED',
                                            verbose_status=f'Unrecoverable: {fundamental_problem[:100]}',
                                            percent_complete=100
                                        )
                                    except Exception as e:
                                        logger.warning(f"[EXECUTION] Failed to update run status: {e}")

                                # Set result as failed with apology
                                result['success'] = False
                                result['error'] = fundamental_problem
                                result['user_facing_apology'] = user_facing_apology
                                result['show_new_table_card'] = True
                                result['row_count'] = 0
                                result['approved_rows'] = []

                                # Return early - hard failure, frontend shows apology + new table card
                                return result

                    # ======================================================================
                    # Phase 2, Item 6: Check for QC retrigger request
                    # ======================================================================
                    retrigger_data = qc_result.get('retrigger_discovery', {})
                    should_retrigger = retrigger_data.get('should_retrigger', False)

                    # Check timeout before allowing retrigger
                    if should_retrigger and not timeout_guard.can_do_discovery_qc_cycle():
                        logger.warning(
                            f"[TIMEOUT] QC requested retrigger but insufficient time remaining. "
                            f"Remaining: {timeout_guard.remaining():.0f}s, needed: {MIN_TIME_FOR_DISCOVERY_QC}s. "
                            f"Skipping retrigger and using current results."
                        )
                        should_retrigger = False
                        # Send WebSocket update about timeout skip
                        send_execution_progress(
                            session_id=session_id,
                            conversation_id=conversation_id,
                            current_step=4,
                            total_steps=4,
                            status='Time constraints - completing with current results',
                            progress_percent=90
                        )

                    if should_retrigger and retry_count < max_retriggers:
                        retry_count += 1
                        retrigger_reason = retrigger_data.get('reason', 'No reason provided')

                        logger.info(f"[RETRIGGER] QC requested retrigger (attempt {retry_count}/{max_retriggers}): {retrigger_reason}")

                        # Send progress update about retrigger
                        send_execution_progress(
                            session_id=session_id,
                            conversation_id=conversation_id,
                            current_step=4,
                            total_steps=4,
                            status=f'QC requested additional discovery: {retrigger_reason}',
                            progress_percent=82
                        )

                        # Extract existing approved/demoted row IDs for exclusion
                        exclusion_list = []
                        for row in approved_rows:
                            id_values = row.get('id_values', {})
                            if id_values:
                                exclusion_list.append(id_values)

                        logger.info(f"[RETRIGGER] Created exclusion list with {len(exclusion_list)} existing rows")

                        # Update search_strategy with new subdomains
                        new_subdomains = retrigger_data.get('new_subdomains', [])
                        if new_subdomains:
                            logger.info(f"[RETRIGGER] Replacing {len(search_strategy.get('subdomains', []))} old subdomains with {len(new_subdomains)} new subdomains")
                            search_strategy['subdomains'] = new_subdomains

                        # Update requirements if provided
                        updated_requirements = retrigger_data.get('updated_requirements')
                        if updated_requirements:
                            logger.info(f"[RETRIGGER] Updating requirements: {len(updated_requirements)} requirements")
                            search_strategy['requirements'] = updated_requirements

                        # Update domain filters if provided
                        updated_default_domains = retrigger_data.get('updated_default_domains')
                        if updated_default_domains:
                            if 'included_domains' in updated_default_domains:
                                search_strategy['default_included_domains'] = updated_default_domains['included_domains']
                                logger.info(f"[RETRIGGER] Updated default_included_domains: {updated_default_domains['included_domains']}")
                            if 'excluded_domains' in updated_default_domains:
                                search_strategy['default_excluded_domains'] = updated_default_domains['excluded_domains']
                                logger.info(f"[RETRIGGER] Updated default_excluded_domains: {updated_default_domains['excluded_domains']}")

                        # Save updated column_definition_result
                        updated_column_result = {
                            'columns': columns,
                            'search_strategy': search_strategy,
                            'table_name': table_name
                        }
                        _save_to_s3(
                            storage_manager, email, session_id, conversation_id,
                            'column_definition_result_retrigger.json', updated_column_result
                        )

                        # Re-run row discovery with updated strategy and exclusion list
                        logger.info("[RETRIGGER] Re-running row discovery with updated strategy")
                        send_execution_progress(
                            session_id=session_id,
                            conversation_id=conversation_id,
                            current_step=4,
                            total_steps=4,
                            status='Re-discovering rows with updated search strategy...',
                            progress_percent=85
                        )

                        # Calculate dynamic max_parallel_streams for retrigger
                        num_subdomains = len(search_strategy.get('subdomains', []))
                        max_parallel_streams_retrigger = min(num_subdomains, 5)

                        # TODO: Pass exclusion_list when row_discovery.py is updated to support it
                        # For now, the new subdomains and updated requirements will help avoid duplicates
                        retrigger_discovery_result = await row_discovery.discover_rows(
                            search_strategy=search_strategy,
                            columns=columns,
                            target_row_count=conversation_state.get('target_row_count', 15),
                            discovery_multiplier=1.5,
                            min_match_score=min_match_score,
                            max_parallel_streams=max_parallel_streams_retrigger,
                            escalation_strategy=escalation_strategy,
                            check_targets_between_subdomains=check_targets_between_subdomains,
                            early_stop_threshold_percentage=early_stop_threshold_percentage,
                            # exclusion_list=exclusion_list,  # TODO: Add when parameter is supported
                            websocket_callback=websocket_callback,
                            soft_schema=soft_schema
                        )

                        if not retrigger_discovery_result.get('success'):
                            logger.error(f"[RETRIGGER] Re-discovery failed: {retrigger_discovery_result.get('error')}")
                            # Keep original rows and break
                            break

                        new_rows = retrigger_discovery_result.get('final_rows', [])
                        logger.info(f"[RETRIGGER] Re-discovery found {len(new_rows)} new rows")

                        # Track retrigger discovery API calls
                        retrigger_stream_results = retrigger_discovery_result.get('stream_results', [])
                        for stream_result in retrigger_stream_results:
                            subdomain_name = stream_result.get('subdomain', 'Unknown')
                            all_rounds = stream_result.get('all_rounds', [])

                            for round_data in all_rounds:
                                round_num = round_data.get('round', '?')
                                model = round_data.get('model', 'unknown')
                                processing_time = round_data.get('processing_time', 0.0)

                                _add_api_call_to_runs(
                                    session_id=session_id,
                                    run_key=run_key,
                                    api_response=round_data,
                                    model=model,
                                    processing_time=processing_time,
                                    call_type='row_discovery_retrigger',
                                    status='IN_PROGRESS',
                                    verbose_status=f'Retrigger discovery: {subdomain_name} round {round_num}'
                                )

                        # Merge new rows with existing approved rows (deduplicate by ID values)
                        # IMPORTANT: Reset final_rows to only contain approved rows from first QC
                        # Second QC will see:
                        #   (1) Approved rows from QC1 (with their qc_score from QC1)
                        #   (2) New rows from retrigger (with their match_score from discovery)
                        # Second QC doesn't know about QC1 - it just evaluates all rows it sees
                        final_rows = list(approved_rows)  # Start fresh with only approved rows

                        existing_ids = set()
                        for row in approved_rows:
                            id_values = row.get('id_values', {})
                            if id_values:
                                # Create a hashable key from ID values
                                id_key = tuple(sorted(id_values.items()))
                                existing_ids.add(id_key)

                        # Add new rows that don't duplicate existing approved rows
                        merged_count = 0
                        for new_row in new_rows:
                            id_values = new_row.get('id_values', {})
                            if id_values:
                                id_key = tuple(sorted(id_values.items()))
                                if id_key not in existing_ids:
                                    final_rows.append(new_row)
                                    merged_count += 1
                                    existing_ids.add(id_key)

                        logger.info(f"[RETRIGGER] Merged {merged_count} new unique rows with {len(approved_rows)} approved rows, total now: {len(final_rows)}")

                        # Update discovery_only_rows for second QC
                        # For retrigger, QC2 should re-evaluate ALL non-prepopulated rows:
                        # - Previously approved rows from QC1 (excluding prepopulated)
                        # - New rows from retrigger discovery
                        # The prepopulated rows are already in column_result and shown separately
                        if initial_rows:
                            # Filter out prepopulated rows from final_rows for QC2
                            initial_ids = set()
                            for row in initial_rows:
                                id_values = row.get('id_values', {})
                                if id_values:
                                    initial_ids.add(tuple(sorted(id_values.items())))

                            discovery_only_rows = [
                                row for row in final_rows
                                if tuple(sorted(row.get('id_values', {}).items())) not in initial_ids
                            ]
                            logger.info(f"[RETRIGGER] Second QC will review {len(discovery_only_rows)} rows (excluding {len(initial_rows)} prepopulated)")
                        else:
                            discovery_only_rows = final_rows

                        # Update original_discovered_count to include retrigger rows
                        # This ensures the frontend sees the total cumulative count, not a shrinking number
                        original_discovered_count = original_discovered_count + merged_count
                        logger.info(f"[RETRIGGER] Updated original_discovered_count to {original_discovered_count} (includes retrigger rows)")

                        # Save merged discovery results
                        merged_discovery_result = {
                            'success': True,
                            'final_rows': final_rows,
                            'original_discovery': discovery_result,
                            'retrigger_discovery': retrigger_discovery_result,
                            'retrigger_count': retry_count
                        }
                        _save_to_s3(
                            storage_manager, email, session_id, conversation_id,
                            'discovery_result_merged.json', merged_discovery_result
                        )

                        # Update discovery_result to merged result for next QC iteration
                        discovery_result = merged_discovery_result

                        # Disable retrigger for next QC iteration
                        retrigger_allowed = False

                        # Continue to re-run QC with merged results
                        logger.info("[RETRIGGER] Re-running QC with merged results (retrigger disabled)")
                        continue

                    else:
                        # No retrigger or max retriggers reached
                        if should_retrigger and retry_count >= max_retriggers:
                            logger.warning(f"[RETRIGGER] QC requested retrigger but max_retriggers ({max_retriggers}) reached")

                        # Break out of QC loop
                        break

                except Exception as e:
                    logger.error(f"[EXECUTION] QC review error: {e}", exc_info=True)
                    # Continue with discovered rows if QC fails
                    approved_rows = final_rows
                    break

        # Store final approved rows (second QC has full authority)
        result['approved_rows'] = approved_rows
        result['row_count'] = len(approved_rows)

        # Pass QC warning to frontend if present (check qc_result exists first)
        if 'qc_result' in locals() and qc_result.get('warning'):
            result['qc_warning'] = qc_result['warning']
            warning = qc_result['warning']
            logger.warning(f"[EXECUTION] QC warning present: {warning['type']}")

            # Send warning via WebSocket for immediate display
            send_warning(
                session_id=session_id,
                conversation_id=conversation_id,
                warning_type=warning['type'],
                title=warning['title'],
                message=warning['message'],
                rows_included=warning.get('rows_included'),
                reason=warning.get('reason')
            )

        # Pass qc_bypassed flag to frontend if present
        if 'qc_result' in locals() and qc_result.get('qc_bypassed'):
            result['qc_bypassed'] = True
            logger.info("[EXECUTION] QC was bypassed - rows sorted by discovery score only")

        logger.info(f"[EXECUTION] Step 4 complete: {len(approved_rows)} approved rows (after {retry_count} retrigger(s))")

        # ======================================================================
        # Write QC section to md_tables.md (incremental update)
        # ======================================================================
        try:
            qc_res = qc_result if 'qc_result' in locals() else {}
            _write_qc_section(
                storage_manager, email, session_id, conversation_id,
                qc_res, approved_rows, columns
            )
            logger.info("[MD_TABLES] Wrote QC section to md_tables.md")

        except Exception as md_err:
            logger.warning(f"[MD_TABLES] Failed to write QC section: {md_err}")

        # Build progress message based on what's still running
        # At this point, QC is done but config might still be running
        progress_message_parts = []
        if result.get('insufficient_rows'):
            progress_message_parts.append(f"Only {len(approved_rows)} rows found")
        else:
            # Config is still running in background - indicate we're waiting for it
            progress_message_parts.append('Wrapping up validation configuration...')

        progress_message = ' | '.join(progress_message_parts) if progress_message_parts else 'Wrapping up validation configuration...'

        # Prepare approved rows preview for frontend (first 15 rows with id_values only)
        # This updates Info Box 3 from "Discovered Rows" to "Approved Rows" after QC
        # Note: QC sets 'row_score', but fallback to 'match_score' if QC was bypassed
        approved_rows_preview = [
            {
                "id_values": row.get("id_values", {}),
                "row_score": round(row.get("row_score", row.get("match_score", 0)), 2)  # Round to 2 decimal places
            }
            for row in approved_rows[:15]  # First 15 approved rows only
        ]

        # Extract QC summary for frontend display
        qc_summary = qc_result.get('qc_summary', {}) if qc_result else {}

        # For retrigger cases, simplify QC summary to avoid confusion
        # (promoted/demoted counts are messy when rows go through 2 QC rounds)
        if retry_count > 0:
            total_reviewed = qc_result.get('total_reviewed', len(approved_rows) + qc_summary.get('rejected', 0))
            rejected = qc_summary.get('rejected', 0)
            qc_summary = {
                'total_reviewed': total_reviewed,
                'approved': len(approved_rows),
                'rejected': rejected,
                'rejection_rate': round(rejected / total_reviewed, 2) if total_reviewed > 0 else 0,
                'rounds': 2,  # Indicate 2 rounds of search and QC were performed
                'note': '2 rounds of search and QC'
            }
            logger.info(f"[QC] Retrigger QC summary simplified: {len(approved_rows)} approved, {rejected} rejected from {total_reviewed} total (2 rounds)")

        logger.info(
            f"[DEBUG] Sending WebSocket with approved_rows: "
            f"count={len(approved_rows_preview)}, total_approved={len(approved_rows)}, "
            f"has_qc_summary={bool(qc_summary)}"
        )

        # Send progress update with approved_rows data (top 15 for display)
        # FRONTEND IMPLEMENTATION NOTE (Info Box 3 - Updated after QC):
        # Update the "Discovered Rows" box to "Approved Rows" after QC completes
        # - Header: "Approved Rows: X of Y discovered" (green button color)
        # - Show first 10-15 approved rows with ID values only
        # - Display format: "{ID Column 1}: {value}, {ID Column 2}: {value}, ..."
        # - Show "+Z more rows" if total_approved > 15
        # - Include QC summary stats if available:
        #   * Single QC: Promoted/demoted/rejected counts
        #   * Retrigger (2 rounds): Simplified to show rejection_rate and note '2 rounds of search and QC'
        # - QC summary display: "QC Review: +X promoted, -Y rejected" (single) or "Y% rejected (2 rounds)" (retrigger)

        # Build kwargs for additional fields
        additional_fields = {
            'approved_rows': approved_rows_preview,  # First 15 rows for display
            'total_approved': len(approved_rows),
            'total_discovered': original_discovered_count,  # Use tracked count (includes retrigger rows, doesn't shrink)
            'qc_summary': qc_summary  # QC summary with promoted/demoted/rejected counts
        }

        # Add insufficient rows info if applicable
        if result.get('insufficient_rows'):
            additional_fields['insufficient_rows'] = True
            additional_fields['insufficient_rows_statement'] = result.get('insufficient_rows_statement', '')
            additional_fields['insufficient_rows_recommendations'] = result.get('insufficient_rows_recommendations', [])

        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=4,
            total_steps=4,
            status=progress_message,
            progress_percent=80,
            **additional_fields
        )

        # ======================================================================
        # MUTUAL COMPLETION: Wait for Config Generation
        # ======================================================================
        # Start config generation if we skipped row discovery (it wasn't started earlier)
        if skip_to_csv_generation:
            logger.info("[EXECUTION] Starting config generation (was skipped during row discovery phase)")
            config_generation_task = asyncio.create_task(
                _generate_validation_config(
                    email=email,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    conversation_state=conversation_state,
                    columns=columns,
                    table_name=table_name
                )
            )

        logger.info("[EXECUTION] Waiting for config generation to complete...")

        # DO NOT send WebSocket update here - config is silent in background
        # Sending a message here causes progress indicator to disappear/flicker

        # Wait for config generation to finish
        if config_generation_task:
            try:
                config_result = await config_generation_task

                if isinstance(config_result, Exception):
                    logger.warning(f"[EXECUTION] Config generation failed with exception: {config_result}")
                    result['config_generated'] = False
                elif config_result.get('success'):
                    logger.info(f"[EXECUTION] Config generation succeeded: {config_result.get('config_s3_key')}")
                    result['config_generated'] = True
                    result['config_s3_key'] = config_result.get('config_s3_key')
                    result['config_version'] = config_result.get('config_version')
                else:
                    logger.warning(f"[EXECUTION] Config generation failed: {config_result.get('error')}")
                    result['config_generated'] = False
            except Exception as e:
                logger.error(f"[EXECUTION] Error waiting for config generation: {e}", exc_info=True)
                result['config_generated'] = False
        else:
            logger.warning("[EXECUTION] Config generation task was not created")
            result['config_generated'] = False

        # ======================================================================
        # GENERATE EXCEL with sources embedded as comments (PRIMARY)
        # ======================================================================
        logger.info("[EXECUTION] Generating Excel file with source URLs embedded as comments...")

        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=4,
            total_steps=4,
            status='Generating Excel file with sources...',
            progress_percent=90
        )

        excel_success = False
        try:
            import xlsxwriter
            import tempfile

            # Get ID columns and all column names
            id_columns = [col['name'] for col in columns if col.get('importance', '').upper() == 'ID']
            all_column_names = [col['name'] for col in columns]

            # Get citations dictionary from conversation_state
            citations = conversation_state.get('citations', {})
            logger.info(f"[EXECUTION] Found {len(citations)} citations for Excel generation")

            # Create temporary Excel file
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.xlsx', delete=False) as tmp_file:
                excel_temp_path = tmp_file.name

            # Create workbook and worksheet
            workbook = xlsxwriter.Workbook(excel_temp_path)
            worksheet = workbook.add_worksheet('Data')

            # Write headers
            for col_idx, col_name in enumerate(all_column_names):
                worksheet.write(0, col_idx, col_name)

            # Write data rows with source URLs as comments on cells that have citations
            from urllib.parse import urlparse
            sources_added = 0

            for row_idx, row in enumerate(approved_rows, start=1):
                id_values = row.get('id_values', {})
                research_values = row.get('research_values', {})
                cell_citations = row.get('cell_citations', {})  # Per-cell citation URLs

                for col_idx, col_name in enumerate(all_column_names):
                    # Get cell value (already clean, citations were stripped during parsing)
                    if col_name in id_columns:
                        cell_value = id_values.get(col_name, '')
                    elif col_name in research_values:
                        cell_value = research_values.get(col_name, '')
                    else:
                        cell_value = ''

                    # Write cell value
                    worksheet.write(row_idx, col_idx, cell_value)

                    # Add sources as comment if this cell has citations
                    cell_source_urls = cell_citations.get(col_name, [])
                    if cell_source_urls:
                        # Format sources to match parser expectations (shared_table_parser.py)
                        # Expected format:
                        #   Sources:
                        #   [1] Source Title (URL)
                        comment_lines = ["Sources:"]
                        for i, url in enumerate(cell_source_urls, 1):
                            # Extract domain as title
                            try:
                                domain = urlparse(url).netloc or url
                                # Format: [#] Domain (URL) - parser expects URL in parentheses
                                comment_lines.append(f"[{i}] {domain} ({url})")
                            except Exception:
                                # Fallback: just use URL
                                comment_lines.append(f"[{i}] Source ({url})")

                        comment_text = '\n'.join(comment_lines)

                        try:
                            worksheet.write_comment(
                                row_idx, col_idx, comment_text,
                                {'width': 300, 'height': 150}
                            )
                            sources_added += 1
                        except Exception as e_comment:
                            logger.warning(f"[EXECUTION] Failed to add comment to row {row_idx}, col {col_idx}: {e_comment}")

            # Close workbook
            workbook.close()

            # Read Excel file and upload to S3
            with open(excel_temp_path, 'rb') as f:
                excel_content = f.read()

            # Remove '_template' or 'template' from filename for validation compatibility
            # Clean table name: replace spaces with underscores, remove template suffix
            clean_table_name = table_name.replace(' ', '_')
            # Don't add '_template' suffix - validation expects clean names
            excel_filename = f"{clean_table_name}.xlsx"

            # Store in session folder (not in table_maker subfolder) for validation to find
            session_path = storage_manager.get_session_path(email, session_id)
            excel_s3_key = f"{session_path}{excel_filename}"

            storage_manager.s3_client.put_object(
                Bucket=storage_manager.bucket_name,
                Key=excel_s3_key,
                Body=excel_content,
                ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

            result['excel_s3_key'] = excel_s3_key
            result['excel_filename'] = excel_filename

            # Clean up temp file
            import os
            os.unlink(excel_temp_path)

            logger.info(
                f"[EXECUTION] Excel generated with {len(approved_rows)} rows, "
                f"{sources_added} cells have source comments (citations embedded per-cell)"
            )

            # Update session_info.json with Excel path
            try:
                session_info = storage_manager.load_session_info(email, session_id)
                session_info['table_path'] = excel_s3_key  # Use Excel with sources
                session_info['table_name'] = table_name
                session_info['last_updated'] = datetime.now().isoformat()
                storage_manager.save_session_info(email, session_id, session_info)
                logger.info(f"[EXECUTION] Updated session_info.json with Excel table_path: {excel_s3_key}")
            except Exception as e_session:
                logger.warning(f"[EXECUTION] Failed to update session_info with table_path: {e_session}")

            # Mark Excel generation as successful
            excel_success = True
            logger.info("[EXECUTION] Excel generation successful - skipping CSV generation")

        except Exception as e_excel:
            logger.error(f"[EXECUTION] Failed to generate Excel: {e_excel}", exc_info=True)
            result['excel_generation_error'] = str(e_excel)
            excel_success = False

        # ======================================================================
        # GENERATE CSV (FALLBACK - only if Excel failed)
        # ======================================================================
        if not excel_success:
            logger.info("[EXECUTION] Excel generation failed - creating CSV fallback...")
            try:
                import csv
                import io

                csv_buffer = io.StringIO()

                # Get ID columns and all column names (may not be defined if Excel failed early)
                if 'id_columns' not in locals():
                    id_columns = [col['name'] for col in columns if col.get('importance', '').upper() == 'ID']
                if 'all_column_names' not in locals():
                    all_column_names = [col['name'] for col in columns]

                writer = csv.DictWriter(csv_buffer, fieldnames=all_column_names)
                writer.writeheader()

                # Write rows with ID columns and research columns (if available) filled
                populated_research_count = 0
                total_research_cells = 0

                for row in approved_rows:
                    csv_row = {}
                    research_values = row.get('research_values', {})

                    for col_name in all_column_names:
                        if col_name in id_columns:
                            # Fill ID columns from id_values
                            csv_row[col_name] = row.get('id_values', {}).get(col_name, '')
                        elif col_name in research_values:
                            # Fill research columns if populated during discovery
                            csv_row[col_name] = research_values.get(col_name, '')
                            populated_research_count += 1
                        else:
                            # Leave other columns empty
                            csv_row[col_name] = ''

                        # Track total research cells for logging
                        if col_name not in id_columns:
                            total_research_cells += 1

                    writer.writerow(csv_row)

                csv_content = csv_buffer.getvalue()

                # Save CSV to S3
                csv_filename = f"{table_name.replace(' ', '_')}.csv"  # No _template suffix
                session_path = storage_manager.get_session_path(email, session_id)
                csv_s3_key = f"{session_path}{csv_filename}"

                storage_manager.s3_client.put_object(
                    Bucket=storage_manager.bucket_name,
                    Key=csv_s3_key,
                    Body=csv_content,
                    ContentType='text/csv'
                )

                result['csv_s3_key'] = csv_s3_key
                result['csv_filename'] = csv_filename

                # Calculate population statistics
                research_columns_count = len(all_column_names) - len(id_columns)
                population_pct = (populated_research_count / total_research_cells * 100) if total_research_cells > 0 else 0

                logger.info(
                    f"[EXECUTION] CSV fallback generated with {len(approved_rows)} rows: "
                    f"{len(id_columns)} ID columns filled, "
                    f"{populated_research_count}/{total_research_cells} research cells populated ({population_pct:.1f}%)"
                )

                # Update session_info.json with CSV path as fallback
                try:
                    session_info = storage_manager.load_session_info(email, session_id)
                    session_info['table_path'] = csv_s3_key
                    session_info['table_name'] = table_name
                    session_info['last_updated'] = datetime.now().isoformat()
                    storage_manager.save_session_info(email, session_id, session_info)
                    logger.info(f"[EXECUTION] Updated session_info.json with CSV fallback path: {csv_s3_key}")
                except Exception as e_session:
                    logger.warning(f"[EXECUTION] Failed to update session_info with CSV path: {e_session}")

            except Exception as e_csv:
                logger.error(f"[EXECUTION] Failed to generate CSV fallback: {e_csv}", exc_info=True)
                result['csv_generation_error'] = str(e_csv)
        else:
            logger.info("[EXECUTION] Skipped CSV generation - Excel succeeded")

        # ======================================================================
        # COMPLETE
        # ======================================================================

        # Update conversation state with approved rows
        conversation_state['approved_rows'] = approved_rows
        conversation_state['columns'] = columns
        conversation_state['table_name'] = table_name

        # Store file paths (Excel if successful, otherwise CSV fallback)
        if excel_success and result.get('excel_s3_key'):
            conversation_state['excel_s3_key'] = result.get('excel_s3_key')
            conversation_state['primary_file'] = 'excel'
        elif result.get('csv_s3_key'):
            conversation_state['csv_s3_key'] = result.get('csv_s3_key')
            conversation_state['primary_file'] = 'csv'

        _save_to_s3(
            storage_manager, email, session_id, conversation_id,
            'conversation_state.json', conversation_state
        )

        # Send final progress
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=4,
            total_steps=4,
            status='Table ready for validation!',
            progress_percent=100
        )

        # Update runs database
        if run_key:
            try:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='COMPLETE',
                    verbose_status=f'Completed: {len(approved_rows)} rows, CSV generated',
                    percent_complete=100
                )
            except Exception as e:
                logger.warning(f"[EXECUTION] Failed to update run status: {e}")

        result['success'] = True
        logger.info(f"[EXECUTION] Pipeline complete: {len(approved_rows)} rows")

        # Flush memory cache to S3 at batch end (single write for all stored tables)
        if SEARCH_MEMORY_AVAILABLE:
            try:
                if MemoryCache.is_dirty(session_id):
                    await MemoryCache.flush(session_id)
                    logger.info("[EXECUTION] Memory cache flushed to S3")
            except Exception as mem_error:
                logger.warning(f"[EXECUTION] Failed to flush memory cache (non-fatal): {mem_error}")

        return result

    except Exception as e:
        result['error'] = f"Execution pipeline error: {str(e)}"
        logger.error(f"[EXECUTION] {result['error']}", exc_info=True)

        # Try to flush memory even on error
        if SEARCH_MEMORY_AVAILABLE:
            try:
                if MemoryCache.is_dirty(session_id):
                    await MemoryCache.flush(session_id)
            except:
                pass  # Silently ignore flush errors on exception path

        return result
