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
    "status": "Extracting claims from text...",
    "progress_percent": 10,
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
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

# Lambda infrastructure imports
from interface_lambda.core.unified_s3_manager import UnifiedS3Manager
from dynamodb_schemas import update_run_status

# WebSocket client for real-time updates
try:
    from websocket_client import WebSocketClient
    websocket_client = WebSocketClient()
except ImportError:
    websocket_client = None
    logger = logging.getLogger()
    logger.warning("WebSocket client not available")

# AI API client
from ai_api_client import AIAPIClient

# Import conversation helpers
from .conversation import _load_conversation_state, _save_conversation_state

# Import AI logic modules
from .reference_check_lib.claim_extractor import extract_claims
from .reference_check_lib.reference_validator import validate_claim
from .reference_check_lib.result_compiler import compile_results_to_csv, get_summary_stats

logger = logging.getLogger()
logger.setLevel(logging.INFO)


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
    if not websocket_client or not session_id:
        return

    try:
        message = {
            'type': 'reference_check_progress',
            'conversation_id': conversation_id,
            'current_step': current_step,
            'total_steps': total_steps,
            'status': status,
            'progress_percent': progress_percent,
            'phase': phase,
            **kwargs
        }

        websocket_client.send_to_session(session_id, message)
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
            status='Analyzing text and extracting claims...',
            progress_percent=20,
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
    config: Dict
) -> Dict[str, Any]:
    """
    Compile validation results into CSV and generate summary.
    Save to session results folder (like table_maker) and copy static validation config.

    Args:
        validation_results: List of validation results
        session_id: Session identifier
        conversation_id: Conversation identifier
        email: User email
        storage_manager: S3 manager instance
        config: Configuration dict

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
        logger.info(f"[COMPILATION] Compiling {len(validation_results)} validation results")

        # Send progress update
        send_execution_progress(
            session_id=session_id,
            conversation_id=conversation_id,
            current_step=2,
            total_steps=2,
            status='Compiling results into CSV...',
            progress_percent=85,
            phase='compilation'
        )

        # Use result compiler module to generate CSV
        csv_content = compile_results_to_csv(validation_results, config)

        # Get summary statistics
        summary = get_summary_stats(validation_results, config)

        # Save CSV to session results folder (like table_maker does)
        # Use results/ path structure for consistency with table_maker
        domain = email.split('@')[1] if '@' in email else 'unknown'
        email_prefix = email.split('@')[0] if '@' in email else email
        csv_filename = f"reference_check_{conversation_id}.csv"
        csv_s3_key = f"results/{domain}/{email_prefix}/{session_id}/{csv_filename}"

        storage_manager.s3_client.put_object(
            Bucket=storage_manager.bucket_name,
            Key=csv_s3_key,
            Body=csv_content,
            ContentType='text/csv'
        )

        logger.info(f"[COMPILATION] CSV saved to S3: {csv_s3_key}")

        # Copy static validation config from local file to session
        try:
            config_path = Path(__file__).parent / 'reference_check_validation_config.json'
            with open(config_path, 'r') as f:
                validation_config = json.load(f)

            # Load conversation state to get submitted text
            conversation_state = _load_conversation_state(storage_manager, email, session_id, conversation_id)
            submitted_text = conversation_state.get('submitted_text', '')

            # Append submitted text to general_notes
            original_notes = validation_config.get('general_notes', '')
            validation_config['general_notes'] = f"{original_notes}\n\n--- ORIGINAL TEXT PROVIDED BY USER ---\n\n{submitted_text}"

            # Update config metadata for this session
            if 'storage_metadata' not in validation_config:
                validation_config['storage_metadata'] = {}
            validation_config['storage_metadata']['session_id'] = session_id
            validation_config['storage_metadata']['email'] = email
            validation_config['storage_metadata']['copied_at'] = datetime.now().isoformat()
            validation_config['storage_metadata']['source'] = 'reference_check_static_template'

            # Save config to session results folder
            config_filename = f"reference_check_validation_config.json"
            config_s3_key = f"results/{domain}/{email_prefix}/{session_id}/{config_filename}"

            storage_manager.s3_client.put_object(
                Bucket=storage_manager.bucket_name,
                Key=config_s3_key,
                Body=json.dumps(validation_config, indent=2),
                ContentType='application/json'
            )

            logger.info(f"[COMPILATION] Validation config copied to S3: {config_s3_key}")

        except Exception as config_error:
            logger.warning(f"[COMPILATION] Failed to copy validation config: {config_error}")
            config_s3_key = None

        logger.info(f"[COMPILATION] Summary: {summary}")

        return {
            'success': True,
            'csv_s3_key': csv_s3_key,
            'csv_filename': csv_filename,
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
        # STEP 0: Extract Claims
        # ======================================================================
        logger.info("[EXECUTION] Step 0/2: Extract Claims")

        extraction_result = await _extract_claims(
            submitted_text=submitted_text,
            conversation_id=conversation_id,
            session_id=session_id,
            config=config
        )

        if not extraction_result.get('success'):
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
        # STEP 1: Validate Claims
        # ======================================================================
        logger.info(f"[EXECUTION] Step 1/2: Validate {len(claims)} Claims")

        validation_results = await _validate_claims(
            claims=claims,
            session_id=session_id,
            conversation_id=conversation_id,
            config=config
        )

        logger.info(f"[EXECUTION] Step 1 complete: {len(validation_results)} claims validated")

        # Track API calls for each validation
        if run_key:
            for validation_result in validation_results:
                if validation_result.get('success') and validation_result.get('enhanced_data'):
                    _add_api_call_to_runs(
                        session_id=session_id,
                        run_key=run_key,
                        api_response=validation_result,
                        model=validation_result.get('model_used', 'claude-haiku-4-5'),
                        processing_time=validation_result.get('processing_time', 0.0),
                        call_type='reference_validation',
                        status='IN_PROGRESS',
                        verbose_status=f'Validated claim {validation_result.get("claim_id")}'
                    )

        # Save validation results to S3
        _save_to_s3(
            storage_manager, email, session_id, conversation_id,
            'validation_results.json', validation_results
        )

        # Update conversation state
        conversation_state['validation_results'] = validation_results
        _save_conversation_state(storage_manager, email, session_id, conversation_id, conversation_state)

        # ======================================================================
        # STEP 2: Compile Results
        # ======================================================================
        logger.info("[EXECUTION] Step 2/2: Compile Results")

        compilation_result = await _compile_results(
            validation_results=validation_results,
            session_id=session_id,
            conversation_id=conversation_id,
            email=email,
            storage_manager=storage_manager,
            config=config
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
            current_step=2,
            total_steps=2,
            status='Reference check complete!',
            progress_percent=100,
            phase='complete'
        )

        # Send completion message with results (like table_maker does)
        if websocket_client:
            # Flatten summary for frontend compatibility
            summary = result['summary']
            breakdown = summary.get('support_level_breakdown', {})

            websocket_client.send_to_session(session_id, {
                'type': 'reference_check_complete',
                'conversation_id': conversation_id,
                'status': 'complete',
                'csv_s3_key': result['csv_s3_key'],
                'csv_filename': result['csv_filename'],
                'config_s3_key': result['config_s3_key'],
                'session_id': session_id,
                'summary': {
                    **summary,
                    # Flatten support level counts for frontend
                    'strongly_supported': breakdown.get('strongly_supported', 0),
                    'supported': breakdown.get('supported', 0),
                    'partially_supported': breakdown.get('partially_supported', 0),
                    'unclear': breakdown.get('unclear', 0),
                    'contradicted': breakdown.get('contradicted', 0),
                    'inaccessible': breakdown.get('inaccessible', 0)
                }
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
        if websocket_client:
            websocket_client.send_to_session(session_id, {
                'type': 'reference_check_error',
                'conversation_id': conversation_id,
                'status': 'error',
                'message': 'An error occurred during reference check. Please try again.'
            })

        return result
