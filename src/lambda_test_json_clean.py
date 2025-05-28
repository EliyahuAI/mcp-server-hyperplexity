#!/usr/bin/env python3
"""
Clean Lambda test script for Excel validation with robust column handling.
Tests rows in datasets against the Lambda validation function and formats results in Excel.
"""

import os
import sys
import json
import logging
import pandas as pd
import boto3
import time
import re
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import botocore.config
import math
import xlsxwriter

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
    norm = norm.replace('\u00b0', '')   # Degree symbol
    norm = norm.replace('\u00b1', '')   # Plus-minus symbol
    norm = norm.replace('\u00b5', 'u')  # Micro symbol
    norm = norm.replace('\u00c4', 'a')  # A with umlaut
    norm = norm.replace('\u00d6', 'o')  # O with umlaut
    norm = norm.replace('\u00dc', 'u')  # U with umlaut
    norm = norm.replace('\u00df', 'ss') # German sharp S
    norm = norm.replace('\u00e4', 'a')  # a with umlaut
    norm = norm.replace('\u00f6', 'o')  # o with umlaut
    norm = norm.replace('\u00fc', 'u')  # u with umlaut
    norm = norm.replace('\u03b1', 'a')  # Greek alpha
    norm = norm.replace('\u03b2', 'b')  # Greek beta
    norm = norm.replace('\u03b3', 'g')  # Greek gamma
    norm = norm.replace('\u03b4', 'd')  # Greek delta
    norm = norm.replace('\u2122', '')   # Trademark symbol
    norm = norm.replace('\u00ae', '')   # Registered trademark
    norm = norm.replace('\u00a9', '')   # Copyright symbol
    
    # Remove all separators and punctuation for clean comparison
    norm = norm.replace(" ", "").replace("-", "").replace("_", "")
    norm = norm.replace("/", "").replace("\\", "").replace(".", "")
    norm = norm.replace("(", "").replace(")", "").replace(",", "")
    norm = norm.replace(":", "").replace(";", "").replace("&", "")
    norm = norm.replace("+", "").replace("=", "").replace("%", "")
    norm = norm.replace("'", "").replace('"', "").replace('`', "")
    norm = norm.replace("[", "").replace("]", "").replace("{", "").replace("}", "")
    norm = norm.replace("|", "").replace("\\", "").replace("/", "")
    norm = norm.replace("!", "").replace("?", "").replace("*", "")
    norm = norm.replace("<", "").replace(">", "").replace("~", "")
    norm = norm.replace("▒", "").replace("□", "").replace("■", "")
    
    # Remove specific problem characters from original Excel and result set
    norm = ''.join(c for c in norm if c.isalnum())
    
    return norm

def match_column(col_name, df_columns):
    """Match column name to DataFrame columns using multiple strategies."""
    # Direct match (exact case)
    if col_name in df_columns:
        return col_name
        
    # Try with regular space instead of non-breaking space and vice versa
    col_with_nbsp = col_name.replace(' ', '\xa0')
    col_without_nbsp = col_name.replace('\xa0', ' ')
    
    if col_with_nbsp in df_columns:
        return col_with_nbsp
        
    if col_without_nbsp in df_columns:
        return col_without_nbsp
    
    # Case-insensitive match
    for col in df_columns:
        if col.lower() == col_name.lower():
            return col
    
    # Normalized match
    col_norm = normalize_column_name(col_name)
    for col in df_columns:
        if normalize_column_name(col) == col_norm:
            return col
    
    # No match found
    return None

def load_excel_data(excel_path, sheet_name=0):
    """Load data from Excel file into a DataFrame with robust column handling."""
    try:
        # First, check if this is a multi-sheet Excel file (could be from a previous validation)
        try:
            # First try to load just the sheet list
            sheet_list = pd.ExcelFile(excel_path).sheet_names
            logger.info(f"Excel file has {len(sheet_list)} sheets: {sheet_list}")
            
            # If we have 'Main View' sheet, always use that as our main data source
            if 'Main View' in sheet_list:
                logger.info("Found 'Main View' sheet, using it as the main data source")
                sheet_name = 'Main View'
            # If we have a numeric sheet_name but also have other sheets like 'Detailed View', 
            # make sure we're using the first/primary data sheet
            elif isinstance(sheet_name, int) and sheet_name == 0 and len(sheet_list) > 1:
                if 'Detailed View' in sheet_list or 'Reasons & Notes' in sheet_list:
                    # This looks like a previously processed file, so use the first non-detail sheet
                    for sheet in sheet_list:
                        if sheet not in ['Detailed View', 'Reasons & Notes']:
                            logger.info(f"Using sheet '{sheet}' as main data source")
                            sheet_name = sheet
                            break
        except Exception as sheet_error:
            # If we can't read the sheet list, just proceed with the default sheet
            logger.warning(f"Could not read sheet list: {str(sheet_error)}")
        
        # Now load the actual data
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        logger.info(f"Loaded Excel file, sheet '{sheet_name}' with {len(df)} rows and {len(df.columns)} columns")
        
        # Check if this looks like a "Detailed View" sheet incorrectly loaded
        if len(df.columns) >= 3 and df.columns[0] == 'Row' and df.columns[1] == 'Column':
            error_msg = "Attempted to load 'Detailed View' sheet instead of main data sheet. Please specify correct sheet."
            logger.error(error_msg)
            raise ValueError(error_msg)
        
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

def create_lambda_payload(row_data, config, row_key):
    """Create a payload for the Lambda function."""
    payload = {
        "test_mode": True,
        "config": config,
        "validation_data": {
            "rows": [row_data]
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
    """Invoke Lambda function with the given payload with retry and timeout handling."""
    import time
    
    # Configure boto3 with longer timeouts and retry settings
    config = botocore.config.Config(
        connect_timeout=120,  # 2 minutes connection timeout
        read_timeout=300,     # 5 minutes read timeout
        retries={
            'max_attempts': 5,
            'mode': 'adaptive'
        }
    )
    
    max_retries = 3
    retry_delay = 5  # Start with 5 seconds delay
    
    for attempt in range(1, max_retries + 1):
        try:
            # Create Lambda client with custom config
            lambda_client = boto3.client('lambda', region_name='us-east-1', config=config)
            
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
            logger.info(f"Invoking Lambda function (attempt {attempt}/{max_retries})...")
            response = lambda_client.invoke(
                FunctionName=LAMBDA_ARN,
                InvocationType='RequestResponse',
                Payload=payload_json
            )
            
            # Parse response
            response_payload = json.loads(response['Payload'].read().decode())
            logger.info(f"Lambda function response status: {response['StatusCode']}")
            
            return response_payload
        
        except botocore.exceptions.ReadTimeoutError as e:
            if attempt < max_retries:
                # Implement exponential backoff
                wait_time = retry_delay * (2 ** (attempt - 1))
                logger.warning(f"Lambda timeout on attempt {attempt}. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"Lambda function timed out after {max_retries} attempts. Last error: {str(e)}")
                # Create a basic error response so processing can continue
                error_response = {
                    "statusCode": 408,  # Request Timeout
                    "body": {
                        "error": "Lambda function timed out",
                        "validation_results": {}
                    }
                }
                return error_response
        
        except Exception as e:
            logger.error(f"Error invoking Lambda function (attempt {attempt}): {str(e)}")
            if attempt < max_retries:
                # Implement exponential backoff
                wait_time = retry_delay * (2 ** (attempt - 1))
                logger.warning(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"Failed to invoke Lambda after {max_retries} attempts")
                # Create a basic error response so processing can continue
                error_response = {
                    "statusCode": 500,
                    "body": {
                        "error": f"Error invoking Lambda: {str(e)}",
                        "validation_results": {}
                    }
                }
                return error_response

def process_lambda_response(response, row_data, row_key):
    """Process Lambda function response with robust column handling."""
    try:
        # Check if response is valid
        if not response or not isinstance(response, dict):
            logger.error(f"Invalid Lambda response: {response}")
            return None
        
        # Check for Lambda API Gateway format (statusCode/body)
        if 'statusCode' in response and 'body' in response:
            logger.info(f"Response has API Gateway format, statusCode: {response['statusCode']}")
            
            # Check if the status code indicates success
            if response['statusCode'] != 200:
                logger.error(f"Lambda returned error status: {response['statusCode']}")
                if isinstance(response['body'], dict) and 'error' in response['body']:
                    logger.error(f"Error message: {response['body']['error']}")
                return None
            
            # Try to parse the body
            try:
                # If body is a string (JSON), parse it
                if isinstance(response['body'], str):
                    body = json.loads(response['body'])
                else:
                    body = response['body']
                
                logger.info(f"Parsed response body with keys: {list(body.keys())}")
                
                # Check if this is the lambda_converted_debug.json format
                if 'data' in body:
                    # This is the converted debug format - extract the data directly
                    data = body['data']
                    
                    # Find the matching key for this row
                    row_key_variants = [row_key, row_key.replace('||', '|')]
                    matching_key = None
                    
                    for key in data.keys():
                        if key in row_key_variants or any(variant in key for variant in row_key_variants):
                            matching_key = key
                            break
                    
                    if matching_key:
                        # Extract the validation results directly
                        if 'validation_results' in data[matching_key]:
                            results = data[matching_key]['validation_results']
                            logger.info(f"Found results for row with key {matching_key} in data format")
                            
                            # Clean the column names to ensure consistent handling
                            cleaned_results = {}
                            for col, value in results.items():
                                # Replace non-breaking spaces with regular spaces
                                if isinstance(col, str) and '\xa0' in col:
                                    cleaned_col = col.replace('\xa0', ' ')
                                    cleaned_results[cleaned_col] = value
                                else:
                                    cleaned_results[col] = value
                            
                            # Check for validation history in the response
                            if 'validation_history' in data[matching_key]:
                                validation_history = data[matching_key]['validation_history']
                                # Add validation history to the results
                                cleaned_results['validation_history'] = validation_history
                            
                            # Return as dictionary keyed by row_key
                            return {row_key: cleaned_results}
                    
                    # If we didn't find a direct match, try a fuzzy match
                    for key in data.keys():
                        # Split on common separators and compare individual parts
                        key_parts = re.split(r'[|]+', key)
                        row_key_parts = re.split(r'[|]+', row_key)
                        
                        # Check if any part matches
                        if any(kp in row_key for kp in key_parts) or any(rkp in key for rkp in row_key_parts):
                            if 'validation_results' in data[key]:
                                results = data[key]['validation_results']
                                logger.info(f"Found results for row with fuzzy match key {key} in data format")
                                
                                # Clean the column names to ensure consistent handling
                                cleaned_results = {}
                                for col, value in results.items():
                                    # Replace non-breaking spaces with regular spaces
                                    if isinstance(col, str) and '\xa0' in col:
                                        cleaned_col = col.replace('\xa0', ' ')
                                        cleaned_results[cleaned_col] = value
                                    else:
                                        cleaned_results[col] = value
                                
                                # Check for validation history in the response
                                if 'validation_history' in data[key]:
                                    validation_history = data[key]['validation_history']
                                    # Add validation history to the results
                                    cleaned_results['validation_history'] = validation_history
                                
                                # Return as dictionary keyed by row_key
                                return {row_key: cleaned_results}
                    
                    # Still no match, log and return empty
                    logger.warning(f"No matching results found in data format for key {row_key}")
                    logger.warning(f"Available keys: {list(data.keys())}")
                    return None
                
                # Standard API response format
                if 'validation_results' in body:
                    validation_results = body['validation_results']
                    
                    if isinstance(validation_results, dict):
                        result_keys = list(validation_results.keys())
                        logger.info(f"Validation results contains {len(result_keys)} row keys")
                        
                        if result_keys:
                            # Get the first result (there should only be one for our test)
                            results = validation_results[result_keys[0]]
                            
                            # Clean the column names to ensure consistent handling
                            cleaned_results = {}
                            for col, value in results.items():
                                # Replace non-breaking spaces with regular spaces
                                if isinstance(col, str) and '\xa0' in col:
                                    cleaned_col = col.replace('\xa0', ' ')
                                    cleaned_results[cleaned_col] = value
                                else:
                                    cleaned_results[col] = value
                            
                            # Create dictionary with our row key as the key
                            processed_results = {}
                            processed_results[row_key] = cleaned_results
                            
                            # Check for validation history in the response
                            if 'validation_history' in body:
                                validation_history = body['validation_history']
                                # If there's a direct entry for the row key in the history
                                if row_key in validation_history:
                                    # Add validation history to the results
                                    cleaned_results['validation_history'] = validation_history[row_key]
                                # Or if there's an entry for the first result key
                                elif result_keys[0] in validation_history:
                                    # Add validation history to the results
                                    cleaned_results['validation_history'] = validation_history[result_keys[0]]
                            
                            logger.info(f"Found results for row index {result_keys[0]}")
                            
                            # Save raw response for detailed view
                            if 'raw_responses' in body:
                                # Add the raw_responses to the results
                                cleaned_results['_raw_responses'] = body['raw_responses']
                            
                            return processed_results
                        else:
                            logger.warning("No result keys found in validation_results")
                    else:
                        logger.warning(f"validation_results is not a dictionary: {validation_results}")
                else:
                    logger.warning("No validation_results found in response body")
                
                # Fall back to empty results
                logger.warning("No usable results found in response")
                return None
                
            except Exception as e:
                logger.error(f"Error parsing response body: {str(e)}")
                import traceback
                traceback.print_exc()
                return None
        else:
            # For old-format responses (unlikely)
            logger.warning("Response is not in API Gateway format, cannot process")
            return None
        
    except Exception as e:
        logger.error(f"Error processing Lambda response: {str(e)}")
        import traceback
        traceback.print_exc()
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
    logger.info(f"Generated row key: {row_key}")
    return row_key

def save_results_to_excel(df, results_dict, output_path, config):
    """Save validation results to Excel with robust column handling."""
    try:
        # Generate timestamp for the output file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not output_path:
            output_path = f"validation_results_{timestamp}.xlsx"
        
        # Add timestamp to filename if file already exists to avoid conflicts
        if os.path.exists(output_path):
            base_name, ext = os.path.splitext(output_path)
            output_path = f"{base_name}_{timestamp}{ext}"
            logger.info(f"Output file already exists, using new name: {output_path}")
        
        # Define helper function for Excel-safe values
        def safe_for_excel(value):
            """Convert value to Excel-safe format."""
            if value is None:
                return ""
            if isinstance(value, float) and (pd.isna(value) or np.isnan(value) or np.isinf(value)):
                return ""
            if isinstance(value, str) and len(value) > 32767:  # Excel's cell content limit
                return value[:32700] + "..."
            return value
        
        # Pre-process the dataframe to handle problematic values
        df_safe = df.copy()
        # Replace inf/-inf with empty strings
        df_safe = df_safe.replace([float('inf'), float('-inf')], '')
        # Replace NaN with empty strings
        df_safe = df_safe.fillna('')
        
        # Use pandas ExcelWriter with xlsxwriter engine
        # Need to handle different pandas versions
        try:
            # For newer pandas versions
            writer_options = {
                'engine': 'xlsxwriter',
                'engine_kwargs': {'options': {'nan_inf_to_errors': True, 'strings_to_urls': False}}
            }
            with pd.ExcelWriter(output_path, **writer_options) as writer:
                # Process the Excel output
                _write_excel_content(df_safe, results_dict, writer, config, safe_for_excel)
                return output_path
        except TypeError:
            # For older pandas versions
            try:
                writer = pd.ExcelWriter(output_path, engine='xlsxwriter')
                writer.book.set_properties({
                    'comments': 'Generated by perplexityValidator',
                    'category': 'Data Validation',
                    'status': 'Completed'
                })
                
                # Process the Excel output
                _write_excel_content(df_safe, results_dict, writer, config, safe_for_excel)
                writer.close()
                return output_path
            except Exception as e:
                logger.error(f"Error with older pandas ExcelWriter: {str(e)}")
                raise
        
    except Exception as e:
        logger.error(f"Error saving results to Excel: {str(e)}")
        import traceback
        traceback.print_exc()
        # Try a simple save as a last resort
        try:
            # Just save the basic DataFrame without any formatting
            df_simple = df.copy()
            # Replace all problematic values
            df_simple = df_simple.replace([float('inf'), float('-inf')], '')
            df_simple = df_simple.fillna('')
            # Convert all columns to string with truncation to avoid Excel limits
            for col in df_simple.columns:
                if df_simple[col].dtype == 'object':
                    df_simple[col] = df_simple[col].astype(str).apply(
                        lambda x: x[:32700] + "..." if len(x) > 32767 else x)
            
            # Simplest possible Excel save
            df_simple.to_excel(output_path, index=False, engine='openpyxl')
            logger.warning(f"Fallback save to Excel without formatting succeeded: {output_path}")
            return output_path
        except Exception as fallback_error:
            logger.error(f"Even fallback Excel save failed: {str(fallback_error)}")
            # Try CSV as a last resort
            try:
                csv_path = output_path.replace('.xlsx', '.csv')
                df_simple.to_csv(csv_path, index=False)
                logger.warning(f"Emergency fallback to CSV succeeded: {csv_path}")
                return csv_path
            except:
                logger.error("All Excel/CSV save attempts failed")
        raise

def _write_excel_content(df, results_dict, writer, config, safe_for_excel):
    """Write content to Excel with the given writer."""
    # Create a copy of the original DataFrame to avoid modifying the input
    result_df = df.copy().fillna('')
    
    # Convert all column names with non-breaking spaces to regular spaces
    column_mapping = {}
    for col in result_df.columns:
        if '\xa0' in col:
            new_col = col.replace('\xa0', ' ')
            column_mapping[col] = new_col
    
    # Rename columns with non-breaking spaces
    if column_mapping:
        logger.info(f"Renaming columns with non-breaking spaces: {column_mapping}")
        result_df = result_df.rename(columns=column_mapping)
    
    # Remove duplicate columns (keep first occurrence)
    result_df = result_df.loc[:, ~result_df.columns.duplicated()]
    
    # Get primary key columns using SimplifiedSchemaValidator
    try:
        from schema_validator_simplified import SimplifiedSchemaValidator
        validator = SimplifiedSchemaValidator(config)
        primary_key_columns = validator.primary_key
        id_fields = [target.column for target in validator.get_id_fields()]
        logger.info(f"Using auto-generated primary key: {primary_key_columns}")
        logger.info(f"ID fields (no confidence formatting): {id_fields}")
    except Exception as e:
        logger.warning(f"Could not create SimplifiedSchemaValidator: {e}")
        # Fallback to old method
        primary_key_columns = config.get('primary_key', [])
        if not primary_key_columns:
            # Try to find ID fields manually
            id_fields = []
            for target in config.get('validation_targets', []):
                if target.get('importance', '').upper() == 'ID':
                    id_fields.append(target['column'])
            primary_key_columns = id_fields
        else:
            id_fields = primary_key_columns  # Fallback assumption
        logger.info(f"Using fallback primary key: {primary_key_columns}")
        logger.info(f"ID fields (fallback): {id_fields}")
    
    # Create workbook and formats
    workbook = writer.book
    
    # Add a date format for date columns
    date_format = workbook.add_format({'num_format': 'yyyy-mm-dd', 'align': 'center'})
    
    # Add worksheets
    worksheet = workbook.add_worksheet('Results')
    detail_worksheet = workbook.add_worksheet('Details')
    reasons_worksheet = workbook.add_worksheet('Reasons')
    history_worksheet = workbook.add_worksheet('History')
    
    # Formats
    header_format = workbook.add_format({'bold': True, 'text_wrap': True, 'valign': 'top',
                                       'fg_color': '#4472C4', 'font_color': 'white', 'border': 1})
    
    subheader_format = workbook.add_format({'bold': True, 'text_wrap': True, 'valign': 'top',
                                       'fg_color': '#8EA9DB', 'font_color': 'black', 'border': 1})
    
    alert_format = workbook.add_format({'bold': True, 'italic': True, 'fg_color': '#FFC7CE', 'font_color': '#9C0006'})
    
    confidence_formats = {
        'HIGH': workbook.add_format({'bold': True, 'fg_color': '#C6EFCE', 'font_color': '#006100'}),
        'MEDIUM': workbook.add_format({'fg_color': '#FFEB9C', 'font_color': '#9C6500'}),
        'LOW': workbook.add_format({'italic': True, 'fg_color': '#FFC7CE', 'font_color': '#9C0006'})
    }
    
    # Write headers for main Results worksheet
    for col_idx, col_name in enumerate(result_df.columns):
        worksheet.write(0, col_idx, col_name, header_format)
    
    # Set columns widths based on data
    for col_idx, col_name in enumerate(result_df.columns):
        max_len = max(result_df[col_name].astype(str).str.len().max(), len(col_name)) + 2
        worksheet.set_column(col_idx, col_idx, min(max_len, 40))  # Cap at 40 characters
    
    # Write column data for each row with validation results overlay
    for row_idx, (_, row) in enumerate(result_df.iterrows()):
        # Try to find validation results for this row
        row_validation_data = None
        if row_idx in results_dict:
            row_validation_data = results_dict[row_idx]
        elif str(row_idx) in results_dict:
            row_validation_data = results_dict[str(row_idx)]
        
        for col_idx, (col_name, cell_value) in enumerate(row.items()):
            # Check if this is an ID field (should not have confidence formatting)
            is_id_field = col_name in id_fields
            
            # Check if we have validation results for this column
            validated_value = None
            confidence_level = None
            if row_validation_data and isinstance(row_validation_data, dict):
                if col_name in row_validation_data and isinstance(row_validation_data[col_name], dict):
                    validated_value = row_validation_data[col_name].get('value')
                    confidence_level = row_validation_data[col_name].get('confidence_level')
            
            # Use validated value if available, otherwise use original value
            final_value = validated_value if validated_value is not None else cell_value
            
            # Determine the format to use
            cell_format = None
            if not is_id_field and confidence_level and confidence_level.upper() in confidence_formats:
                # Apply confidence formatting for non-ID fields
                cell_format = confidence_formats[confidence_level.upper()]
            elif validated_value is not None and validated_value != cell_value:
                # Apply light green background for validated/updated values (but not confidence color)
                cell_format = workbook.add_format({'bg_color': '#E6FFE6'})
            
            # Write the value to Excel
            try:
                # Skip NaN values
                if pd.isna(final_value):
                    worksheet.write(row_idx + 1, col_idx, '', cell_format)
                else:
                    # For Excel compatibility, make sure the value is not too long
                    if isinstance(final_value, str) and len(final_value) > 32767:
                        safe_value = final_value[:32700] + '... [truncated]'
                        worksheet.write(row_idx + 1, col_idx, safe_value, cell_format)
                    else:
                        worksheet.write(row_idx + 1, col_idx, final_value, cell_format)
                    
                    # Add comment with quote and sources if this column was validated
                    if row_validation_data and isinstance(row_validation_data, dict):
                        if col_name in row_validation_data and isinstance(row_validation_data[col_name], dict):
                            col_validation = row_validation_data[col_name]
                            quote = col_validation.get('quote', '')
                            sources = col_validation.get('sources', [])
                            
                            # Create comment text if we have quote or sources
                            comment_parts = []
                            if quote and quote != 'N/A' and quote.strip():
                                comment_parts.append(f'Quote: "{quote}"')
                            
                            if sources and isinstance(sources, list) and sources:
                                sources_text = ', '.join(sources)
                                comment_parts.append(f'Sources: {sources_text}')
                            elif sources and str(sources) != 'N/A' and str(sources).strip():
                                comment_parts.append(f'Sources: {sources}')
                            
                            if comment_parts:
                                comment_text = '\n\n'.join(comment_parts)
                                try:
                                    worksheet.write_comment(row_idx + 1, col_idx, comment_text, 
                                                          {'width': 300, 'height': 150})
                                except Exception as comment_error:
                                    logger.warning(f"Could not add comment to cell ({row_idx+1}, {col_idx}): {comment_error}")
                        
            except Exception as e:
                logger.error(f"Error writing cell value for {col_name} ({final_value}): {str(e)}")
                try:
                    # Try to convert to string if there's an error
                    worksheet.write(row_idx + 1, col_idx, str(final_value)[:1000], cell_format)
                except:
                    worksheet.write(row_idx + 1, col_idx, "[Error - could not display value]", cell_format)
    
    # Initialize counters for details and reasons worksheets
    detail_row = 1  # Start at 1 to leave room for header
    reasons_row = 1
    history_row_counter = 1
    used_result_keys = set()  # Initialize here to avoid scoping issues
    
    # Write headers for detail worksheet
    detail_headers = ["Row Key", "Identifier", "Column", "Original Value", "Validated Value", "Confidence", "Quote", "Sources", "Explanation", "Update Required", "Substantially Different", "Consistent with Model"]
    for col_idx, header in enumerate(detail_headers):
        detail_worksheet.write(0, col_idx, header, header_format)
    
    # Set column widths for detail worksheet
    detail_worksheet.set_column(0, 0, 15)  # Row Key
    detail_worksheet.set_column(1, 1, 30)  # Identifier
    detail_worksheet.set_column(2, 2, 25)  # Column
    detail_worksheet.set_column(3, 3, 30)  # Original Value
    detail_worksheet.set_column(4, 4, 30)  # Validated Value
    detail_worksheet.set_column(5, 5, 15)  # Confidence
    detail_worksheet.set_column(6, 6, 50)  # Quote
    detail_worksheet.set_column(7, 7, 40)  # Sources
    detail_worksheet.set_column(8, 8, 60)  # Explanation
    detail_worksheet.set_column(9, 9, 15)  # Update Required
    detail_worksheet.set_column(10, 10, 20)  # Substantially Different
    detail_worksheet.set_column(11, 11, 25)  # Consistent with Model
    
    # Write headers for reasons worksheet
    reasons_headers = ["Row Key", "Identifier", "Holistic Validation", "Reason"]
    for col_idx, header in enumerate(reasons_headers):
        reasons_worksheet.write(0, col_idx, header, header_format)
    
    # Set column widths for reasons worksheet
    reasons_worksheet.set_column(0, 0, 15)  # Row Key
    reasons_worksheet.set_column(1, 1, 30)  # Identifier
    reasons_worksheet.set_column(2, 2, 20)  # Holistic Validation
    reasons_worksheet.set_column(3, 3, 80)  # Reason
    
    # Write headers for history worksheet
    history_headers = ["Row Key"] + primary_key_columns + ["Column", "Value", "Confidence", "Timestamp"]
    for col_idx, header in enumerate(history_headers):
        history_worksheet.write(0, col_idx, header, header_format)
    
    # Set column widths for history worksheet
    history_worksheet.set_column(0, 0, 15)  # Row Key
    for i in range(len(primary_key_columns)):
        history_worksheet.set_column(1+i, 1+i, 25)  # Primary key columns
    hist_offset = len(primary_key_columns) + 1
    history_worksheet.set_column(hist_offset, hist_offset, 25)  # Column
    history_worksheet.set_column(hist_offset+1, hist_offset+1, 30)  # Value
    history_worksheet.set_column(hist_offset+2, hist_offset+2, 15)  # Confidence
    history_worksheet.set_column(hist_offset+3, hist_offset+3, 20)  # Timestamp
    
    # Process each row's validation results
    for row_idx, (_, row) in enumerate(result_df.iterrows()):
        # Try to find matching result using row index directly
        matched_key = None
        row_data = None
        
        # Check if we have results for this row index
        if row_idx in results_dict:
            matched_key = row_idx
            row_data = results_dict[row_idx]
        else:
            # Try string version of row index
            str_row_idx = str(row_idx)
            if str_row_idx in results_dict:
                matched_key = str_row_idx
                row_data = results_dict[str_row_idx]
            else:
                # Try to find any result that hasn't been used yet
                for key, data in results_dict.items():
                    if key not in used_result_keys:
                        matched_key = key
                        row_data = data
                        break
        
        if not matched_key or not row_data:
            logger.warning(f"No validation results found for row {row_idx+1}")
            continue
            
        # Mark this key as used
        used_result_keys.add(matched_key)
        
        # Skip non-dictionary values
        if not isinstance(row_data, dict):
            logger.warning(f"Skipping non-dictionary result for row {row_idx+1}: {type(row_data)}")
            continue
        
        logger.info(f"Processing row {row_idx+1} with matched key: {matched_key}")
        
        # Generate identifier from primary key values
        identifier_parts = []
        for pk in primary_key_columns:
            if pk in row and not pd.isna(row[pk]):
                identifier_parts.append(str(row[pk]))
            else:
                identifier_parts.append("?")
        
        identifier = " | ".join(identifier_parts) if identifier_parts else f"Row {row_idx+1}"
        
        # Process individual column validations
        for col_name, col_data in row_data.items():
            # Skip special fields and non-dictionary values
            if col_name in ['holistic_validation', 'reasons', 'next_check', '_raw_responses', 'validation_history']:
                continue
                
            if not isinstance(col_data, dict):
                continue
            
            # Extract validation details
            value = col_data.get('value', 'N/A')
            confidence = col_data.get('confidence_level', col_data.get('confidence', 'N/A'))  # Use text confidence first
            quote = col_data.get('quote', 'N/A')
            sources = col_data.get('sources', [])
            explanation = col_data.get('explanation', 'N/A')
            update_required = col_data.get('update_required', 'N/A')
            substantially_different = col_data.get('substantially_different', 'N/A')
            consistent_with_model = col_data.get('consistent_with_model_knowledge', 'N/A')
            
            # Get original value from the DataFrame
            original_value = 'N/A'
            if col_name in row:
                original_value = row[col_name]
                if pd.isna(original_value):
                    original_value = 'N/A'
                else:
                    original_value = str(original_value)
            
            # Convert sources list to string
            if isinstance(sources, list):
                sources_str = '; '.join(sources) if sources else 'N/A'
            else:
                sources_str = str(sources) if sources else 'N/A'
            
            # Ensure all values are strings and safe for Excel
            if not isinstance(value, str):
                value = str(value)
            
            if not isinstance(confidence, str):
                confidence = str(confidence)
                
            if not isinstance(quote, str):
                quote = str(quote)
                
            if not isinstance(explanation, str):
                explanation = str(explanation)
                
            if not isinstance(update_required, str):
                update_required = str(update_required)
                
            if not isinstance(substantially_different, str):
                substantially_different = str(substantially_different)
                
            if not isinstance(consistent_with_model, str):
                consistent_with_model = str(consistent_with_model)
            
            # Make sure values are safe for Excel (truncate if needed)
            original_value = safe_for_excel(original_value)
            value = safe_for_excel(value)
            confidence = safe_for_excel(confidence)
            quote = safe_for_excel(quote)
            sources_str = safe_for_excel(sources_str)
            explanation = safe_for_excel(explanation)
            update_required = safe_for_excel(update_required)
            substantially_different = safe_for_excel(substantially_different)
            consistent_with_model = safe_for_excel(consistent_with_model)
            
            # Write to detail worksheet
            detail_worksheet.write(detail_row, 0, matched_key)  # Row Key
            detail_worksheet.write(detail_row, 1, identifier)  # Identifier
            detail_worksheet.write(detail_row, 2, col_name)  # Column
            detail_worksheet.write(detail_row, 3, original_value)  # Original Value
            detail_worksheet.write(detail_row, 4, value)  # Validated Value
            
            # Apply confidence formatting (skip for ID fields)
            if col_name not in id_fields and confidence.upper() in confidence_formats:
                detail_worksheet.write(detail_row, 5, confidence, confidence_formats[confidence.upper()])
            else:
                detail_worksheet.write(detail_row, 5, confidence)
                
            detail_worksheet.write(detail_row, 6, quote)  # Quote
            detail_worksheet.write(detail_row, 7, sources_str)  # Sources
            detail_worksheet.write(detail_row, 8, explanation)  # Explanation
            detail_worksheet.write(detail_row, 9, update_required)  # Update Required
            detail_worksheet.write(detail_row, 10, substantially_different)  # Substantially Different
            detail_worksheet.write(detail_row, 11, consistent_with_model)  # Consistent with Model
            
            detail_row += 1
        
        # Process holistic validation and reasons
        if 'holistic_validation' in row_data and 'reasons' in row_data:
            holistic_result = row_data['holistic_validation']
            reasons = row_data['reasons']
            
            for reason in reasons:
                # Ensure reason is string and safe for Excel
                if not isinstance(reason, str):
                    reason = str(reason)
                
                reason = safe_for_excel(reason)
                
                # Write to reasons worksheet
                reasons_worksheet.write(reasons_row, 0, matched_key)  # Row Key
                reasons_worksheet.write(reasons_row, 1, identifier)  # Identifier
                reasons_worksheet.write(reasons_row, 2, holistic_result)  # Holistic Validation
                reasons_worksheet.write(reasons_row, 3, reason)  # Reason
                
                reasons_row += 1
    
    # Try adding autofilter to each worksheet
    try:
        worksheet.autofilter(0, 0, len(result_df), len(result_df.columns) - 1)
    except Exception as filter_error:
        logger.error(f"Error adding autofilter to main worksheet: {str(filter_error)}")
    
    try:
        detail_worksheet.autofilter(0, 0, detail_row - 1, len(detail_headers) - 1)
    except Exception as detail_filter_error:
        logger.error(f"Error adding autofilter to detail worksheet: {str(detail_filter_error)}")
    
    try:
        reasons_worksheet.autofilter(0, 0, reasons_row - 1, len(reasons_headers) - 1)
    except Exception as reasons_filter_error:
        logger.error(f"Error adding autofilter to reasons worksheet: {str(reasons_filter_error)}")
    
    try:
        history_worksheet.autofilter(0, 0, history_row_counter - 1, len(history_headers) - 1)
    except Exception as history_filter_error:
        logger.error(f"Error adding autofilter to history worksheet: {str(history_filter_error)}")

def main():
    """Main function to test Lambda with rows from the Excel file."""
    try:
        import argparse
        parser = argparse.ArgumentParser(description="Lambda validation test with Excel output")
        parser.add_argument("--input", "-i", help="Input Excel file path", required=True)
        parser.add_argument("--config", "-c", help="Configuration JSON file path", required=True)
        parser.add_argument("--output", "-o", help="Output Excel file path")
        parser.add_argument("--rows", "-r", type=int, default=3, help="Number of rows to test (default: 3)")
        parser.add_argument("--api-key", "-k", help="API key for authentication")
        parser.add_argument("--timeout", "-t", type=int, default=300, help="Lambda timeout in seconds (default: 300)")
        parser.add_argument("--sheet", "-s", help="Excel sheet name or index to use (default: 0 or 'Main View' if exists)")
        args = parser.parse_args()
        
        # Load config from the JSON file
        logger.info(f"Loading configuration from: {args.config}")
        config = load_config_file(args.config)
        
        # Load Excel data
        logger.info(f"Loading data from: {args.input}")
        sheet_name = args.sheet if args.sheet is not None else 0
        df = load_excel_data(args.input, sheet_name=sheet_name)
        
        # Take the specified number of rows
        test_df = df.head(args.rows) if args.rows > 0 else df
        logger.info(f"Testing with {len(test_df)} rows")
        
        # Process each row
        all_results = {}
        errors = 0
        success = 0
        
        for index, row in test_df.iterrows():
            try:
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
                row_key = generate_row_key(row_data, config.get('primary_key', []))
                logger.info(f"Processing row {index+1}/{len(test_df)}: {row_key}")
                
                # Add API key if provided
                if args.api_key:
                    config['api_key'] = args.api_key
                
                # Create Lambda payload
                payload = create_lambda_payload(row_data, config, row_key)
                
                # Invoke Lambda function
                response = invoke_lambda(payload)
                
                # Process response
                results = process_lambda_response(response, row_data, row_key)
                if results:
                    # Merge into all_results
                    all_results.update(results)
                    logger.info(f"Added results for row {index+1}")
                    success += 1
                else:
                    logger.warning(f"No results obtained for row {index+1}")
                    errors += 1
                
                # Add a delay to avoid rate limiting
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error processing row {index+1}: {str(e)}")
                import traceback
                traceback.print_exc()
                errors += 1
                # Continue processing other rows
                continue
        
        # Report success/failure counts
        logger.info(f"Processing complete: {success} rows succeeded, {errors} rows failed")
        
        # Save results to Excel if we have any
        if all_results:
            output_path = args.output
            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = f"validation_results_{timestamp}.xlsx"
            
            save_results_to_excel(df, all_results, output_path, config)
            logger.info(f"Results saved to {output_path}")
        else:
            logger.warning("No results to save to Excel")
        
        logger.info("Test completed successfully")
        
        # Return error count as exit code
        if errors > 0:
            sys.exit(min(errors, 100))  # Cap at 100 to avoid OS limits
            
    except Exception as e:
        logger.error(f"Error in test: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 