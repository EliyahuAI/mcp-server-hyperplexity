"""
Handles invoking the core validator Lambda function.
"""
import io
import json
import logging
import os
import tempfile
import time
import openpyxl
import csv
import boto3
import math
from pathlib import Path

from src.shared.row_key_utils import generate_row_key
from src.lambdas.interface.utils.history_loader import load_validation_history_from_excel
from src.shared.schema_validator_simplified import SimplifiedSchemaValidator
from src.lambdas.interface.reporting.markdown_report import create_markdown_table_from_results

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
lambda_client = boto3.client('lambda')

def invoke_validator_lambda(excel_s3_key, config_s3_key, max_rows, batch_size, S3_CACHE_BUCKET, VALIDATOR_LAMBDA_NAME, preview_first_row=False, preview_max_rows=5, sequential_call=None, session_id=None, update_callback=None, special_request=None):
    """Invoke the core validator Lambda with Excel data."""
    
    logger.info(">>> ENTER invoke_validator_lambda <<<")
    logger.info(f">>> Parameters: excel_s3_key={excel_s3_key}, preview={preview_first_row}, sequential_call={sequential_call}, special_request={special_request} <<<")
    
    # Handle special requests (like config generation)
    if special_request:
        logger.info(f"Processing special request: {special_request.get('action', 'unknown')}")
        return _handle_special_request(special_request, excel_s3_key, S3_CACHE_BUCKET, VALIDATOR_LAMBDA_NAME)
    
    try:
        logger.info(f"Starting invoke_validator_lambda - preview_first_row: {preview_first_row}")
        logger.info(f"Excel S3 key: {excel_s3_key}")
        logger.info(f"Config S3 key: {config_s3_key}")
        
        # Download Excel file from S3
        excel_response = s3_client.get_object(Bucket=S3_CACHE_BUCKET, Key=excel_s3_key)
        excel_content = excel_response['Body'].read()
        
        # Download config file from S3
        config_response = s3_client.get_object(Bucket=S3_CACHE_BUCKET, Key=config_s3_key)
        config_data = json.loads(config_response['Body'].read().decode('utf-8'))
        
        # Preprocess config to support both 'column' and 'name' fields
        if 'validation_targets' in config_data and isinstance(config_data['validation_targets'], list):
            for target in config_data['validation_targets']:
                # Ensure both 'column' and 'name' fields exist for compatibility
                if 'column' in target and 'name' not in target:
                    target['name'] = target['column']
                elif 'name' in target and 'column' not in target:
                    target['column'] = target['name']
                # Keep both fields for backward compatibility
        
        # Detect file type and load data accordingly
        # Check if this is a CSV file and convert to Excel format if needed
        original_file_type = "Excel"
        
        # First check if it's a valid Excel file by checking ZIP signature
        if excel_content.startswith(b'PK'):
            # This is likely a ZIP-based file (Excel .xlsx)
            logger.info("Detected Excel file format (ZIP signature)")
            original_file_type = "Excel"
        else:
            # Not a ZIP file, try to process as CSV
            try:
                # Try multiple encodings to handle different CSV file encodings
                encodings_to_try = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'utf-16']
                text_content = None
                used_encoding = None
                
                for encoding in encodings_to_try:
                    try:
                        text_content = excel_content.decode(encoding)
                        used_encoding = encoding
                        break
                    except UnicodeDecodeError:
                        continue
                
                if text_content is None:
                    raise ValueError(f"Could not decode file with any of the tried encodings: {encodings_to_try}")
                    
                logger.info(f"Successfully decoded file using {used_encoding} encoding")
                # Simple heuristic: if it contains commas, treat as CSV
                if ',' in text_content:
                    original_file_type = "CSV"
                    logger.info("Detected CSV file format - converting to Excel")
                    
                    # Parse CSV content
                    csv_reader = csv.reader(io.StringIO(text_content))
                    csv_rows = list(csv_reader)
                    
                    if not csv_rows:
                        raise ValueError("CSV file is empty")
                    
                    # Convert CSV to Excel format in memory
                    workbook = openpyxl.Workbook()
                    worksheet = workbook.active
                    worksheet.title = "Data"
                    
                    # Write CSV data to Excel worksheet
                    for row_idx, csv_row in enumerate(csv_rows, 1):
                        for col_idx, cell_value in enumerate(csv_row, 1):
                            worksheet.cell(row=row_idx, column=col_idx, value=cell_value)
                    
                    # Save Excel workbook to bytes
                    excel_buffer = io.BytesIO()
                    workbook.save(excel_buffer)
                    excel_content = excel_buffer.getvalue()
                    excel_buffer.close()
                    
                    logger.info(f"Converted CSV with {len(csv_rows)} rows to Excel format")
                else:
                    # Can decode as UTF-8 but no commas - might be old Excel format or other file
                    logger.error(f"File doesn't appear to be CSV or Excel format. Content starts with: {text_content[:100]}...")
                    raise ValueError("File format not supported - must be Excel (.xlsx) or CSV")
            except UnicodeDecodeError:
                # Can't decode as UTF-8 and not a ZIP file - unsupported format
                logger.error("File is binary but not a valid Excel file (no ZIP signature)")
                logger.error(f"File starts with bytes: {excel_content[:20]}")
                raise ValueError("File format not supported - file appears to be binary but not a valid Excel file")
        
        # Now process as Excel file (whether original or converted from CSV)
        logger.info(f"Processing {original_file_type} file as Excel format")
        workbook = openpyxl.load_workbook(io.BytesIO(excel_content))
        
        # Log available sheet names
        logger.info(f"Available sheets in Excel: {workbook.sheetnames}")
        
        # Select the appropriate sheet
        if 'Results' in workbook.sheetnames:
            worksheet = workbook['Results']
            logger.info(f"Using 'Results' sheet as data source")
        elif len(workbook.sheetnames) > 0:
            worksheet = workbook[workbook.sheetnames[0]]
            logger.info(f"Using first sheet '{worksheet.title}' as data source")
        else:
            worksheet = workbook.active
            logger.info(f"Using active sheet: {worksheet.title}")
        
        # Read headers from first row
        headers = []
        for cell in worksheet[1]:
            header = cell.value
            if header:
                headers.append(str(header).strip())
            else:
                headers.append('')
        
        logger.info(f"Headers found: {headers}")
        logger.info(f"Total columns: {len(headers)}")
        
        # Process data rows
        rows = []
        total_rows = worksheet.max_row - 1  # Exclude header
        
        # Limit rows for preview mode or max_rows
        if preview_first_row:
            # For preview mode, we want to load all rows up to preview_max_rows
            # so the validator can process them sequentially and use caching
            max_process_rows = min(preview_max_rows, total_rows)
        else:
            max_process_rows = min(max_rows, total_rows) if max_rows else total_rows
        
        logger.info(f"Processing {max_process_rows} rows from {original_file_type} (total available: {total_rows})")
        
        # Get ID fields from config for row key generation
        id_fields = []
        logger.info("Searching for ID fields in validation targets...")
        for i, target in enumerate(config_data.get('validation_targets', [])):
            importance = target.get('importance', '')
            logger.info(f"Target {i}: importance='{importance}', column='{target.get('column')}', name='{target.get('name')}'")
            if importance.upper() == 'ID':
                # Support both 'name' and 'column' fields
                field_name = target.get('name') or target.get('column')
                if field_name:
                    id_fields.append(field_name)
                    logger.info(f"Found ID field: {field_name}")
                else:
                    logger.warning(f"ID target found but no field name: {target}")
            else:
                logger.debug(f"Target '{target.get('column')}' has importance '{importance}' (not ID)")
        
        # If no ID fields found, try to use SimplifiedSchemaValidator to determine primary keys
        if not id_fields:
            try:
                validator = SimplifiedSchemaValidator(config_data)
                id_fields = validator.primary_key
                logger.info(f"Using primary keys from SimplifiedSchemaValidator: {id_fields}")
            except ImportError:
                logger.warning("SimplifiedSchemaValidator not available in deployment package")
            except Exception as e:
                logger.warning(f"Could not use SimplifiedSchemaValidator: {e}")
        
        logger.info(f"ID fields for row key generation: {id_fields}")
        
        # Process data rows using Excel format (works for both original Excel and converted CSV)
        for row_idx in range(2, min(2 + max_process_rows, worksheet.max_row + 1)):
            row_data = {}
            
            # Extract cell values
            for col_idx, header in enumerate(headers):
                if header:  # Skip empty headers
                    cell_value = worksheet.cell(row=row_idx, column=col_idx + 1).value
                    row_data[header] = str(cell_value) if cell_value is not None else ""
            
            # Debug: Log first row's data to see what we're getting
            if row_idx == 2:  # First data row
                logger.info(f"First row data extracted: {json.dumps(row_data)}")
                logger.info(f"Looking for ID fields: {id_fields}")
                for id_field in id_fields:
                    logger.info(f"  {id_field}: '{row_data.get(id_field, 'NOT FOUND')}'")
            
            # Generate row key
            row_key = generate_row_key(row_data, id_fields)
            logger.debug(f"Generated row key: {row_key}")
            
            row_data['_row_key'] = row_key
            rows.append(row_data)
        
        # Show sample row data to understand what keys will be generated
        if rows and len(rows) > 0:
            sample_row = rows[0]
            logger.info("Sample row data for first row:")
            for id_field in id_fields:
                value = sample_row.get(id_field, 'NOT FOUND')
                logger.info(f"  {id_field}: {value}")
        
        # Load validation history if available and we have Excel content
        validation_history = {}
        if not preview_first_row:  # Load validation history for all files (now all are Excel format)
            try:
                # Save Excel content to a temporary file for history extraction
                with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
                    tmp_file.write(excel_content)
                    tmp_file_path = tmp_file.name
                
                original_validation_history = load_validation_history_from_excel(tmp_file_path)
                
                logger.info(f"Loaded validation history for {len(original_validation_history)} row keys from Excel")
                
                if original_validation_history:
                    validation_history = original_validation_history
                    
                    # Log matching summary
                    matched_count = 0
                    for row in rows:
                        payload_key = row.get('_row_key', '')
                        if payload_key and payload_key in validation_history:
                            matched_count += 1
                    
                    logger.info(f"Matched {matched_count} out of {len(rows)} rows with validation history")
                    
                    if matched_count == 0 and len(validation_history) > 0:
                        logger.warning("No rows matched with validation history - may be using different primary keys")
                        logger.info(f"Current primary keys: {id_fields}")
                
                # Clean up temp file
                os.unlink(tmp_file_path)
                
            except Exception as e:
                logger.warning(f"Could not load validation history: {e}")
                import traceback
                traceback.print_exc()
                validation_history = {}
        
        # Initialize aggregated metadata
        aggregated_metadata = {
            'total_rows': total_rows,
            'token_usage': {
                'total_tokens': 0, 'total_cost': 0.0, 'api_calls': 0, 'cached_calls': 0,
                'by_provider': {
                    'perplexity': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'calls': 0, 'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0},
                    'anthropic': {'input_tokens': 0, 'output_tokens': 0, 'cache_creation_tokens': 0, 'cache_read_tokens': 0, 'total_tokens': 0, 'calls': 0, 'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0}
                },
                'by_model': {}
            }
        }
        
        if preview_first_row:
            total_rows_to_send = min(sequential_call, preview_max_rows, len(rows)) if sequential_call else min(preview_max_rows, len(rows))
            logger.info(f"Preview mode: sending {total_rows_to_send} rows to validator")
            
            preview_rows = rows[:total_rows_to_send]
            
            payload = {
                "test_mode": True, "config": config_data,
                "validation_data": {"rows": preview_rows}, "validation_history": {}
            }
            
            try:
                validation_start_time = time.time()
                response = lambda_client.invoke(
                    FunctionName=VALIDATOR_LAMBDA_NAME, InvocationType='RequestResponse', Payload=json.dumps(payload)
                )
                validation_processing_time = time.time() - validation_start_time
                logger.info(f"Validator Lambda processing took {validation_processing_time:.2f} seconds")
                
                response_payload = json.loads(response['Payload'].read().decode('utf-8'))
                
                validation_results, metadata = None, None
                if isinstance(response_payload, dict):
                    body = response_payload.get('body', {})
                    if isinstance(body, dict):
                        validation_results = body.get('data', {}).get('rows')
                        metadata = body.get('metadata', {})
                    if 'validation_results' in response_payload:
                        validation_results = response_payload['validation_results']

                if metadata:
                    aggregated_metadata.update(metadata)

                new_row_processed = None
                if validation_results:
                    for row_key in sorted(validation_results.keys(), key=lambda x: int(x) if x.isdigit() else -1, reverse=True):
                        row_data = validation_results[row_key]
                        if isinstance(row_data, dict) and '_raw_responses' in row_data:
                            if any(not r.get('is_cached', True) for r in row_data['_raw_responses'].values()):
                                new_row_processed = int(row_key) + 1
                                break
                
                preview_complete = (new_row_processed is None or new_row_processed >= preview_max_rows or new_row_processed >= len(rows))
                
                result_response = {
                    'total_rows': total_rows, 'validation_results': validation_results, 'metadata': aggregated_metadata,
                    'total_processed_rows': len(validation_results) if validation_results else 0,
                    'new_row_number': new_row_processed, 'preview_complete': preview_complete
                }
                if isinstance(response_payload, dict):
                    result_response.update(response_payload)
                return result_response
                
            except Exception as e:
                logger.warning(f"Validator Lambda timeout or error in preview mode: {str(e)}")
                return {'status': 'timeout', 'total_rows': total_rows, 'validation_results': None, 'metadata': aggregated_metadata, 'note': f'Validation timed out (>25s), using demo data. Error: {str(e)}'}
        else:
            # For normal mode, process in batches
            all_validation_results = {}
            # Use the passed batch_size, defaulting to 10 if it's None or invalid
            effective_batch_size = batch_size if batch_size and batch_size > 0 else 10
            total_batches = (len(rows) + effective_batch_size - 1) // effective_batch_size
            
            logger.info(f"Processing {len(rows)} rows in {total_batches} batches of size {effective_batch_size}")
            
            if update_callback:
                update_callback(session_id, "PROCESSING", 0, f"Starting processing of {len(rows)} rows in {total_batches} batches.", 0, None, 0, total_batches)

            for batch_num in range(total_batches):
                start_idx = batch_num * effective_batch_size
                end_idx = min(start_idx + effective_batch_size, len(rows))
                batch_rows = rows[start_idx:end_idx]
                current_batch = batch_num + 1
                
                logger.info(f"Processing batch {current_batch}/{total_batches}, rows {start_idx+1}-{end_idx}")
                
                batch_payload = {"test_mode": False, "config": config_data, "validation_data": {"rows": batch_rows}, "validation_history": validation_history}
                
                try:
                    response = lambda_client.invoke(FunctionName=VALIDATOR_LAMBDA_NAME, InvocationType='RequestResponse', Payload=json.dumps(batch_payload))
                    response_payload = json.loads(response['Payload'].read().decode('utf-8'))
                    
                    batch_validation_results, batch_metadata = None, None
                    if isinstance(response_payload, dict):
                        body = response_payload.get('body', {})
                        if isinstance(body, dict):
                           batch_validation_results = body.get('data', {}).get('rows')
                           batch_metadata = body.get('metadata', {})
                        if 'validation_results' in response_payload:
                           batch_validation_results = response_payload['validation_results']

                    if batch_metadata and 'token_usage' in batch_metadata:
                        batch_token_usage = batch_metadata['token_usage']
                        agg_token_usage = aggregated_metadata['token_usage']
                        agg_token_usage['total_tokens'] += batch_token_usage.get('total_tokens', 0)
                        agg_token_usage['total_cost'] += batch_token_usage.get('total_cost', 0.0)
                        agg_token_usage['api_calls'] += batch_token_usage.get('api_calls', 0)
                        agg_token_usage['cached_calls'] += batch_token_usage.get('cached_calls', 0)
                        
                        if 'by_provider' in batch_token_usage:
                            for provider, data in batch_token_usage['by_provider'].items():
                                for key, val in data.items():
                                    if isinstance(val, (int, float)):
                                        agg_token_usage['by_provider'].setdefault(provider, {})[key] = agg_token_usage['by_provider'].setdefault(provider, {}).get(key, 0) + val
                        
                        if 'by_model' in batch_token_usage:
                            for model, data in batch_token_usage['by_model'].items():
                                if model not in agg_token_usage['by_model']: agg_token_usage['by_model'][model] = {}
                                for key, val in data.items():
                                     if isinstance(val, (int, float)):
                                         agg_token_usage['by_model'][model][key] = agg_token_usage['by_model'][model].get(key, 0) + val
                                     else:
                                         agg_token_usage['by_model'][model][key] = val

                    if batch_validation_results:
                        for batch_key, batch_result in batch_validation_results.items():
                            if batch_key.isdigit():
                                all_validation_results[str(start_idx + int(batch_key))] = batch_result
                            else:
                                all_validation_results[batch_key] = batch_result
                    
                except Exception as e:
                    logger.error(f"Error processing batch {batch_num+1}: {str(e)}")
                
                if batch_num < total_batches - 1:
                    time.sleep(0.5)
                
                # After processing a batch, call the update_callback
                if update_callback:
                    processed_rows_count = end_idx
                    percent_complete = int((processed_rows_count / len(rows)) * 100)
                    verbose_status = f"Processing batch {current_batch} of {total_batches}..."
                    # Pass batch information as additional parameters
                    update_callback(session_id, "PROCESSING", processed_rows_count, verbose_status, percent_complete, None, current_batch, total_batches)

            logger.info(f"Completed processing all batches. Total results: {len(all_validation_results)}")
            return {'total_rows': total_rows, 'validation_results': all_validation_results, 'metadata': aggregated_metadata, 'status': 'completed'}
            
    except Exception as e:
        logger.error(f"Error invoking validator Lambda: {str(e)}")
        import traceback
        traceback.print_exc()
        raise 


def _handle_special_request(special_request, excel_s3_key, S3_CACHE_BUCKET, VALIDATOR_LAMBDA_NAME):
    """Handle special requests like config generation that use the validation lambda's Claude integration"""
    
    action = special_request.get('action')
    
    if action == 'generate_config':
        logger.info("Handling config generation request")
        
        try:
            # Build config generation payload for validation lambda
            payload = {
                "config_generation_request": True,
                "table_analysis": special_request.get('table_analysis'),
                "generation_mode": special_request.get('generation_mode', 'automatic'),
                "conversation_id": special_request.get('conversation_id'),
                "user_message": special_request.get('user_message', ''),
                "session_id": special_request.get('session_id'),
                "excel_s3_key": excel_s3_key,
                "s3_cache_bucket": S3_CACHE_BUCKET
            }
            
            logger.info(f"Calling validation lambda for config generation with session_id: {special_request.get('session_id')}")
            
            # Call validation lambda
            response = lambda_client.invoke(
                FunctionName=VALIDATOR_LAMBDA_NAME,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            response_payload = json.loads(response['Payload'].read().decode('utf-8'))
            logger.info(f"Config generation response received from validation lambda")
            
            # Extract the result from validation lambda response
            if isinstance(response_payload, dict):
                body = response_payload.get('body', {})
                if isinstance(body, dict):
                    return body
                else:
                    # Direct response format
                    return response_payload
            
            return response_payload
            
        except Exception as e:
            logger.error(f"Error in config generation request: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': f'Config generation failed: {str(e)}'
            }
    
    else:
        logger.error(f"Unknown special request action: {action}")
        return {
            'success': False,
            'error': f'Unknown special request action: {action}'
        }