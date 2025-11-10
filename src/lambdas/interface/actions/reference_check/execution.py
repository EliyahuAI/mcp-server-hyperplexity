"""
Reference Check Execution Handler for Lambda.

This module orchestrates the 3-step reference check pipeline:
0. Extract claims from submitted text using SONNET 4.5
1. Validate each claim (reference check or fact-check)
2. Compile results into CSV

WEBSOCKET MESSAGES FOR FRONTEND:
================================
Step 0 (Extraction):
{
    "type": "reference_check_progress",
    "conversation_id": str,
    "current_step": 0,
    "total_steps": 2,
    "status": "Extracting claims and references. This takes a minute...",
    "progress_percent": 50,
    "progress": 50,
    "phase": "extraction"
}

Step 1 (Validation):
{
    "type": "reference_check_progress",
    "conversation_id": str,
    "current_step": 1,
    "total_steps": 2,
    "status": "Validating claim X of Y...",
    "progress_percent": 30,
    "phase": "validation",
    "claims_validated": X,
    "total_claims": Y
}

Step 2 (Compilation):
{
    "type": "reference_check_progress",
    "conversation_id": str,
    "current_step": 2,
    "total_steps": 2,
    "status": "Compiling results...",
    "progress_percent": 90,
    "phase": "compilation"
}

Complete:
{
    "type": "reference_check_complete",
    "conversation_id": str,
    "status": "complete",
    "csv_s3_key": str,
    "csv_filename": str,
    "summary": {
        "total_claims": int,
        "strongly_supported": int,
        "supported": int,
        "partially_supported": int,
        "unclear": int,
        "contradicted": int,
        "inaccessible": int
    }
}
"""

import logging
import json
import asyncio
import csv
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

# Lambda infrastructure imports
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from dynamodb_schemas import update_run_status

# AI API client
from ai_api_client import AIAPIClient

# Import conversation helpers
from .conversation import _load_conversation_state, _save_conversation_state

# Import AI logic modules
from .reference_check_lib.claim_extractor import extract_claims
from .reference_check_lib.reference_validator import validate_claim
from .reference_check_lib.result_compiler import compile_results_to_csv, get_summary_stats
from .reference_check_lib.reference_parser import parse_and_resolve_references

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _format_text_location(text_location: Optional[Dict[str, Any]]) -> str:
    """
    Format text location data into human-readable pipe-delimited string.

    Args:
        text_location: Dict with keys like start_char, end_char, paragraph_index,
                      section_name, sentence_index, word_start, word_end

    Returns:
        Formatted string like "Section: Introduction | Para: 2 | Sentence: 3 | Words: 45-67 | Chars: 234-456"
        or "Para: 2 | Sentence: 3 | Words: 45-67 | Chars: 234-456" if no section
    """
    if not text_location:
        return ''

    parts = []

    # Add section if available
    if text_location.get('section_name'):
        parts.append(f"Section: {text_location['section_name']}")

    # Add paragraph index (convert from 0-indexed to 1-indexed for readability)
    if 'paragraph_index' in text_location:
        para_num = text_location['paragraph_index'] + 1
        parts.append(f"Para: {para_num}")

    # Add sentence index if available
    if 'sentence_index' in text_location:
        sent_num = text_location['sentence_index'] + 1
        parts.append(f"Sentence: {sent_num}")

    # Add word range if available
    if 'word_start' in text_location and 'word_end' in text_location:
        parts.append(f"Words: {text_location['word_start']}-{text_location['word_end']}")

    # Add character range (always include if start_char and end_char exist)
    if 'start_char' in text_location and 'end_char' in text_location:
        parts.append(f"Chars: {text_location['start_char']}-{text_location['end_char']}")

    return ' | '.join(parts)


def _expand_reference_to_full_format(citation_text: str, reference_map: Dict[str, str]) -> str:
    """
    Expand numbered citations to full format: "[1] Full Citation, [2] Full Citation"

    Args:
        citation_text: Text with citations like "[1]", "[2][3]", or "[1,2,3]"
        reference_map: Dict mapping ref_id to full citation

    Returns:
        Comma-separated full references with brackets
        Example: "[1][2]" -> "[1] Smith et al. (2023). Title..., [2] Johnson (2024). Title..."
    """
    if not citation_text or not reference_map:
        return citation_text

    # Find all citation numbers in the text
    # Matches: [1], [2], [3] or [1,2,3] or [1][2][3]
    citation_pattern = r'\[(\d+(?:,\s*\d+)*)\]|\[(\d+)\]'
    matches = re.findall(citation_pattern, citation_text)

    # Extract all unique numbers
    ref_nums = set()
    for match in matches:
        # match is a tuple: (comma_separated, single)
        if match[0]:  # Comma-separated: [1,2,3]
            nums = re.findall(r'\d+', match[0])
            ref_nums.update(nums)
        elif match[1]:  # Single: [1]
            ref_nums.add(match[1])

    # Build full citation list
    full_citations = []
    for num in sorted(ref_nums, key=int):
        ref_id = f"[{num}]"
        if ref_id in reference_map:
            full_citation = reference_map[ref_id]
            # Format as "[1] Full Citation"
            formatted = f"{ref_id} {full_citation}"
            full_citations.append(formatted)
            logger.info(f"[COMPILATION] Expanded {ref_id} to full citation")
        else:
            # Keep original if not found
            full_citations.append(ref_id)
            logger.warning(f"[COMPILATION] Could not expand {ref_id}, keeping as-is")

    # Join with comma-space for inline display
    return ', '.join(full_citations) if full_citations else citation_text


def _get_websocket_client():
    """Get WebSocket client instance, handling errors gracefully."""
    try:
        from websocket_client import WebSocketClient
        return WebSocketClient()
    except Exception as e:
        logger.warning(f"WebSocket client not available: {e}")
        return None


def send_execution_progress(
    session_id: str,
    conversation_id: str,
    current_step: int,
    total_steps: int,
    status: str,
    progress_percent: int,
    phase: str,
    **kwargs
) -> None:
    """
    Send execution progress update via WebSocket.

    Args:
        session_id: Session identifier
        conversation_id: Conversation identifier
        current_step: Current step number (0-2)
        total_steps: Total number of steps (2)
        status: Human-readable status message
        progress_percent: Progress percentage (0-100)
        phase: Current phase (extraction, validation, compilation)
        **kwargs: Additional fields to include in message
    """
    ws_client = _get_websocket_client()
    if not ws_client or not session_id:
        return

    try:
        message = {
            'type': 'reference_check_progress',
            'conversation_id': conversation_id,
            'current_step': current_step,
            'total_steps': total_steps,
            'status': status,
            'progress_percent': progress_percent,
            'progress': progress_percent,  # Frontend expects 'progress' field
            'phase': phase,
            **kwargs
        }

        ws_client.send_to_session(session_id, message)
        logger.info(
            f"[EXECUTION] Progress {progress_percent}% (Step {current_step}/{total_steps}, {phase}): {status}"
        )
    except Exception as e:
        logger.warning(f"[EXECUTION] Failed to send WebSocket update: {e}")


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

    This uses the SAME pattern as table_maker/execution.py to ensure consistent metrics tracking.

    Args:
        session_id: Session identifier
        run_key: Run tracking key
        api_response: API response dict from handler with structure:
            {'enhanced_data': {...}, 'model_used': str, 'processing_time': float, ...}
        model: Model name used
        processing_time: Processing time in seconds
        call_type: Type of call (e.g., 'claim_extraction', 'reference_validation')
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

        # Step 2: Extract existing call_metrics_list and models list
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
        if 'enhanced_data' in api_response and api_response['enhanced_data']:
            new_call_metrics = api_response['enhanced_data']
            logger.debug(f"[EXECUTION] Using pre-computed enhanced_data from API response")
        else:
            # Fallback: regenerate enhanced metrics if not present
            logger.warning(f"[EXECUTION] enhanced_data not found in api_response, regenerating...")
            new_call_metrics = AIAPIClient().get_enhanced_call_metrics(
                response=api_response.get('response', api_response),
                model=model,
                processing_time=processing_time,
                pre_extracted_token_usage=api_response.get('token_usage'),
                is_cached=api_response.get('is_cached', False)
            )

        # Tag with call type for tracking
        new_call_metrics['call_type'] = call_type
        existing_call_metrics.append(new_call_metrics)

        # Extract max_web_searches from enhanced data (for validation calls)
        max_web_searches_value = new_call_metrics.get('call_info', {}).get('max_web_searches', 0)

        # Build model entry
        model_entry = {
            'model': model,
            'call_type': call_type,
            'max_web_searches': max_web_searches_value,
            'is_cached': api_response.get('is_cached', False)
        }
        existing_models_list.append(model_entry)

        logger.info(f"[EXECUTION] Added new {call_type} call metrics for {model}, total calls: {len(existing_call_metrics)}")

        # Step 4: Re-aggregate ALL calls
        aggregated = AIAPIClient.aggregate_provider_metrics(existing_call_metrics)
        providers = aggregated.get('providers', {})
        totals = aggregated.get('totals', {})

        # Step 5: WRITE back to database with aggregated metrics
        total_actual_cost = totals.get('total_cost_actual', 0.0)
        total_estimated_cost = totals.get('total_cost_estimated', 0.0)
        total_actual_time = totals.get('total_actual_processing_time', 0.0)
        total_calls = totals.get('total_calls', 0)

        # Build run_type with operation details
        call_type_names = {
            'claim_extraction': 'Claim Extraction',
            'reference_validation': 'Reference Validation',
            'fact_check': 'Fact Check'
        }
        operation_sequence = ', '.join([call_type_names.get(c.get('call_type'), c.get('call_type', 'Unknown'))
                                       for c in existing_call_metrics])
        run_type = f"Reference Check ({operation_sequence})" if operation_sequence else "Reference Check"

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
            'call_metrics_list': existing_call_metrics,
            'enhanced_metrics_aggregated': aggregated,
            'reference_check_breakdown': {
                'claim_extraction_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'claim_extraction']),
                'reference_validation_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'reference_validation']),
                'fact_check_calls': len([c for c in existing_call_metrics if c.get('call_type') == 'fact_check']),
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


def _save_to_s3(
    storage_manager: UnifiedS3Manager,
    email: str,
    session_id: str,
    conversation_id: str,
    file_name: str,
    data: Any,
    content_type: str = 'application/json'
) -> str:
    """
    Save data to S3.

    Args:
        storage_manager: S3 manager instance
        email: User email
        session_id: Session ID
        conversation_id: Conversation ID
        file_name: File name to save
        data: Data to save (will be JSON encoded if dict)
        content_type: Content type for S3 object

    Returns:
        S3 key of saved file
    """
    try:
        s3_key = f"reference_checks/{email}/{session_id}/{conversation_id}/{file_name}"

        # Encode data based on content type
        if content_type == 'application/json':
            body = json.dumps(data, indent=2)
        else:
            body = data

        storage_manager.s3_client.put_object(
            Bucket=storage_manager.bucket_name,
            Key=s3_key,
            Body=body,
            ContentType=content_type
        )

        logger.info(f"[EXECUTION] Saved to S3: {s3_key}")
        return s3_key

    except Exception as e:
        logger.error(f"[EXECUTION] Failed to save to S3: {e}")
        raise


def _load_config() -> Dict:
    """Load reference_check_config.json."""
    try:
        config_path = Path(__file__).parent / 'reference_check_config.json'
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[EXECUTION] Failed to load config: {e}")
        return {}


async def _extract_claims(
    submitted_text: str,
    conversation_id: str,
    session_id: str,
    config: Dict
) -> Dict[str, Any]:
    """
    Extract claims from submitted text using SONNET 4.5.

    Args:
        submitted_text: The text to analyze
        conversation_id: Conversation identifier
        session_id: Session identifier
        config: Configuration dict

    Returns:
        {
            'success': bool,
            'claims': List[Dict],  # List of extracted claims
            'processing_time': float,
            'model_used': str,
            'enhanced_data': Dict,  # API metrics
            'error': str (if failed)
        }
    """
    try:
        logger.info(f"[EXTRACTION] Starting claim extraction for {conversation_id}")

        # Send progress update
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=0,
            total_steps=2,
            status='Extracting claims and references. This takes a minute...',
            progress_percent=50,
            phase='extraction'
        )

        # Call claim extraction module
        logger.info(f"[EXTRACTION] Calling claim extractor for text length: {len(submitted_text)} chars")

        extraction_result = await extract_claims(submitted_text, config)

        # Check if extraction was successful
        if not extraction_result.get('is_suitable', True):
            logger.warning(f"[EXTRACTION] Text unsuitable: {extraction_result.get('reason')}")
            return {
                'success': False,
                'unsuitable': True,
                'reason': extraction_result.get('reason', 'Text is not suitable for reference checking'),
                'suggestion': extraction_result.get('suggestion', ''),
                'claims': [],
                'total_claims': 0
            }

        # Extract claims and metadata
        claims = extraction_result.get('claims', [])
        total_claims = extraction_result.get('total_claims', len(claims))

        # Get API response for metrics tracking
        api_response = extraction_result.get('api_response', {})
        processing_time = extraction_result.get('processing_time', 0)

        # Extract model info
        extraction_config = config.get('extraction', {})
        model = extraction_config.get('model', 'claude-sonnet-4-5')

        # Get enhanced metrics for tracking
        if 'enhanced_data' in api_response:
            enhanced_data = api_response['enhanced_data']
        else:
            # Fallback: regenerate enhanced metrics
            ai_client = AIAPIClient()
            enhanced_data = ai_client.get_enhanced_call_metrics(
                response=api_response.get('response', api_response),
                model=model,
                processing_time=processing_time,
                pre_extracted_token_usage=api_response.get('token_usage'),
                is_cached=api_response.get('is_cached')
            )

        result = {
            'success': True,
            'claims': claims,
            'total_claims': total_claims,
            'claims_with_references': extraction_result.get('claims_with_references', 0),
            'claims_without_references': extraction_result.get('claims_without_references', 0),
            'source_type_guess': extraction_result.get('source_type_guess', 'Unknown'),
            'source_confidence': extraction_result.get('source_confidence', 0.0),
            'reference_list': extraction_result.get('reference_list'),
            'table_name': extraction_result.get('table_name', 'reference_check'),
            'processing_time': processing_time,
            'model_used': model,
            'enhanced_data': enhanced_data
        }

        logger.info(f"[EXTRACTION] Extracted {total_claims} claims successfully")
        return result

    except Exception as e:
        logger.error(f"[EXTRACTION] Error extracting claims: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'claims': []
        }


async def _validate_single_claim(
    claim: Dict[str, Any],
    claim_index: int,
    total_claims: int,
    session_id: str,
    conversation_id: str,
    config: Dict
) -> Dict[str, Any]:
    """
    Validate a single claim using reference check or fact-check.

    Args:
        claim: Claim dict with statement, reference, etc.
        claim_index: Index of this claim (for progress tracking)
        total_claims: Total number of claims
        session_id: Session identifier
        conversation_id: Conversation identifier
        config: Configuration dict

    Returns:
        {
            'success': bool,
            'claim_id': str,
            'support_level': str,  # strongly_supported, supported, etc.
            'confidence': float,  # 0.0-1.0
            'what_reference_says': str,
            'validation_notes': str,
            'processing_time': float,
            'model_used': str,
            'enhanced_data': Dict,
            'error': str (if failed)
        }
    """
    try:
        claim_id = claim.get('claim_id', f"claim_{claim_index}")
        statement = claim.get('statement', '')
        reference = claim.get('reference', '')
        reference_type = claim.get('reference_type', 'reference_check')

        logger.info(f"[VALIDATION] Validating claim {claim_index+1}/{total_claims}: {claim_id}")

        # Send progress update
        progress = 30 + int((claim_index / total_claims) * 50)  # 30-80%
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=1,
            total_steps=2,
            status=f'Validating claim {claim_index+1} of {total_claims}...',
            progress_percent=progress,
            phase='validation',
            claims_validated=claim_index,
            total_claims=total_claims
        )

        # Call reference validation module
        logger.info(f"[VALIDATION] Validating claim {claim_id} via {reference_type}")
        logger.info(f"[VALIDATION] Statement: {statement[:100]}...")

        validation_result = await validate_claim(claim, config)

        # Check if validation was successful
        if 'error' in validation_result:
            logger.warning(f"[VALIDATION] Claim {claim_id} validation had error: {validation_result.get('error')}")
            # Still return the result (will have support_level='unclear')

        # Get API response for metrics tracking
        api_response = validation_result.get('api_response', {})
        processing_time = validation_result.get('processing_time', 0)

        # Get model info
        validation_config = config.get('validation', {})
        model = validation_config.get('model', 'claude-haiku-4-5')

        # Get enhanced metrics for tracking
        if 'enhanced_data' in api_response:
            enhanced_data = api_response['enhanced_data']
        else:
            # Fallback: regenerate enhanced metrics
            ai_client = AIAPIClient()
            enhanced_data = ai_client.get_enhanced_call_metrics(
                response=api_response.get('response', api_response),
                model=model,
                processing_time=processing_time,
                pre_extracted_token_usage=api_response.get('token_usage'),
                is_cached=api_response.get('is_cached')
            )

        # Add metadata to result
        result = {
            **validation_result,
            'processing_time': processing_time,
            'model_used': model,
            'enhanced_data': enhanced_data,
            'success': True
        }

        support_level = validation_result.get('support_level', 'unknown')
        confidence = validation_result.get('confidence', 0)
        logger.info(f"[VALIDATION] Claim {claim_id} validated: {support_level} (confidence: {confidence:.2f})")
        return result

    except Exception as e:
        logger.error(f"[VALIDATION] Error validating claim {claim.get('claim_id')}: {e}", exc_info=True)
        return {
            'success': False,
            'claim_id': claim.get('claim_id', f"claim_{claim_index}"),
            'error': str(e),
            'support_level': 'error',
            'confidence': 0.0
        }


async def _validate_claims(
    claims: List[Dict[str, Any]],
    session_id: str,
    conversation_id: str,
    config: Dict
) -> List[Dict[str, Any]]:
    """
    Validate all claims in parallel (max 5 at a time).

    Args:
        claims: List of claims to validate
        session_id: Session identifier
        conversation_id: Conversation identifier
        config: Configuration dict

    Returns:
        List of validation results
    """
    try:
        logger.info(f"[VALIDATION] Starting validation of {len(claims)} claims")

        # Get max parallel from config
        max_parallel = config.get('validation', {}).get('max_parallel_validations', 5)

        # Process claims in batches
        validation_results = []
        for i in range(0, len(claims), max_parallel):
            batch = claims[i:i+max_parallel]
            batch_tasks = [
                _validate_single_claim(
                    claim=claim,
                    claim_index=i+j,
                    total_claims=len(claims),
                    session_id=session_id,
                    conversation_id=conversation_id,
                    config=config
                )
                for j, claim in enumerate(batch)
            ]

            # Wait for batch to complete
            batch_results = await asyncio.gather(*batch_tasks)
            validation_results.extend(batch_results)

            logger.info(f"[VALIDATION] Completed batch {i//max_parallel + 1}, total validated: {len(validation_results)}/{len(claims)}")

        logger.info(f"[VALIDATION] All {len(claims)} claims validated")
        return validation_results

    except Exception as e:
        logger.error(f"[VALIDATION] Error validating claims: {e}", exc_info=True)
        return []


async def _compile_results(
    validation_results: List[Dict[str, Any]],
    session_id: str,
    conversation_id: str,
    email: str,
    storage_manager: UnifiedS3Manager,
    config: Dict,
    claims: List[Dict[str, Any]] = None,
    submitted_text: str = None,
    source_guess: str = None,
    ai_source_guess: str = None,
    ai_source_confidence: float = None,
    path_type: str = None,
    final_reference_map: Dict[str, str] = None,
    conversation_state: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Generate CSV with claims (ID columns filled, RESEARCH columns empty).
    Save to session results folder and copy static validation config.

    Args:
        validation_results: List of validation results (empty during extraction phase)
        session_id: Session identifier
        conversation_id: Conversation identifier
        email: User email
        storage_manager: S3 manager instance
        config: Configuration dict
        claims: List of claims from extraction (used when validation_results is empty)

    Returns:
        {
            'success': bool,
            'csv_s3_key': str,
            'csv_filename': str,
            'config_s3_key': str,
            'summary': Dict,
            'error': str (if failed)
        }
    """
    try:
        # If validation_results is empty, generate CSV from claims (ID columns only)
        if not validation_results and claims:
            logger.info(f"[COMPILATION] Generating CSV from {len(claims)} extracted claims (ID columns only)")
            csv_rows = []
            for claim in claims:
                # Expand reference from "[1]" to "1, Full Citation"
                ref_citation = claim.get('reference', '')
                if ref_citation and final_reference_map:
                    expanded_ref = _expand_reference_to_full_format(ref_citation, final_reference_map)
                else:
                    expanded_ref = ref_citation

                csv_rows.append({
                    'claim_id': claim.get('claim_id', ''),
                    'claim_order': claim.get('claim_order', ''),
                    'statement': claim.get('statement', ''),
                    'context': claim.get('context', ''),
                    'text_location': _format_text_location(claim.get('text_location')),
                    'reference': expanded_ref,
                    'supporting_data': claim.get('supporting_data', ''),
                    'criticality': claim.get('criticality', ''),
                    'reference_description': '',  # Empty - to be filled during validation
                    'reference_says': '',  # Empty
                    'qualified_fact': claim.get('statement', ''),  # Pre-populate with original claim
                    'support_level': '',  # Empty
                    'validation_notes': ''  # Empty
                })
            csv_content = compile_results_to_csv(csv_rows, config)
        else:
            logger.info(f"[COMPILATION] Compiling {len(validation_results)} validation results")
            csv_content = compile_results_to_csv(validation_results, config)

        # Send progress update
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=1,
            total_steps=1,
            status='Generating table with extracted claims...',
            progress_percent=85,
            phase='compilation'
        )

        # Generate summary from claims (not validation results yet)
        if not validation_results and claims:
            summary = {
                'total_claims': len(claims),
                'claims_with_references': sum(1 for c in claims if c.get('reference') not in [None, '', []]),
                'claims_without_references': sum(1 for c in claims if c.get('reference') in [None, '', []])
            }
        else:
            summary = get_summary_stats(validation_results, config)

        # Get table name from extraction result (or use default)
        table_name = conversation_state.get('extraction_result', {}).get('table_name', 'reference_check')
        # Sanitize table name for filename
        safe_table_name = re.sub(r'[^\w\s-]', '', table_name).strip().replace(' ', '_')
        if not safe_table_name:
            safe_table_name = 'reference_check'

        # Save CSV using store_excel_file (handles CSV too)
        # Note: store_excel_file automatically adds _input suffix
        csv_filename = f"{safe_table_name}_{conversation_id}.csv"

        store_result = storage_manager.store_excel_file(
            email=email,
            session_id=session_id,
            file_content=csv_content.encode('utf-8'),
            filename=csv_filename
        )

        if not store_result.get('success'):
            raise Exception(f"Failed to store CSV file: {store_result.get('error')}")

        csv_s3_key = store_result.get('s3_key')
        logger.info(f"[COMPILATION] CSV saved to S3: {csv_s3_key}")

        # Define session_path for subsequent operations
        domain = email.split('@')[1] if '@' in email else 'unknown'
        email_prefix = email.split('@')[0] if '@' in email else email
        session_path = f"results/{domain}/{email_prefix}/{session_id}/"

        # Save full source text to results folder
        source_text_filename = f"reference_check_{conversation_id}_source.txt"
        source_text_key = f"{session_path}{source_text_filename}"

        try:
            storage_manager.s3_client.put_object(
                Bucket=storage_manager.bucket_name,
                Key=source_text_key,
                Body=submitted_text.encode('utf-8'),
                ContentType='text/plain',
                Metadata={
                    'conversation_id': conversation_id,
                    'session_id': session_id,
                    'email': email,
                    'source_type': source_guess,
                    'reference_path': path_type,
                    'total_claims': str(len(claims))
                }
            )
            logger.info(f"[COMPILATION] Saved source text to S3: {source_text_key}")
        except Exception as e:
            logger.warning(f"[COMPILATION] Failed to save source text: {e}")

        # Copy static validation config from S3 base location or local file
        config_s3_key = None
        try:
            # Try to load from S3 base config location first
            base_config_key = 'configs/reference_check_validation_config.json'
            try:
                response = storage_manager.s3_client.get_object(
                    Bucket=storage_manager.bucket_name,
                    Key=base_config_key
                )
                validation_config = json.loads(response['Body'].read())
                logger.info(f"[COMPILATION] Loaded base config from S3: {base_config_key}")
            except storage_manager.s3_client.exceptions.NoSuchKey:
                # Fallback to local file
                config_path = Path(__file__).parent / 'reference_check_validation_config.json'
                with open(config_path, 'r') as f:
                    validation_config = json.load(f)
                logger.info(f"[COMPILATION] Loaded config from local file (S3 base not found)")

                # Save to S3 base location for future use
                try:
                    storage_manager.s3_client.put_object(
                        Bucket=storage_manager.bucket_name,
                        Key=base_config_key,
                        Body=json.dumps(validation_config, indent=2),
                        ContentType='application/json'
                    )
                    logger.info(f"[COMPILATION] Saved base config to S3: {base_config_key}")
                except Exception as save_error:
                    logger.warning(f"[COMPILATION] Could not save base config to S3: {save_error}")

            # Load conversation state to get submitted text
            conversation_state = _load_conversation_state(storage_manager, email, session_id, conversation_id)
            if not conversation_state:
                logger.error(f"[COMPILATION] Failed to load conversation state for {conversation_id}")
                submitted_text = ""
                reference_map = {}
            else:
                submitted_text = conversation_state.get('submitted_text', '')

                # Build reference list section
                reference_map = conversation_state.get('reference_map', {})

            # Append submitted text and reference list to general_notes
            original_notes = validation_config.get('general_notes', '')
            if reference_map:
                ref_list_text = "\n\n--- EXTRACTED REFERENCES ---\n\n"
                for ref_id in sorted(reference_map.keys(), key=lambda x: int(re.search(r'\d+', x).group())):
                    ref_list_text += f"{ref_id} {reference_map[ref_id]}\n"
            else:
                ref_list_text = ""

            validation_config['general_notes'] = f"{original_notes}\n\n--- ORIGINAL TEXT PROVIDED BY USER ---\n\n{submitted_text}{ref_list_text}"

            # Update config metadata for this session
            if 'storage_metadata' not in validation_config:
                validation_config['storage_metadata'] = {}
            validation_config['storage_metadata']['session_id'] = session_id
            validation_config['storage_metadata']['email'] = email
            validation_config['storage_metadata']['copied_at'] = datetime.now().isoformat()
            validation_config['storage_metadata']['source'] = 'reference_check_static_template'

            # Save config using store_config_file (proper naming for preview)
            config_store_result = storage_manager.store_config_file(
                email=email,
                session_id=session_id,
                config_data=validation_config,
                version=1,
                source='reference_check',
                description='Reference check validation config with source text',
                original_name='reference_check_validation_config'
            )

            if config_store_result.get('success'):
                config_s3_key = config_store_result.get('s3_key')
                logger.info(f"[COMPILATION] Validation config saved to S3: {config_s3_key}")
            else:
                raise Exception(f"Failed to store config: {config_store_result.get('error')}")

        except Exception as config_error:
            logger.error(f"[COMPILATION] Exception copying validation config: {config_error}", exc_info=True)
            config_s3_key = None

        # Update session_info.json with reference check activity (AFTER config is saved)
        try:
            session_info = storage_manager.load_session_info(email, session_id)
            logger.info(f"[COMPILATION] Loaded session_info, updating with reference check data")

            # Add reference_check tracking section
            if 'reference_check' not in session_info:
                session_info['reference_check'] = {}

            session_info['reference_check'][conversation_id] = {
                'conversation_id': conversation_id,
                'created_at': datetime.now().isoformat(),
                'source_detection': {
                    'python_guess': source_guess if source_guess else 'Unknown',
                    'ai_guess': ai_source_guess if ai_source_guess else 'Unknown',
                    'ai_confidence': ai_source_confidence if ai_source_confidence else 0.0,
                    'reference_path': path_type if path_type else 'unknown'
                },
                'total_claims': len(claims) if claims else 0,
                'claims_with_references': summary.get('claims_with_references', 0),
                'claims_without_references': summary.get('claims_without_references', 0),
                'references_extracted': len(final_reference_map) if final_reference_map else 0,
                'csv_s3_key': csv_s3_key,
                'config_s3_key': config_s3_key,
                'source_text_s3_key': source_text_key,
                'status': 'complete'
            }

            # Also update table_path for compatibility
            session_info['table_path'] = csv_s3_key
            session_info['table_name'] = f"reference_check_{conversation_id}"
            session_info['session_id'] = session_id
            session_info['email'] = email

            save_success = storage_manager.save_session_info(email, session_id, session_info)
            if save_success:
                logger.info(f"[COMPILATION] Updated session_info.json with reference check tracking")
            else:
                logger.error(f"[COMPILATION] Failed to save session_info.json (returned False)")
        except Exception as session_info_error:
            logger.error(f"[COMPILATION] Exception updating session_info.json: {session_info_error}", exc_info=True)

        logger.info(f"[COMPILATION] Summary: {summary}")

        return {
            'success': True,
            'csv_s3_key': csv_s3_key,
            'csv_filename': csv_filename,
            'table_name': table_name,  # Include table name for frontend
            'config_s3_key': config_s3_key,
            'summary': summary
        }

    except Exception as e:
        logger.error(f"[COMPILATION] Error compiling results: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }


async def execute_reference_check(
    email: str,
    session_id: str,
    conversation_id: str,
    run_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute the complete reference check pipeline.

    Pipeline Flow:
        Step 0: Extract Claims (~10-30s)
            - Use SONNET 4.5 to extract claims from submitted text
            - Identify which claims need reference checking vs fact-checking
            - Return structured list of claims with references
            ↓
        Step 1: Validate Claims (~30-120s depending on claim count)
            - For each claim: validate reference or fact-check
            - Process in parallel (max 5 at a time)
            - Track support level, confidence, and notes for each claim
            ↓
        Step 2: Compile Results (~5s)
            - Generate CSV with all validation results
            - Create summary statistics (support level breakdown)
            - Save to S3
            ↓
        Complete

    Total Duration: ~45-155 seconds (depending on claim count)
    Total Cost: ~$0.02-0.15 (depending on claim count and complexity)

    Args:
        email: User email
        session_id: Session identifier
        conversation_id: Conversation identifier
        run_key: Run tracking key (optional)

    Returns:
        {
            'success': bool,
            'conversation_id': str,
            'csv_s3_key': str,
            'csv_filename': str,
            'summary': Dict,
            'error': Optional[str]
        }
    """
    result = {
        'success': False,
        'conversation_id': conversation_id,
        'csv_s3_key': None,
        'csv_filename': None,
        'summary': None,
        'error': None
    }

    try:
        logger.info(f"[EXECUTION] Starting reference check pipeline for {conversation_id}")

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

        # Get submitted text
        submitted_text = conversation_state.get('submitted_text', '')
        if not submitted_text:
            result['error'] = 'No submitted text found in conversation state'
            logger.error(f"[EXECUTION] {result['error']}")
            return result

        # Load config
        config = _load_config()

        # Send initial progress
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=0,
            total_steps=2,
            status='Starting reference check pipeline',
            progress_percent=5,
            phase='initialization'
        )

        # Update runs database
        if run_key:
            try:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='IN_PROGRESS',
                    run_type='Reference Check',
                    verbose_status='Starting 3-step pipeline',
                    percent_complete=5
                )
            except Exception as e:
                logger.warning(f"[EXECUTION] Failed to update run status: {e}")

        # ======================================================================
        # STEP 0: Pre-parse References and Extract Claims
        # ======================================================================
        logger.info("[EXECUTION] Step 0a: Pre-parse references from text")

        # Parse references BEFORE sending to AI
        from .reference_check_lib.reference_parser import ReferenceParser
        parser = ReferenceParser()

        parsed_reference_map = parser.extract_reference_list(submitted_text)
        path_type, confidence = parser.detect_reference_format(submitted_text, parsed_reference_map)

        logger.info(f"[EXECUTION] Reference detection: path={path_type}, confidence={confidence:.2f}")

        # Guess source type for better context
        content_type = parser.detect_content_type(submitted_text)
        source_guess = parser.guess_source_type(submitted_text, parsed_reference_map, content_type, path_type)
        logger.info(f"[EXECUTION] Source guess: {source_guess}")

        # ======================================================================
        # STEP 0a-2: AI Reference Extraction (when Python parsing needs confirmation)
        # ======================================================================
        confirmed_reference_map = parsed_reference_map

        # Check if AI reference extraction is needed
        ref_extraction_config = config.get('reference_extraction', {})
        ref_extraction_enabled = ref_extraction_config.get('enabled', True)

        if ref_extraction_enabled and path_type == "needs_parsing":
            # Run quality check on Python-parsed refs
            is_good, failure_reason = parser.check_reference_quality(parsed_reference_map)

            if not is_good:
                # Python parsing failed - use AI to extract references
                logger.info(f"[EXECUTION] Python refs failed quality check: {failure_reason}")
                logger.info(f"[EXECUTION] Calling AI reference extractor (haiku-4-5) to extract references")

                # Send progress update
                send_execution_progress(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    current_step=0,
                    total_steps=2,
                    status='Extracting references from document...',
                    progress_percent=30,
                    phase='reference_extraction'
                )

                from .reference_check_lib.reference_extractor import extract_references
                ref_extraction_result = await extract_references(
                    text=submitted_text,
                    config=config,
                    parsed_refs=parsed_reference_map  # Pass for context
                )

                if ref_extraction_result.get('success') and ref_extraction_result.get('references'):
                    # Use AI-extracted references
                    confirmed_reference_map = {
                        r['ref_id']: r['full_citation']
                        for r in ref_extraction_result['references']
                    }
                    logger.info(f"[EXECUTION] AI extracted {len(confirmed_reference_map)} references successfully")

                    # Track API call for reference extraction
                    if run_key and ref_extraction_result.get('api_response'):
                        _add_api_call_to_runs(
                            session_id=session_id,
                            run_key=run_key,
                            api_response=ref_extraction_result['api_response'],
                            model=ref_extraction_config.get('model', 'claude-haiku-4-5'),
                            processing_time=ref_extraction_result.get('processing_time', 0.0),
                            call_type='reference_extraction',
                            status='IN_PROGRESS',
                            verbose_status=f'Extracted {len(confirmed_reference_map)} references',
                            percent_complete=30
                        )
                else:
                    # AI extraction failed - fall back to Python refs
                    logger.warning(f"[EXECUTION] AI reference extraction failed, using Python refs as fallback")
                    confirmed_reference_map = parsed_reference_map
            else:
                # Python refs passed quality check - use them
                logger.info(f"[EXECUTION] Python refs passed quality check, using them directly")
                confirmed_reference_map = parsed_reference_map
        elif ref_extraction_enabled and path_type == "not_found":
            # No refs found by Python - try AI extraction
            logger.info(f"[EXECUTION] No references found by Python, trying AI extraction")

            # Send progress update
            send_execution_progress(
                session_id=session_id,
                conversation_id=conversation_id,
                current_step=0,
                total_steps=2,
                status='Extracting references from document...',
                progress_percent=30,
                phase='reference_extraction'
            )

            from .reference_check_lib.reference_extractor import extract_references
            ref_extraction_result = await extract_references(
                text=submitted_text,
                config=config,
                parsed_refs=None
            )

            if ref_extraction_result.get('success') and ref_extraction_result.get('references'):
                confirmed_reference_map = {
                    r['ref_id']: r['full_citation']
                    for r in ref_extraction_result['references']
                }
                logger.info(f"[EXECUTION] AI extracted {len(confirmed_reference_map)} references from document")

                # Track API call
                if run_key and ref_extraction_result.get('api_response'):
                    _add_api_call_to_runs(
                        session_id=session_id,
                        run_key=run_key,
                        api_response=ref_extraction_result['api_response'],
                        model=ref_extraction_config.get('model', 'claude-haiku-4-5'),
                        processing_time=ref_extraction_result.get('processing_time', 0.0),
                        call_type='reference_extraction',
                        status='IN_PROGRESS',
                        verbose_status=f'Extracted {len(confirmed_reference_map)} references',
                        percent_complete=30
                    )
            else:
                # No refs found
                logger.info(f"[EXECUTION] No references found by AI either")
                confirmed_reference_map = {}

        # Build enriched text with confirmed references
        enriched_text = parser.build_enriched_text(submitted_text, confirmed_reference_map, path_type, source_guess)

        logger.info("[EXECUTION] Step 0b: Extract Claims")

        extraction_result = await _extract_claims(
            submitted_text=enriched_text,  # Send enriched text, not original
            conversation_id=conversation_id,
            session_id=session_id,
            config=config
        )

        if not extraction_result.get('success'):
            # Check if text was unsuitable (not an error, just wrong type of content)
            if extraction_result.get('unsuitable'):
                result['error'] = extraction_result.get('reason', 'Text is not suitable for reference checking')
                result['suggestion'] = extraction_result.get('suggestion', '')
                logger.warning(f"[EXECUTION] Text unsuitable: {result['error']}")

                # Send more helpful WebSocket message
                ws_client = _get_websocket_client()
                if ws_client:
                    ws_client.send_to_session(session_id, {
                        'type': 'reference_check_unsuitable',
                        'conversation_id': conversation_id,
                        'status': 'unsuitable',
                        'reason': result['error'],
                        'suggestion': result['suggestion'],
                        'message': f"{result['error']}. {result['suggestion']}"
                    })
            else:
                result['error'] = f"Claim extraction failed: {extraction_result.get('error')}"
                logger.error(f"[EXECUTION] {result['error']}")

            # Update run status to failed
            if run_key:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='FAILED',
                    verbose_status=result['error'],
                    percent_complete=0
                )

            return result

        claims = extraction_result.get('claims', [])
        logger.info(f"[EXECUTION] Step 0 complete: {len(claims)} claims extracted")

        # Log source type guesses for comparison
        ai_source_guess = extraction_result.get('source_type_guess', 'Unknown')
        ai_source_confidence = extraction_result.get('source_confidence', 0.0)
        logger.info(f"[EXECUTION] Source detection - Python: '{source_guess}', AI: '{ai_source_guess}' (confidence: {ai_source_confidence:.2f})")

        # Use confirmed reference map (already determined in Step 0a-2)
        final_reference_map = confirmed_reference_map
        logger.info(f"[EXECUTION] Using confirmed reference map with {len(final_reference_map)} references")

        # Keep claims with just numbered citations like [1], [2]
        # Full references will be expanded in CSV generation
        logger.info(f"[EXECUTION] Claims extracted with {len(claims)} numbered citations")

        # Store reference map for config
        conversation_state['reference_map'] = final_reference_map
        conversation_state['reference_path'] = path_type
        _save_conversation_state(storage_manager, email, session_id, conversation_id, conversation_state)

        # Check if no claims were extracted
        if len(claims) == 0:
            result['error'] = 'No verifiable claims found in the submitted text'
            logger.warning(f"[EXECUTION] {result['error']}")

            # Update run status to failed
            if run_key:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='FAILED',
                    verbose_status='No verifiable claims found in text',
                    percent_complete=0
                )

            # Send error via WebSocket
            ws_client = _get_websocket_client()
            if ws_client:
                ws_client.send_to_session(session_id, {
                    'type': 'reference_check_error',
                    'conversation_id': conversation_id,
                    'status': 'error',
                    'message': 'No verifiable claims found in your text. Please submit text containing factual claims with citations.'
                })

            return result

        # Track API call
        if run_key and extraction_result.get('enhanced_data'):
            _add_api_call_to_runs(
                session_id=session_id,
                run_key=run_key,
                api_response=extraction_result,
                model=extraction_result.get('model_used', 'claude-sonnet-4-5'),
                processing_time=extraction_result.get('processing_time', 0.0),
                call_type='claim_extraction',
                status='IN_PROGRESS',
                verbose_status=f'Extracted {len(claims)} claims',
                percent_complete=25
            )

        # Save extraction result to S3
        _save_to_s3(
            storage_manager, email, session_id, conversation_id,
            'extraction_result.json', extraction_result
        )

        # Update conversation state
        conversation_state['extraction_result'] = extraction_result
        _save_conversation_state(storage_manager, email, session_id, conversation_id, conversation_state)

        # ======================================================================
        # STEP 1: Generate CSV with ID Columns Only (No Validation Yet)
        # ======================================================================
        logger.info("[EXECUTION] Step 1/1: Generate CSV with extracted claims")

        # Create CSV with ID columns populated, RESEARCH columns empty
        compilation_result = await _compile_results(
            validation_results=[],  # Empty - no validation done yet
            session_id=session_id,
            conversation_id=conversation_id,
            email=email,
            storage_manager=storage_manager,
            config=config,
            claims=claims,  # Pass claims for CSV generation
            submitted_text=submitted_text,
            source_guess=source_guess,
            ai_source_guess=ai_source_guess,
            ai_source_confidence=ai_source_confidence,
            path_type=path_type,
            final_reference_map=final_reference_map,
            conversation_state=conversation_state  # Pass conversation_state
        )

        if not compilation_result.get('success'):
            result['error'] = f"Result compilation failed: {compilation_result.get('error')}"
            logger.error(f"[EXECUTION] {result['error']}")
            return result

        logger.info(f"[EXECUTION] Step 2 complete: CSV generated")

        # Update result
        result['success'] = True
        result['csv_s3_key'] = compilation_result.get('csv_s3_key')
        result['csv_filename'] = compilation_result.get('csv_filename')
        result['table_name'] = compilation_result.get('table_name')
        result['config_s3_key'] = compilation_result.get('config_s3_key')
        result['summary'] = compilation_result.get('summary')
        result['session_id'] = session_id  # Include session_id in response

        # Update conversation state
        conversation_state['csv_s3_key'] = result['csv_s3_key']
        conversation_state['config_s3_key'] = result['config_s3_key']
        conversation_state['summary'] = result['summary']
        conversation_state['status'] = 'complete'
        conversation_state['completed_at'] = datetime.now().isoformat()
        _save_conversation_state(storage_manager, email, session_id, conversation_id, conversation_state)

        # Send final progress
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=1,
            total_steps=1,
            status='Claim extraction complete!',
            progress_percent=100,
            phase='complete'
        )

        # Send completion message (like table_maker does)
        ws_client = _get_websocket_client()
        if ws_client:
            ws_client.send_to_session(session_id, {
                'type': 'reference_check_complete',
                'conversation_id': conversation_id,
                'status': 'complete',
                'csv_s3_key': result['csv_s3_key'],
                'csv_filename': result['csv_filename'],
                'table_name': result.get('table_name', 'Reference Check'),
                'config_s3_key': result['config_s3_key'],
                'session_id': session_id,
                'summary': result['summary'],
                'claims': [{'claim_id': c['claim_id'], 'statement': c['statement'], 'reference': c.get('reference', 'None')} for c in claims[:10]]
            })

        # Update runs database
        if run_key:
            try:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='COMPLETE',
                    verbose_status=f"Completed: {result['summary']['total_claims']} claims validated",
                    percent_complete=100
                )
            except Exception as e:
                logger.warning(f"[EXECUTION] Failed to update run status: {e}")

        logger.info(f"[EXECUTION] Pipeline complete: {result['summary']['total_claims']} claims validated")
        return result

    except Exception as e:
        result['error'] = f"Execution pipeline error: {str(e)}"
        logger.error(f"[EXECUTION] {result['error']}", exc_info=True)

        # Update run status to failed
        if run_key:
            try:
                update_run_status(
                    session_id=session_id,
                    run_key=run_key,
                    status='FAILED',
                    verbose_status=f"Error: {str(e)[:100]}",
                    percent_complete=0
                )
            except Exception as e2:
                logger.warning(f"[EXECUTION] Failed to update run status: {e2}")

        # Send error via WebSocket
        ws_client = _get_websocket_client()
        if ws_client:
            ws_client.send_to_session(session_id, {
                'type': 'reference_check_error',
                'conversation_id': conversation_id,
                'status': 'error',
                'message': 'An error occurred during reference check. Please try again.'
            })

        return result
