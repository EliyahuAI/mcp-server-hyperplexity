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

# Configure logging
logging.basicConfig(level=logging.INFO,
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
        "test_mode": False,  # Set to False for production use
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
            logger.error(f"Error converting payload to JSON: {str(e)}")
            # Save the problematic payload for debugging
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
                        
                        # Map results to the original row keys using the results dictionary
                        processed_results = {}
                        
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
                                # If no match found, use the result key as is
                                processed_results[result_key] = cleaned_result
                                logger.info(f"No matching original key found for result key: {result_key}")
                        
                        # Add raw responses to each result for detailed view
                        if 'raw_responses' in body:
                            for key in processed_results:
                                processed_results[key]['_raw_responses'] = body['raw_responses']
                        
                        return processed_results
                    else:
                        logger.warning(f"validation_results is not a dictionary")
                else:
                    logger.warning("No validation_results found in response body")
                
                return {}
                
            except Exception as e:
                logger.error(f"Error parsing response body: {str(e)}")
                import traceback
                traceback.print_exc()
                return {}
        else:
            # For old-format responses (unlikely)
            logger.warning("Response is not in API Gateway format, cannot process")
            return {}
        
    except Exception as e:
        logger.error(f"Error processing Lambda response: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}

def match_key_to_original(result_key, original_keys):
    """Match a result key to one of the original row keys."""
    # Try direct match first
    if result_key in original_keys:
        return result_key
    
    # Try normalized matching
    result_key_norm = normalize_column_name(result_key)
    for orig_key in original_keys:
        orig_key_norm = normalize_column_name(orig_key)
        if result_key_norm == orig_key_norm:
            return orig_key
    
    # Try partial matching
    for orig_key in original_keys:
        # Split both keys by separators and check if parts match
        result_parts = result_key.split("||") if "||" in result_key else result_key.split("|")
        orig_parts = orig_key.split("||") if "||" in orig_key else orig_key.split("|")
        
        # If number of parts matches and most parts match
        if len(result_parts) == len(orig_parts):
            match_count = sum(1 for r, o in zip(result_parts, orig_parts) 
                             if normalize_column_name(r) == normalize_column_name(o) or 
                                normalize_column_name(r) in normalize_column_name(o) or
                                normalize_column_name(o) in normalize_column_name(r))
            if match_count >= max(2, len(result_parts) * 2 // 3):  # At least 2/3 of parts match
                return orig_key
    
    # No match found
    return None

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
        
        # Save payload for debugging (optional)
        debug_file = f"batch_{batch_num+1}_payload.json"
        with open(debug_file, "w") as f:
            json.dump(payload, f, indent=2)
        
        # Invoke Lambda function
        try:
            response = invoke_lambda(payload)
            
            # Save the raw response for debugging (optional)
            debug_response = f"batch_{batch_num+1}_response.json"
            with open(debug_response, "w") as f:
                json.dump(response, f, indent=2)
            
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
        from lambda_test_json_clean import save_results_to_excel as excel_saver
        return excel_saver(df, results_dict, output_path, config)
    except ImportError:
        logger.error("Could not import save_results_to_excel from lambda_test_json_clean.py")
        logger.error("Falling back to basic Excel saving")
        
        # Basic Excel saving if the import fails
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not output_path:
            output_path = f"validation_results_{timestamp}.xlsx"
        
        # Use pandas ExcelWriter
        writer = pd.ExcelWriter(output_path, engine='xlsxwriter')
        df.to_excel(writer, index=False)
        writer.close()
        logger.info(f"Results saved to {output_path} (basic format)")
        return output_path

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