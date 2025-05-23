#!/usr/bin/env python3
"""
Excel Batch Processor for Lambda Validation

This script processes Excel files in batches through the Lambda validation function.
It supports parallel processing by sending multiple rows at once to the Lambda function.
"""

import os
import sys
import json
import logging
import argparse
import pandas as pd
import boto3
import time
from datetime import datetime
from pathlib import Path
import re

# Configure logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Lambda function ARN
LAMBDA_ARN = "arn:aws:lambda:us-east-1:400232868802:function:perplexity-validator"

def normalize_column_name(col):
    """Normalize column name for comprehensive matching across different formats."""
    if col is None:
        return ""
    
    # Convert to lowercase
    norm = str(col).lower()
    
    # Replace non-breaking space with regular space
    norm = norm.replace('\xa0', ' ')
    
    # Replace other special characters and Unicode variants
    norm = norm.replace('\u2011', '-')  # Non-breaking hyphen
    norm = norm.replace('\u2012', '-')  # Figure dash
    norm = norm.replace('\u2013', '-')  # En dash
    norm = norm.replace('\u2014', '-')  # Em dash
    norm = norm.replace('\u2015', '-')  # Horizontal bar
    norm = norm.replace('\u2018', "'")  # Left single quote
    norm = norm.replace('\u2019', "'")  # Right single quote
    norm = norm.replace('\u201c', '"')  # Left double quote
    norm = norm.replace('\u201d', '"')  # Right double quote
    
    # Remove all separators and punctuation for clean comparison
    norm = norm.replace(" ", "").replace("-", "").replace("_", "")
    norm = norm.replace("/", "").replace("\\", "").replace(".", "")
    norm = norm.replace("(", "").replace(")", "").replace(",", "")
    norm = norm.replace(":", "").replace(";", "").replace("&", "")
    
    return norm

def load_excel_data(excel_path, sheet_name=0):
    """Load data from Excel file into a DataFrame with robust column handling."""
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        logger.info(f"Loaded Excel file with {len(df)} rows and {len(df.columns)} columns")
        
        # Identify columns with non-breaking spaces
        nonbreaking_space_cols = [col for col in df.columns if '\xa0' in str(col)]
        if nonbreaking_space_cols:
            logger.info(f"Found {len(nonbreaking_space_cols)} columns with non-breaking spaces")
            
            # Create a mapping for column renaming
            column_mapping = {}
            for col in nonbreaking_space_cols:
                new_col = col.replace('\xa0', ' ')
                column_mapping[col] = new_col
            
            # Rename columns with non-breaking spaces
            df = df.rename(columns=column_mapping)
            logger.info(f"Renamed columns with non-breaking spaces")
        
        # Remove duplicate columns (keep first occurrence)
        df = df.loc[:, ~df.columns.duplicated()]
        
        # Remove unnamed columns
        df = df.loc[:, [col for col in df.columns if str(col).strip() and not str(col).startswith('Unnamed')]]
        
        logger.info(f"Cleaned DataFrame now has {len(df.columns)} columns")
        return df
    except Exception as e:
        logger.error(f"Error loading Excel file: {str(e)}")
        raise

def load_config_file(config_path):
    """Load configuration from JSON file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info(f"Loaded configuration with {len(config.get('validation_targets', []))} validation targets")
        return config
    except Exception as e:
        logger.error(f"Error loading config file: {str(e)}")
        raise

def create_batch_payload(rows_data, config, row_keys):
    """Create a payload for the Lambda function with multiple rows."""
    payload = {
        "test_mode": True,  # Set to True for better debugging 
        "config": config,
        "validation_data": {
            "rows": rows_data
        }
    }
    
    # Clean payload to remove any NaN values
    def clean_dict(d):
        if isinstance(d, dict):
            return {k: clean_dict(v) for k, v in d.items() if not (isinstance(v, float) and pd.isna(v))}
        elif isinstance(d, list):
            return [clean_dict(v) for v in d if not (isinstance(v, float) and pd.isna(v))]
        elif isinstance(d, float) and pd.isna(d):
            return None
        else:
            return d
    
    cleaned_payload = clean_dict(payload)
    
    return cleaned_payload

def invoke_lambda(payload):
    """Invoke Lambda function with the given payload."""
    try:
        # Create Lambda client
        lambda_client = boto3.client('lambda', region_name='us-east-1')
        
        # Convert to JSON, then parse to validate
        try:
            payload_json = json.dumps(payload)
            # Test parse to validate
            json.loads(payload_json)
        except Exception as e:
            # Log the problematic payload but don't write to file unless in debug mode
            logger.error(f"Error converting payload to JSON: {str(e)}")
            if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                with open("error_payload.json", "w") as f:
                    # Use built-in str to avoid JSON errors
                    f.write(str(payload))
            raise
        
        # Invoke Lambda function
        logger.info(f"Invoking Lambda function with {len(payload['validation_data']['rows'])} rows...")
        response = lambda_client.invoke(
            FunctionName=LAMBDA_ARN,
            InvocationType='RequestResponse',
            Payload=payload_json
        )
        
        # Parse response
        response_payload = json.loads(response['Payload'].read().decode())
        logger.info(f"Lambda function response status: {response['StatusCode']}")
        
        return response_payload
    except Exception as e:
        logger.error(f"Error invoking Lambda function: {str(e)}")
        raise

def process_lambda_response(response, row_keys):
    """Process Lambda function response for multiple rows."""
    try:
        # Check if response is valid
        if not response or not isinstance(response, dict):
            logger.error(f"Invalid Lambda response format")
            return {}
        
        # Check for Lambda API Gateway format (statusCode/body)
        if 'statusCode' in response and 'body' in response:
            logger.info(f"Response has API Gateway format, statusCode: {response['statusCode']}")
            
            # Check if the status code indicates success
            if response['statusCode'] != 200:
                logger.error(f"Lambda returned error status: {response['statusCode']}")
                if isinstance(response['body'], dict) and 'error' in response['body']:
                    logger.error(f"Error message: {response['body']['error']}")
                return {}
            
            # Try to parse the body
            try:
                # If body is a string (JSON), parse it
                if isinstance(response['body'], str):
                    body = json.loads(response['body'])
                else:
                    body = response['body']
                
                logger.info(f"Parsed response body with keys: {list(body.keys())}")
                
                # Process validation results
                if 'validation_results' in body:
                    validation_results = body['validation_results']
                    
                    if isinstance(validation_results, dict):
                        logger.info(f"Received validation results for {len(validation_results)} rows")
                        
                        # Debug print all result keys
                        result_keys = list(validation_results.keys())
                        logger.info(f"Result keys from Lambda: {result_keys}")
                        logger.info(f"Original row keys: {row_keys}")
                        
                        # Map results to the original row keys using the results dictionary
                        processed_results = {}
                        
                        # Special case: Check if all result keys are numeric (0, 1, 2, ...)
                        # This happens when the Lambda returns results with numeric indices
                        numeric_keys = all(k.isdigit() for k in result_keys if isinstance(k, str))
                        
                        if numeric_keys and len(result_keys) == len(row_keys):
                            logger.info("Detected numeric keys - using position-based mapping")
                            # Map results based on position/index
                            for i, (result_key, row_key) in enumerate(zip(sorted(result_keys), row_keys)):
                                # Get the result data and clean column names
                                result_data = validation_results[result_key]
                                cleaned_result = {}
                                for col, value in result_data.items():
                                    # Replace non-breaking spaces with regular spaces
                                    if isinstance(col, str) and '\xa0' in col:
                                        cleaned_col = col.replace('\xa0', ' ')
                                        cleaned_result[cleaned_col] = value
                                    else:
                                        cleaned_result[col] = value
                                
                                # Store with original row key
                                processed_results[row_key] = cleaned_result
                                logger.info(f"Mapped result key {result_key} to row key {row_key} by position")
                        else:
                            # Standard matching approach
                            # Match results to the original row keys
                            for result_key, result_data in validation_results.items():
                                # Clean the column names in results
                                cleaned_result = {}
                                for col, value in result_data.items():
                                    # Replace non-breaking spaces with regular spaces
                                    if isinstance(col, str) and '\xa0' in col:
                                        cleaned_col = col.replace('\xa0', ' ')
                                        cleaned_result[cleaned_col] = value
                                    else:
                                        cleaned_result[col] = value
                                
                                # Try to match with an original row key
                                matched_key = match_key_to_original(result_key, row_keys)
                                if matched_key:
                                    processed_results[matched_key] = cleaned_result
                                    logger.info(f"Matched result key: {result_key} to original key: {matched_key}")
                                else:
                                    # If no match found, use the result key as is - this is important!
                                    processed_results[result_key] = cleaned_result
                                    logger.info(f"No matching original key found for result key: {result_key}")
                        
                        # Add raw responses to each result for detailed view
                        if 'raw_responses' in body:
                            for key in processed_results:
                                processed_results[key]['_raw_responses'] = body['raw_responses']
                        
                        # Check if the processed results dictionary is empty despite having validation results
                        if not processed_results and validation_results:
                            logger.warning("No results were matched to original rows - using Lambda results directly")
                            # Fall back to using the original validation results with their keys
                            for result_key, result_data in validation_results.items():
                                # Just use the unmodified result
                                processed_results[result_key] = result_data
                        
                        logger.info(f"Final processed results contain {len(processed_results)} rows")
                        return processed_results
                    else:
                        logger.warning(f"validation_results is not a dictionary")
                else:
                    logger.warning("No validation_results found in response body")
                
                # If there is 'data' in the response, this could be the debug/converted format
                if 'data' in body:
                    logger.info("Found 'data' field in response - trying to extract results")
                    processed_results = {}
                    data = body['data']
                    
                    for data_key, data_value in data.items():
                        if 'validation_results' in data_value:
                            results = data_value['validation_results']
                            # Try to match with original row keys
                            matched_key = match_key_to_original(data_key, row_keys)
                            if matched_key:
                                processed_results[matched_key] = results
                                logger.info(f"Matched data key: {data_key} to original key: {matched_key}")
                            else:
                                # If no match found, use the data key as is
                                processed_results[data_key] = results
                                logger.info(f"No matching original key found for data key: {data_key}")
                    
                    if processed_results:
                        logger.info(f"Extracted {len(processed_results)} results from data field")
                        return processed_results
                
                # Special handling for debug format
                if 'debug' in body:
                    logger.info("Found 'debug' field in response - extracting results")
                    debug_data = body['debug']
                    if isinstance(debug_data, dict) and 'results' in debug_data:
                        return debug_data['results']
                
                return {}
                
            except Exception as e:
                logger.error(f"Error parsing response body: {str(e)}")
                import traceback
                traceback.print_exc()
                
                # Last resort - try to extract anything useful from the response
                try:
                    if isinstance(response['body'], str):
                        # Only save the response body during debugging/errors
                        logger.info("Trying to parse response body as JSON")
                        
                        # Try a more permissive JSON parse
                        import json5
                        body = json5.loads(response['body'])
                        if 'validation_results' in body:
                            return {'debug_fallback': body['validation_results']}
                except:
                    pass
                    
                return {}
        else:
            # For old-format responses (unlikely)
            logger.warning("Response is not in API Gateway format, cannot process")
            # Log but don't write to file
            logger.debug(f"Raw non-gateway response: {json.dumps(response)[:500]}...")
            return {}
        
    except Exception as e:
        logger.error(f"Error processing Lambda response: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}

def match_key_to_original(result_key, original_keys):
    """Match a result key to one of the original row keys."""
    logger.debug(f"Attempting to match result key: {result_key}")
    
    # Try direct match first
    if result_key in original_keys:
        logger.debug(f"Direct match found for {result_key}")
        return result_key
    
    # Try normalized matching
    result_key_norm = normalize_column_name(result_key)
    for orig_key in original_keys:
        orig_key_norm = normalize_column_name(orig_key)
        if result_key_norm == orig_key_norm:
            logger.debug(f"Normalized match found: {result_key} -> {orig_key}")
            return orig_key
    
    # Try partial matching by splitting on separators
    for orig_key in original_keys:
        # Split both keys by common separators and check if parts match
        result_parts = re.split(r'[|_\-\s]+', result_key)
        orig_parts = re.split(r'[|_\-\s]+', orig_key)
        
        # Check how many parts match between the keys
        common_parts = 0
        for r_part in result_parts:
            if not r_part.strip():
                continue
            r_norm = normalize_column_name(r_part)
            for o_part in orig_parts:
                if not o_part.strip():
                    continue
                o_norm = normalize_column_name(o_part)
                if r_norm == o_norm or r_norm in o_norm or o_norm in r_norm:
                    common_parts += 1
                    break
        
        # If sufficient parts match, consider it a match
        # Require at least 2 matching parts or >50% of parts to match
        min_match = max(2, min(len(result_parts), len(orig_parts)) * 0.5)
        if common_parts >= min_match:
            logger.debug(f"Partial match: {result_key} -> {orig_key} ({common_parts} common parts)")
            return orig_key
    
    # Try content-based matching - look for matching words and numbers
    for orig_key in original_keys:
        # Extract significant content (words, numbers, codes)
        result_content = extract_significant_content(result_key)
        orig_content = extract_significant_content(orig_key)
        
        # Check for overlap in content
        common_content = set(result_content).intersection(set(orig_content))
        if common_content and len(common_content) >= 2:  # At least 2 common elements
            logger.debug(f"Content match: {result_key} -> {orig_key} (common: {common_content})")
            return orig_key
    
    # As a last resort, try positional matching if original_keys is ordered
    if len(original_keys) > 0:
        try:
            # If the number of results matches the number of original keys,
            # assume they're in the same order
            result_keys_seen = []
            if len(result_keys_seen) == len(original_keys):
                idx = result_keys_seen.index(result_key)
                if idx < len(original_keys):
                    logger.debug(f"Positional match: {result_key} -> {original_keys[idx]}")
                    return original_keys[idx]
        except (ValueError, IndexError):
            pass
    
    # No match found
    logger.debug(f"No match found for {result_key}")
    return None

def extract_significant_content(key):
    """Extract significant content from a key string - generic version."""
    if not key:
        return []
    
    content = []
    # Extract all alphanumeric words (3+ chars)
    words = re.findall(r'[A-Za-z0-9]{3,}', key)
    content.extend(words)
    
    # Extract numbers
    numbers = re.findall(r'\d+', key)
    content.extend(numbers)
    
    # Extract codes/identifiers (patterns with letters and numbers)
    codes = re.findall(r'[A-Za-z]+[0-9]+|[0-9]+[A-Za-z]+', key)
    content.extend(codes)
    
    return content

def generate_row_key(row, primary_keys):
    """Generate a unique key for a row based on primary key columns."""
    key_parts = []
    for key in primary_keys:
        # Try to match the key to a column in the row using normalization
        matched_key = None
        if key in row:
            matched_key = key
        else:
            # Try to find a normalized match
            key_norm = normalize_column_name(key)
            for col in row.keys():
                if normalize_column_name(col) == key_norm:
                    matched_key = col
                    break
        
        if matched_key:
            # Convert to string and handle None/NaN values
            value = row[matched_key]
            if pd.isna(value) or value is None:
                value = "NULL"
            else:
                value = str(value)
                # Keep alphanumeric, spaces, and some basic punctuation
                value = ''.join(c for c in value if c.isalnum() or c in ' -_')
            key_parts.append(value)
        else:
            key_parts.append("MISSING")
    
    # Join key parts with a separator
    row_key = "||".join(key_parts)
    return row_key

def process_in_batches(df, config, batch_size, output_path, api_key=None):
    """Process DataFrame in batches through the Lambda function."""
    total_rows = len(df)
    total_batches = (total_rows + batch_size - 1) // batch_size  # Ceiling division
    all_results = {}
    primary_keys = config.get('primary_key', [])
    
    logger.info(f"Processing {total_rows} rows in {total_batches} batches of size {batch_size}")
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, total_rows)
        batch_df = df.iloc[start_idx:end_idx]
        
        logger.info(f"Processing batch {batch_num+1}/{total_batches}, rows {start_idx+1}-{end_idx}")
        
        # Prepare rows data and row keys
        rows_data = []
        row_keys = []
        
        for _, row in batch_df.iterrows():
            # Clean row data
            row_data = {}
            for col, val in row.to_dict().items():
                # Skip NaN values
                if not (isinstance(val, float) and pd.isna(val)):
                    # Convert non-string values to strings
                    if not pd.isna(val) and val is not None:
                        row_data[col] = str(val)
                    else:
                        row_data[col] = None
            
            # Generate row key
            row_key = generate_row_key(row_data, primary_keys)
            
            # Add to batches
            rows_data.append(row_data)
            row_keys.append(row_key)
        
        # Add API key if provided
        if api_key:
            config['api_key'] = api_key
        
        # Create Lambda payload for the batch
        payload = create_batch_payload(rows_data, config, row_keys)
        
        # Invoke Lambda function
        try:
            response = invoke_lambda(payload)
            
            # Process response
            batch_results = process_lambda_response(response, row_keys)
            if batch_results:
                # Merge into all_results
                all_results.update(batch_results)
                logger.info(f"Added results for batch {batch_num+1}, total results: {len(all_results)}")
            else:
                logger.warning(f"No results obtained for batch {batch_num+1}")
        except Exception as e:
            logger.error(f"Error processing batch {batch_num+1}: {str(e)}")
            import traceback
            traceback.print_exc()
        
        # Add a delay to avoid rate limiting
        if batch_num < total_batches - 1:
            time.sleep(1)
    
    return all_results

def save_results_to_excel(df, results_dict, output_path, config):
    """Save validation results to Excel with robust column handling."""
    try:
        # Try to use the rich formatting from lambda_test_json_clean.py
        try:
            # Log the contents of the results dictionary for debugging
            logger.info(f"Results dictionary contains {len(results_dict)} rows")
            for key in results_dict.keys():
                logger.info(f"Result key: {key[:50]}...")
                
                # Check if the results contain the required fields
                result_data = results_dict[key]
                if isinstance(result_data, dict):
                    logger.info(f"  Fields: {list(result_data.keys())}")
                else:
                    logger.info(f"  Not a dictionary: {type(result_data)}")
            
            # Check if we need to convert the row keys
            # lambda_test_json_clean.py expects integer row indices when the keys are numeric
            # But we have matched them to our original row keys
            convert_keys = False
            for key in results_dict.keys():
                try:
                    int(key)
                    # We have at least one numeric key, don't convert
                    convert_keys = False
                    break
                except (ValueError, TypeError):
                    # We have non-numeric keys, we need to convert
                    convert_keys = True
            
            if convert_keys:
                logger.info("Converting result dictionary keys for lambda_test_json_clean compatibility")
                from lambda_test_json_clean import save_results_to_excel as excel_saver
                
                # Get row indices corresponding to the row keys
                row_indices = {}
                for i, row in enumerate(df.iterrows()):
                    # Get index and row data
                    index, row_data = row
                    
                    # Generate row key from primary keys
                    primary_keys = config.get('primary_key', [])
                    key_parts = []
                    for pk in primary_keys:
                        if pk in row_data:
                            value = row_data[pk]
                            if pd.isna(value):
                                value = "NULL"
                            else:
                                value = str(value)
                            key_parts.append(value)
                        else:
                            key_parts.append("MISSING")
                    
                    row_key = "||".join(key_parts)
                    row_indices[row_key] = str(i)  # Use string index for consistency
                
                # Create a new dictionary with indices as keys
                indexed_results = {}
                for key, value in results_dict.items():
                    if key in row_indices:
                        # Use the row index as the key
                        indexed_results[row_indices[key]] = value
                        logger.info(f"Mapped result key {key} to row index {row_indices[key]}")
                    else:
                        # Couldn't map to a row index, use key as is
                        indexed_results[key] = value
                        logger.info(f"Could not map result key {key} to a row index")
                
                # Use the indexed results with the excel_saver
                logger.info("Using enhanced Excel formatting from lambda_test_json_clean")
                return excel_saver(df, indexed_results, output_path, config)
            else:
                # Keys are already in the expected format for lambda_test_json_clean
                from lambda_test_json_clean import save_results_to_excel as excel_saver
                logger.info("Using enhanced Excel formatting from lambda_test_json_clean (with existing keys)")
                return excel_saver(df, results_dict, output_path, config)
                
        except ImportError as e:
            logger.error(f"Could not import save_results_to_excel: {str(e)}")
            logger.error("Falling back to basic Excel saving")
        except Exception as e:
            logger.error(f"Error using enhanced Excel formatting: {str(e)}")
            import traceback
            traceback.print_exc()
            logger.error("Falling back to basic Excel saving")
        
        # Basic Excel saving if the import fails
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not output_path:
            output_path = f"validation_results_{timestamp}.xlsx"
        
        # Use pandas ExcelWriter
        writer = pd.ExcelWriter(output_path, engine='xlsxwriter')
        
        # Create a copy of the original DataFrame to avoid modifying the input
        result_df = df.copy()
        
        # Save the raw DataFrame
        result_df.to_excel(writer, sheet_name='Raw Data', index=False)
        
        # Add a results sheet if we have results
        if results_dict:
            # Create a results summary sheet
            workbook = writer.book
            results_sheet = workbook.add_worksheet('Results Summary')
            
            # Create formats
            header_format = workbook.add_format({
                'bold': True, 'text_wrap': True, 'valign': 'center',
                'fg_color': '#4472C4', 'font_color': 'white', 'border': 1
            })
            
            # Add headers
            headers = ["Row", "Key", "Columns Validated"]
            for i, header in enumerate(headers):
                results_sheet.write(0, i, header, header_format)
            
            # Set column widths
            results_sheet.set_column(0, 0, 5)
            results_sheet.set_column(1, 1, 50)
            results_sheet.set_column(2, 2, 50)
            
            # Fill with result summary
            row_idx = 1
            for key, result_data in results_dict.items():
                results_sheet.write(row_idx, 0, row_idx)
                results_sheet.write(row_idx, 1, key)
                
                if isinstance(result_data, dict):
                    validated_cols = [col for col in result_data.keys() 
                                    if col not in ['holistic_validation', 'next_check', 'reasons', '_raw_responses']]
                    results_sheet.write(row_idx, 2, ", ".join(validated_cols))
                else:
                    results_sheet.write(row_idx, 2, f"Invalid result type: {type(result_data)}")
                
                row_idx += 1
        
        # Save the workbook
        writer.close()
        logger.info(f"Results saved to {output_path} (basic format)")
        return output_path
    except Exception as e:
        logger.error(f"Error saving results to Excel: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Last resort - save results as JSON for manual inspection
        try:
            json_path = f"{os.path.splitext(output_path)[0]}_results.json"
            with open(json_path, 'w') as f:
                json.dump(results_dict, f, indent=2, default=str)
            logger.info(f"Results saved as JSON to {json_path}")
        except:
            logger.error("Could not save results as JSON")
        
        raise

def main():
    """Main function to process Excel file in batches through Lambda."""
    parser = argparse.ArgumentParser(description="Process Excel file in batches through Lambda validation")
    parser.add_argument("--input", "-i", help="Input Excel file path", required=True)
    parser.add_argument("--config", "-c", help="Configuration JSON file path", required=True)
    parser.add_argument("--output", "-o", help="Output Excel file path")
    parser.add_argument("--batch-size", "-b", type=int, default=10, help="Number of rows per batch (default: 10)")
    parser.add_argument("--max-rows", "-m", type=int, help="Maximum number of rows to process")
    parser.add_argument("--api-key", "-k", help="API key for authentication")
    args = parser.parse_args()
    
    try:
        # Load config from the JSON file
        logger.info(f"Loading configuration from: {args.config}")
        config = load_config_file(args.config)
        
        # Load Excel data
        logger.info(f"Loading data from: {args.input}")
        df = load_excel_data(args.input)
        
        # Limit the number of rows if specified
        if args.max_rows and args.max_rows < len(df):
            df = df.head(args.max_rows)
            logger.info(f"Limited to {len(df)} rows as specified")
        
        # Process in batches
        results_dict = process_in_batches(df, config, args.batch_size, args.output, args.api_key)
        
        # Save results to Excel if we have any
        if results_dict:
            output_path = args.output
            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                input_name = os.path.splitext(os.path.basename(args.input))[0]
                output_path = f"validation_results_{input_name}_{timestamp}.xlsx"
            
            # Import and use the full-featured Excel saving function
            save_results_to_excel(df, results_dict, output_path, config)
            logger.info(f"Results saved to {output_path}")
        else:
            logger.warning("No results to save to Excel")
        
        logger.info("Processing completed successfully")
        return 0
    
    except Exception as e:
        logger.error(f"Error in processing: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main()) 