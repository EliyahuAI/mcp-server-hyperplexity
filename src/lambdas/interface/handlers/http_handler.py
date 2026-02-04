"""
Handles HTTP requests from API Gateway.
"""
import base64
import json
import logging
import sys
from pathlib import Path

from interface_lambda.utils.helpers import create_response
from interface_lambda.utils.parsing import parse_multipart_form_data

# Module-level cache for lazy-loaded modules
_loaded_modules = {}

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lazy_import(module_path, module_name):
    """Lazy import with caching to minimize import-time dependencies."""
    key = f"{module_path}.{module_name}"
    if key not in _loaded_modules:
        logger.debug(f"Lazy loading: {key}")
        module = __import__(module_path, fromlist=[module_name])
        _loaded_modules[key] = getattr(module, module_name)
    return _loaded_modules[key]

def handle(event, context):
    """
    Handle HTTP requests.
    This function parses the incoming event and routes it to the appropriate
    action handler, LAZILY loading only the code needed for the specific action.
    """
    logger.info("--- HTTP Handler: Routing request ---")
    
    # Handle CORS preflight OPTIONS requests immediately
    if event.get('httpMethod') == 'OPTIONS':
        logger.info("Handling OPTIONS preflight request")
        return create_response(200, "")

    # Handle dedicated health check
    if event.get('path', '') == '/health':
        logger.info("Handling /health check")
        return create_response(200, {'status': 'ok'})

    # Handle payment webhooks from SquareSpace
    if event.get('path', '') == '/webhook/payment' or event.get('path', '') == '/payment/webhook':
        logger.info("Handling payment webhook")
        payment_webhook = lazy_import('interface_lambda.actions', 'payment_webhook')
        return payment_webhook.handle_webhook_request(event, context)

    # Status check via GET request (lightweight)
    if event.get('httpMethod') == 'GET' and event.get('path', '').startswith('/status/'):
        status_check = lazy_import('interface_lambda.actions', 'status_check')
        return status_check.handle_get_status(event, context)

    # All other actions are POST requests
    if event.get('httpMethod') == 'POST':
        headers = event.get('headers', {})
        content_type = headers.get('Content-Type') or headers.get('content-type', '')
        logger.info(f"POST request with Content-Type: {content_type}")

        # Multipart form data for file uploads (heavyweight)
        if 'multipart/form-data' in content_type:
            # SECURITY: Verify session token for file uploads (all require authentication)
            session_manager = lazy_import('interface_lambda.utils', 'session_manager')
            verified_email = session_manager.extract_email_from_request({}, headers)

            if not verified_email:
                logger.warning(f"[SECURITY] Unauthorized file upload attempt")
                return create_response(401, {
                    'success': False,
                    'error': 'Authentication required. Please log in.',
                    'token_revoked': True
                })

            logger.info(f"[SECURITY] Token verified for file upload: {verified_email}")

            # Check if this is a config generation request based on form fields
            try:
                files, form_data = parse_multipart_form_data(
                    event.get('body', ''), content_type, event.get('isBase64Encoded', False)
                )

                # Add verified email to form_data for action handlers
                form_data['_verified_email'] = verified_email

                # Check for PDF conversion action
                if form_data.get('action') == 'convertPdfToMarkdown':
                    pdf_converter = lazy_import('interface_lambda.actions.reference_check', 'pdf_converter')
                    return pdf_converter.handle_pdf_multipart(files, form_data, context)

                # If generation_mode is present, route to config generation
                if 'generation_mode' in form_data:
                    generate_config_unified = lazy_import('interface_lambda.actions', 'generate_config_unified')
                    return generate_config_unified.handle_generate_config_sync(form_data, context)
            except Exception:
                pass  # Fall through to default Excel processing

            # Default to Excel processing with unified storage
            process_excel_unified = lazy_import('interface_lambda.actions', 'process_excel_unified')
            return process_excel_unified.handle_multipart_form(event, context)

        # JSON body for API-style actions
        elif 'application/json' in content_type:
            body = event.get('body', '{}')
            if event.get('isBase64Encoded'):
                body = base64.b64decode(body).decode('utf-8')
            
            try:
                request_data = json.loads(body)
                # SECURITY: Add headers and requestContext to request_data for action handlers
                request_data['_headers'] = headers
                request_data['_requestContext'] = event.get('requestContext', {})
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in request body: {e}")
                return create_response(400, {'error': 'Invalid JSON format'})

            # Route to action based on 'action' field in JSON body
            action = request_data.get('action')

            # SECURITY: Define public endpoints that don't require authentication
            public_actions = [
                'requestEmailValidation',
                'validateEmailCode',
                'checkEmailValidation',
                'checkOrSendValidation',
                'logout',  # User-initiated logout
                'getDemoData',  # Public demo data
                'getPublicDemoList',  # Public demo list
                'checkStatus'  # Status checks can be unauthenticated
            ]

            # SECURITY: Verify session token for protected endpoints
            if action not in public_actions:
                session_manager = lazy_import('interface_lambda.utils', 'session_manager')
                verified_email = session_manager.extract_email_from_request(request_data, headers)

                if not verified_email:
                    logger.warning(f"[SECURITY] Unauthorized request to action: {action}")
                    return create_response(401, {
                        'success': False,
                        'error': 'Authentication required. Please log in.',
                        'token_revoked': True
                    })

                # Store verified email in request_data for action handlers to use
                request_data['_verified_email'] = verified_email
                logger.info(f"[SECURITY] Token verified for action '{action}': {verified_email}")

            # Legacy email_actions list (kept for compatibility)
            email_actions = public_actions[:5]  # First 5 are email-related

            if action == 'processExcel':
                process_excel_unified = lazy_import('interface_lambda.actions', 'process_excel_unified')
                return process_excel_unified.handle_json_request(event, context)
            elif action == 'generateConfig':
                # Check for async parameter in query string
                query_params = event.get('queryStringParameters') or {}
                is_async = query_params.get('async', 'false').lower() == 'true'

                logger.info(f"generateConfig: query_params={query_params}, is_async={is_async}")

                generate_config_unified = lazy_import('interface_lambda.actions', 'generate_config_unified')
                if is_async:
                    logger.info("Using ASYNC config generation path")
                    return generate_config_unified.handle_generate_config_async(request_data, context)
                else:
                    logger.info("Using SYNC config generation path")
                    return generate_config_unified.handle_generate_config_sync(request_data, context)
            elif action == 'submitInterviewResponses':
                generate_config_unified = lazy_import('interface_lambda.actions', 'generate_config_unified')
                return generate_config_unified.handle_generate_config_sync(request_data, context)
            elif action == 'modifyConfig':
                # Check for async parameter in query string
                query_params = event.get('queryStringParameters') or {}
                is_async = query_params.get('async', 'false').lower() == 'true'

                logger.info(f"=== MODIFY CONFIG REQUEST ===")
                logger.info(f"Query params: {query_params}")
                logger.info(f"Is async: {is_async}")
                logger.info(f"Request data keys: {list(request_data.keys())}")

                generate_config_unified = lazy_import('interface_lambda.actions', 'generate_config_unified')
                if is_async:
                    logger.info("[SUCCESS] USING ASYNC CONFIG MODIFICATION - WebSocket only response")
                    return generate_config_unified.handle_generate_config_async(request_data, context)
                else:
                    logger.info("[SUCCESS] USING SYNC CONFIG MODIFICATION - HTTP response with full data")
                    return generate_config_unified.handle_modify_config(request_data, context)
            elif action == 'repairConfig':
                # Config repair is essentially the same as modify but with repair context
                # Always use async for repair operations
                logger.info(f"=== REPAIR CONFIG REQUEST ===")
                logger.info(f"Request data keys: {list(request_data.keys())}")
                logger.info("[SUCCESS] USING ASYNC CONFIG REPAIR - WebSocket only response")
                generate_config_unified = lazy_import('interface_lambda.actions', 'generate_config_unified')
                return generate_config_unified.handle_generate_config_async(request_data, context)
            elif action in email_actions:
                email_validation = lazy_import('interface_lambda.actions', 'email_validation')
                return email_validation.handle(request_data, context)
            elif action == 'getUserStats':
                user_stats = lazy_import('interface_lambda.actions', 'user_stats')
                return user_stats.handle(request_data, context)
            elif action == 'validateConfig':
                config_validation = lazy_import('interface_lambda.actions', 'config_validation')
                return config_validation.handle(request_data, context)
            elif action == 'checkStatus' or request_data.get('status_check'):
                status_check = lazy_import('interface_lambda.actions', 'status_check')
                return status_check.handle_post_status(request_data, context)
            elif action == 'diagnostics':
                diagnostics = lazy_import('interface_lambda.actions', 'diagnostics')
                return diagnostics.handle(request_data, context)
            elif action == 'findMatchingConfig':
                find_matching_config = lazy_import('interface_lambda.actions', 'find_matching_config')
                return find_matching_config.handle_find_matching_config(request_data, context)
            elif action == 'copyConfig':
                copy_config = lazy_import('interface_lambda.actions', 'copy_config')
                return copy_config.handle_copy_config(request_data, context)
            elif action == 'useConfigById':
                use_config_by_id = lazy_import('interface_lambda.actions', 'use_config_by_id')
                return use_config_by_id.handle_use_config_by_id(request_data, context)
            elif action == 'requestPresignedUrl':
                presigned_upload = lazy_import('interface_lambda.actions', 'presigned_upload')
                return presigned_upload.request_presigned_url(request_data, context)
            elif action == 'confirmUploadComplete':
                presigned_upload = lazy_import('interface_lambda.actions', 'presigned_upload')
                return presigned_upload.confirm_upload_complete(request_data, context)
            elif action == 'getAccountBalance':
                account_balance = lazy_import('interface_lambda.actions', 'account_balance')
                return account_balance.handle(request_data, context)
            elif action == 'addCredits':
                account_balance = lazy_import('interface_lambda.actions', 'account_balance')
                return account_balance.handle_add_credits(request_data, context)
            elif action == 'checkSquarespaceOrders':
                check_squarespace_orders = lazy_import('interface_lambda.actions', 'check_squarespace_orders')
                return check_squarespace_orders.handle(request_data, context)
            elif action == 'getAiSummary':
                get_ai_summary = lazy_import('interface_lambda.actions', 'get_ai_summary')
                return get_ai_summary.handle_get_ai_summary(request_data, context)
            elif action in ['listDemos', 'selectDemo', 'clearUserHistoryForTesting']:
                demo_management = lazy_import('interface_lambda.actions', 'demo_management')
                return demo_management.handle(request_data, context)
            elif action in ['startTableConversation', 'continueTableConversation', 'generateTablePreview', 'acceptTableAndValidate', 'getTableDownloadUrl', 'initTableMakerSession']:
                route_table_maker_action = lazy_import('interface_lambda.actions.table_maker', 'route_table_maker_action')
                return route_table_maker_action(action, request_data, context)
            elif action in ['startReferenceCheck']:
                route_reference_check_action = lazy_import('interface_lambda.actions.reference_check', 'route_reference_check_action')
                return route_reference_check_action(action, request_data, context)
            elif action in ['startUploadInterview', 'continueUploadInterview']:
                route_upload_interview_action = lazy_import('interface_lambda.actions.upload_interview', 'route_upload_interview_action')
                return route_upload_interview_action(action, request_data, context)
            elif action in ['getMessagesForCard', 'getMessagesSince']:
                message_replay = lazy_import('interface_lambda.actions', 'message_replay')
                return message_replay.handle(request_data, context)
            elif action == 'getViewerData':
                viewer_data = lazy_import('interface_lambda.actions', 'viewer_data')
                return viewer_data.handle(request_data, context)
            elif action == 'getDemoData':
                demo_data = lazy_import('interface_lambda.actions', 'demo_data')
                return demo_data.handle(request_data, context)
            elif action == 'createUpdateSession':
                create_update_session = lazy_import('interface_lambda.actions', 'create_update_session')
                return create_update_session.handle_create_update_session(request_data, context)
            elif action == 'shareTable':
                share_table = lazy_import('interface_lambda.actions', 'share_table')
                return share_table.handle(request_data, context)
            elif action == 'unshareTable':
                share_table = lazy_import('interface_lambda.actions', 'share_table')
                return share_table.handle_unshare(request_data, context)
            elif action == 'checkShareStatus':
                share_table = lazy_import('interface_lambda.actions', 'share_table')
                return share_table.handle_check_share_status(request_data, context)
            else:
                logger.warning(f"Unknown action in JSON body: {action}")
                return create_response(400, {'error': f'Unknown or unsupported action: {action}'})
        
        # Fallback for POST requests without proper Content-Type
        else:
            logger.warning(f"POST request without recognized Content-Type: {content_type}")
            # Try to parse as JSON anyway
            try:
                body = event.get('body', '{}')
                if event.get('isBase64Encoded'):
                    body = base64.b64decode(body).decode('utf-8')
                request_data = json.loads(body)
                action = request_data.get('action')
                
                if action == 'submitInterviewResponses':
                    generate_config_unified = lazy_import('interface_lambda.actions', 'generate_config_unified')
                    return generate_config_unified.handle_generate_config_sync(request_data, context)
                elif action == 'modifyConfig':
                    generate_config_unified = lazy_import('interface_lambda.actions', 'generate_config_unified')
                    return generate_config_unified.handle_modify_config(request_data, context)
                else:
                    logger.warning(f"Unknown action in fallback: {action}")
                    return create_response(400, {'error': f'Unknown or unsupported action: {action}'})
            except Exception as e:
                logger.error(f"Failed to parse POST body as JSON: {e}")
                return create_response(400, {'error': 'Invalid request format'})
    
    # Fallback for unsupported methods
    logger.warning(f"Unsupported HTTP method: {event.get('httpMethod')}")
    return create_response(405, {'error': 'Method Not Allowed'}) 