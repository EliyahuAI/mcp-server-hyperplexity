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
from datetime import datetime
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
            if value is None or (isinstance(value, float) and (pd.isna(value) or math.isnan(value) or math.isinf(value))):
                return ""
            return value
        
        # Use pandas ExcelWriter with xlsxwriter engine
        # Need to handle different pandas versions
        try:
            # For newer pandas versions
            with pd.ExcelWriter(output_path, engine='xlsxwriter', engine_kwargs={'options': {'nan_inf_to_errors': True}}) as writer:
                # Process the Excel output
                _write_excel_content(df, results_dict, writer, config, safe_for_excel)
                return output_path
        except TypeError:
            # For older pandas versions
            try:
                writer = pd.ExcelWriter(output_path, engine='xlsxwriter')
                # Make sure all NaN/inf values are converted to empty strings
                df_safe = df.copy().fillna('')
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
            df_simple = df.copy().fillna('')
            df_simple.to_excel(output_path, index=False)
            logger.warning(f"Fallback save to Excel without formatting succeeded: {output_path}")
            return output_path
        except Exception as fallback_error:
            logger.error(f"Even fallback Excel save failed: {str(fallback_error)}")
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
    
    # Remove columns that are entirely unnamed or empty
    result_df = result_df.loc[:, [col for col in result_df.columns if str(col).strip() and not str(col).startswith('Unnamed')]]
    
    # Get the workbook and worksheet objects
    workbook = writer.book
    
    # Create formats for headers and data
    header_format = workbook.add_format({
        'bold': True, 'text_wrap': True, 'valign': 'center',
        'fg_color': '#4472C4', 'font_color': 'white', 'border': 1
    })
    high_confidence = workbook.add_format({'bg_color': '#C6EFCE'})  # Light green
    medium_confidence = workbook.add_format({'bg_color': '#FFEB9C'})  # Light yellow
    low_confidence = workbook.add_format({'bg_color': '#FFC7CE'})  # Light red
    update_required = workbook.add_format({
        'bg_color': '#FF7B7B', 'font_color': 'black', 'bold': True
    })
    wrap_format = workbook.add_format({'text_wrap': True})
    
    # Write the cleaned dataframe to Excel
    result_df.to_excel(writer, sheet_name='Main View', index=False)
    
    # Get the worksheet - handle both dict and attribute access for compatibility
    try:
        worksheet = writer.sheets['Main View']
    except (KeyError, AttributeError):
        try:
            worksheet = writer.book.get_worksheet_by_name('Main View')
        except AttributeError:
            # Last resort, get the first worksheet if we can't access by name
            try:
                worksheet = writer.book.worksheets()[0]
            except:
                worksheet = writer.book.add_worksheet('Main View')
            logger.warning("Could not access 'Main View' worksheet by name, using first worksheet")
    
    # Format the header row and set column widths
    for col_num, value in enumerate(result_df.columns.values):
        worksheet.write(0, col_num, value, header_format)
        max_len = max(
            result_df[value].astype(str).apply(len).max() if not result_df[value].empty else 0,
            len(str(value))
        ) + 2
        worksheet.set_column(col_num, col_num, max_len)
    
    # Log the final DataFrame columns for debugging
    logger.info(f"Final DataFrame columns in Excel: {list(result_df.columns)}")
    
    # Create Detailed View worksheet
    # Check if a Detailed View sheet already exists and use it, otherwise create a new one
    try:
        detail_worksheet = writer.book.get_worksheet_by_name('Detailed View')
        # If it exists, clear it first
        detail_worksheet.clear()
    except (AttributeError, ValueError):
        # Sheet doesn't exist or can't be accessed, create a new one
        detail_worksheet = workbook.add_worksheet('Detailed View')
    
    detail_headers = [
        "Row", "Column", "Original Value", "Validated Value", 
        "Confidence Level", "Update Required", "Sources", "Quote", "Reasoning"
    ]
    for col_num, header in enumerate(detail_headers):
        detail_worksheet.write(0, col_num, header, header_format)
    detail_worksheet.set_column(0, 0, 5)
    detail_worksheet.set_column(1, 1, 25)
    detail_worksheet.set_column(2, 2, 40)
    detail_worksheet.set_column(3, 3, 40)
    detail_worksheet.set_column(4, 4, 15)
    detail_worksheet.set_column(5, 5, 15)
    detail_worksheet.set_column(6, 6, 50)
    detail_worksheet.set_column(7, 7, 50)
    detail_worksheet.set_column(8, 8, 80)
    
    # Create Reasons worksheet
    # Check if a Reasons & Notes sheet already exists and use it, otherwise create a new one
    try:
        reasons_worksheet = writer.book.get_worksheet_by_name('Reasons & Notes')
        # If it exists, clear it first
        reasons_worksheet.clear()
    except (AttributeError, ValueError):
        # Sheet doesn't exist or can't be accessed, create a new one
        reasons_worksheet = workbook.add_worksheet('Reasons & Notes')
    
    reasons_headers = ["Row", "Overall Validation", "Next Check", "Reasons"]
    for col_num, header in enumerate(reasons_headers):
        reasons_worksheet.write(0, col_num, header, header_format)
    reasons_worksheet.set_column(0, 0, 5)
    reasons_worksheet.set_column(1, 1, 20)
    reasons_worksheet.set_column(2, 2, 20)
    reasons_worksheet.set_column(3, 3, 100)
    
    detail_row = 1
    reasons_row = 1
    primary_keys = config.get('primary_key', [])
    if not primary_keys:
        primary_keys = [result_df.columns[0]] if len(result_df.columns) > 0 else []
        logging.warning(f"No primary key found in config, using first column: {primary_keys}")
    
    # Clean the result_dict column names: replace non-breaking spaces with regular spaces
    cleaned_results_dict = {}
    for row_key, row_data in results_dict.items():
        cleaned_row_data = {}
        for col_name, value in row_data.items():
            if isinstance(col_name, str) and '\xa0' in col_name:
                cleaned_col_name = col_name.replace('\xa0', ' ')
                cleaned_row_data[cleaned_col_name] = value
            else:
                cleaned_row_data[col_name] = value
        cleaned_results_dict[row_key] = cleaned_row_data
    
    logger.info(f"Cleaned results dictionary column names")
    
    # Create a lookup dictionary for fuzzy matching result row keys
    # This will help match response keys to the original row keys
    result_keys = list(cleaned_results_dict.keys())
    
    # Log all result keys for debugging
    logger.info(f"Result keys available: {result_keys}")
    
    # Keep track of which result keys have already been used
    used_result_keys = set()
    
    # Use a more flexible row key matching approach
    for row_idx in range(len(result_df)):
        # Generate the row key as we would for the lookup
        pk_values = []
        for pk in primary_keys:
            if pk in result_df.columns:
                pk_value = result_df.iloc[row_idx][pk]
                pk_values.append(str(pk_value) if not pd.isna(pk_value) else "")
        row_key = "||".join(pk_values)
        
        # Try direct match first
        if row_key in cleaned_results_dict and row_key not in used_result_keys:
            matched_key = row_key
            row_results = cleaned_results_dict[matched_key]
            logger.info(f"Processing row {row_idx+1}, direct key match: {row_key}")
            used_result_keys.add(matched_key)
        else:
            # Try fuzzy matching with the result keys
            matched_key = None
            
            # Normalize the row key for matching
            row_key_norm = normalize_column_name(row_key)
            
            # First, try matching by all primary key parts being in the result key
            for result_key in result_keys:
                # Skip already used keys
                if result_key in used_result_keys:
                    continue
                    
                # Check if all parts of the row key are in the result key
                parts_match = True
                for part in pk_values:
                    # Skip empty parts
                    if not part.strip():
                        continue
                    # Normalize for comparison
                    part_norm = normalize_column_name(part)
                    result_norm = normalize_column_name(result_key)
                    
                    # Try more lenient matching for complex product names
                    if part_norm and len(part_norm) >= 3:  # Only consider parts with at least 3 chars
                        # Check if significant portion of part is in result or vice versa
                        if not (part_norm in result_norm or 
                               any(part_norm[i:i+min(len(part_norm), 5)] in result_norm 
                                   for i in range(0, len(part_norm), 3))):
                            parts_match = False
                            break
                    elif part_norm:  # For very short parts (like "Cu"), exact match required
                        if part_norm not in result_norm:
                            parts_match = False
                            break
                
                if parts_match:
                    matched_key = result_key
                    logger.info(f"Found fuzzy match for row {row_idx+1}: {row_key} -> {result_key}")
                    used_result_keys.add(matched_key)
                    break
            
            # If still no match, try matching by keywords in the product name
            if not matched_key and len(pk_values) > 0:
                product_name = pk_values[0]
                
                # Extract significant identifiers from the product name
                # Common patterns: product codes, radionuclides, target names, etc.
                identifiers = []
                
                # Extract product codes (typically alphanumeric with hyphens)
                product_codes = re.findall(r'[A-Za-z0-9]+[-][A-Za-z0-9]+', product_name)
                identifiers.extend(product_codes)
                
                # Extract common radiopharmaceutical isotopes with numbers
                isotope_patterns = [
                    r'(?:64|67)Cu', r'(?:177|175)Lu', r'(?:225|227|223)Ac', r'(?:212|203)Pb',
                    r'(?:68|67|64)Ga', r'99mTc', r'(?:188|186)Re', r'(?:89|90)Zr', r'(?:131|125|123)I',
                    r'(?:90|91)Y', r'(?:161|160)Tb', r'211At', r'213Bi', r'227Th'
                ]
                for pattern in isotope_patterns:
                    matches = re.findall(pattern, product_name)
                    identifiers.extend(matches)
                
                # Extract chemical elements and isotopes (typically 2-3 letters possibly with numbers)
                elements = re.findall(r'(?:[0-9]{1,3}[A-Z][a-z]?|[A-Z][a-z]?)', product_name)
                identifiers.extend(elements)
                
                # Extract common target abbreviations
                target_patterns = [
                    'PSMA', 'FAP', 'SSTR2', 'GRPR', 'CAIX', 'HER2', 'EGFR', 'cMET', 'GPC3',
                    'CD45', 'CD33', 'DLL3', 'LAT1', 'IGF1R', 'B7H3', 'TATE', 'TOC', 'DOTANOC',
                    'DOTATOC', 'DOTATATE', 'FAPI', 'mAb', 'RTX', 'PET'
                ]
                for target in target_patterns:
                    if target in product_name.upper():
                        identifiers.append(target)
                
                # Extract any sequence of 3+ letters (could be targets, etc.)
                words = re.findall(r'[A-Za-z]{3,}', product_name)
                identifiers.extend(words)
                
                # Extract numeric product codes
                numbers = re.findall(r'[0-9]{3,}', product_name)
                identifiers.extend(numbers)
                
                # Special case for common prefixes/formats in radiopharmaceuticals
                special_prefixes = [
                    'SAR', 'TLX', 'RYZ', 'FPI', 'PNT', 'OX', 'BAY', 'AZD',
                    'ACTIMAB', 'IOMAB', 'SOLUCIN', 'ALPHA', 'NANO'
                ]
                for prefix in special_prefixes:
                    if prefix in product_name.upper():
                        identifiers.append(prefix)
                
                # Try to match by these identifiers
                best_match = None
                best_score = 0
                
                for result_key in result_keys:
                    # Skip already used keys
                    if result_key in used_result_keys:
                        continue
                        
                    # Count how many identifiers match
                    match_count = 0
                    for identifier in identifiers:
                        if identifier in result_key:
                            match_count += 1
                    
                    # Calculate a match score (percentage of identifiers that match)
                    score = match_count / len(identifiers) if identifiers else 0
                    
                    # If this is the best match so far and meets minimum threshold, save it
                    if score > best_score and score >= 0.5:  # At least 50% of identifiers must match
                        best_score = score
                        best_match = result_key
                
                # Use the best match if found
                if best_match:
                    matched_key = best_match
                    logger.info(f"Found identifier-based match for row {row_idx+1}: {row_key} -> {matched_key} (score: {best_score:.2f})")
                    logger.info(f"Matching identifiers: {[id for id in identifiers if id in matched_key]}")
                    used_result_keys.add(matched_key)
            
            # If still no match, try matching by primary key position using separators
            if not matched_key:
                best_match = None
                best_score = 0
                
                for result_key in result_keys:
                    # Skip already used keys
                    if result_key in used_result_keys:
                        continue
                        
                    # Split both keys by the separator
                    row_parts = row_key.split("||")
                    result_parts = result_key.split("||") if "||" in result_key else result_key.split("|")
                    
                    # Check if the number of parts match
                    if len(row_parts) == len(result_parts):
                        # Check if enough parts match
                        match_count = 0
                        for i, (row_part, result_part) in enumerate(zip(row_parts, result_parts)):
                            row_part_norm = normalize_column_name(row_part)
                            result_part_norm = normalize_column_name(result_part)
                            
                            # For primary key, check if the normalized value is within the other
                            if row_part_norm in result_part_norm or result_part_norm in row_part_norm:
                                match_count += 1
                        
                        # Calculate a score based on how many parts match
                        score = match_count / len(row_parts)
                        
                        # If this is the best match so far and meets minimum threshold, save it
                        if score > best_score and score >= 0.66:  # At least 2/3 of parts must match
                            best_score = score
                            best_match = result_key
                
                # Use the best match if found
                if best_match:
                    matched_key = best_match
                    logger.info(f"Found position-based match for row {row_idx+1}: {row_key} -> {matched_key} (score: {best_score:.2f})")
                    used_result_keys.add(matched_key)
            
            # Last resort - try to find any key that contains the first primary key value
            if not matched_key and len(pk_values) > 0 and pk_values[0].strip():
                first_pk = pk_values[0].strip()
                # Try both direct and normalized matching, but only for unused keys
                for result_key in result_keys:
                    if result_key in used_result_keys:
                        continue
                        
                    if (first_pk in result_key) or (normalize_column_name(first_pk) in normalize_column_name(result_key)):
                        matched_key = result_key
                        logger.info(f"Found last-resort match for row {row_idx+1}: {row_key} -> {result_key}")
                        used_result_keys.add(matched_key)
                        break
            
            # Final attempt - try completely normalized comparison ignoring all separators and spaces
            if not matched_key and len(pk_values) > 0:
                # Get a super normalized version of the row key (just alphanumeric characters)
                super_norm_row = ''.join(c.lower() for c in row_key if c.isalnum())
                
                # Find the closest match based on character overlap
                best_match = None
                best_score = 0.4  # Minimum threshold (40% similarity)
                
                for result_key in result_keys:
                    if result_key in used_result_keys:
                        continue
                        
                    # Get super normalized version of result key
                    super_norm_result = ''.join(c.lower() for c in result_key if c.isalnum())
                    
                    # Calculate overlap score (proportion of shared characters)
                    if not super_norm_row or not super_norm_result:
                        continue
                        
                    # Find longest common substring
                    from difflib import SequenceMatcher
                    match = SequenceMatcher(None, super_norm_row, super_norm_result).find_longest_match(
                        0, len(super_norm_row), 0, len(super_norm_result))
                    
                    if match.size >= 5:  # At least 5 characters must match
                        score = match.size / max(len(super_norm_row), len(super_norm_result))
                        if score > best_score:
                            best_score = score
                            best_match = result_key
                
                if best_match:
                    matched_key = best_match
                    logger.info(f"Found super-normalized match for row {row_idx+1}: {row_key} -> {matched_key} (score: {best_score:.2f})")
                    used_result_keys.add(matched_key)
            
            # If we found a match, use it, otherwise skip this row
            if matched_key:
                row_results = cleaned_results_dict[matched_key]
                # Update the logged key to what we're actually using
                logger.info(f"Processing row {row_idx+1} with matched key: {matched_key}")
            else:
                logger.warning(f"No matching result key found for row {row_idx+1}, key: {row_key}")
                # Print the first few characters of each result key for comparison
                for rk in result_keys:
                    if rk not in used_result_keys:
                        logger.warning(f"  Available key: {rk[:50]}...")
                continue
        
        # Reasons worksheet
        if 'holistic_validation' in row_results:
            holistic_data = row_results['holistic_validation']
            if isinstance(holistic_data, dict):
                overall_confidence = holistic_data.get('overall_confidence', '')
                reasons_worksheet.write(reasons_row, 0, row_idx + 1)
                reasons_worksheet.write(reasons_row, 1, overall_confidence)
        
        if 'next_check' in row_results:
            next_check = row_results['next_check']
            reasons_worksheet.write(reasons_row, 2, next_check)
        
        if 'reasons' in row_results:
            reasons = row_results['reasons']
            reasons_text = "\n".join(reasons) if isinstance(reasons, list) else str(reasons)
            reasons_worksheet.write(reasons_row, 3, reasons_text, wrap_format)
            reasons_row += 1
        
        row_note = ""
        
        for col_name, result in row_results.items():
            if col_name in ['holistic_validation', 'next_check', 'reasons', '_raw_responses']:
                continue
            
            # Try direct match first
            if col_name in result_df.columns:
                excel_col = col_name
            else:
                # Try to find the column with normalization
                excel_col = match_column(col_name, result_df.columns)
            
            if not excel_col or excel_col not in result_df.columns:
                logger.warning(f"Column {col_name} not found in result_df.columns, skipping.")
                continue
            
            # Get the column index in the result_df
            col_idx = result_df.columns.get_loc(excel_col)
            
            # Extract values from the result based on its type
            validated_value = None
            confidence_level = None
            quote = None
            sources = None
            update_req = False
            reasoning = ""
            original_value = result_df.iloc[row_idx][excel_col]
            
            if isinstance(result, dict):
                validated_value = result.get('value', '')
                confidence_level = result.get('confidence_level', 'MEDIUM')
                sources = result.get('sources', [])
                quote = result.get('quote', '')
                update_req = result.get('update_required', False)
                reasoning = result.get('reasoning', '')
            elif isinstance(result, tuple) and len(result) >= 4:
                validated_value = result[0]
                # Skip confidence_numeric (index 1)
                sources = result[2]
                confidence_level = result[3]
                quote = result[4] if len(result) > 4 else ""
                update_req = result[6] if len(result) > 6 else False
                reasoning = result[5] if len(result) > 5 else ""
            
            # Make all values safe for Excel
            safe_validated = safe_for_excel(validated_value)
            safe_confidence_level = safe_for_excel(confidence_level)
            safe_sources = [safe_for_excel(s) for s in sources] if isinstance(sources, list) else safe_for_excel(sources)
            safe_quote = safe_for_excel(quote)
            safe_reasoning = safe_for_excel(reasoning)
            safe_original = safe_for_excel(original_value)
            
            # Log what we're about to write for debugging
            logger.info(f"Writing to cell ({row_idx+1}, {col_idx}) column '{excel_col}': value='{safe_validated}', confidence={safe_confidence_level}")
            
            # Write value
            worksheet.write(row_idx + 1, col_idx, safe_validated)
            
            # Skip ID columns when adding cell comments and row notes
            is_id_column = False
            for target in config.get('validation_targets', []):
                if target.get('column') == excel_col and target.get('importance', '').upper() == 'ID':
                    is_id_column = True
                    break
            
            # Add comment with quote if available, but only for non-ID columns
            if safe_quote and not is_id_column:
                # Just show the quote without the "Quote:" prefix
                comment_text = f"\"{safe_quote}\""
                if safe_sources:
                    if isinstance(safe_sources, list):
                        source_text = "\n\nSources: " + ", ".join([s for s in safe_sources if s])
                    else:
                        source_text = "\n\nSources: " + str(safe_sources)
                    comment_text += source_text
                worksheet.write_comment(row_idx + 1, col_idx, comment_text, {'width': 300, 'height': 150})
            
            # Apply confidence-based formatting - do this AFTER writing the value
            # Skip coloring for ID columns and UNDEFINED confidence level
            if not is_id_column and safe_confidence_level != "UNDEFINED":
                if safe_confidence_level == "HIGH":
                    worksheet.write(row_idx + 1, col_idx, safe_validated, high_confidence)
                elif safe_confidence_level == "MEDIUM":
                    worksheet.write(row_idx + 1, col_idx, safe_validated, medium_confidence)
                elif safe_confidence_level == "LOW":
                    worksheet.write(row_idx + 1, col_idx, safe_validated, low_confidence)
            
            if update_req and not is_id_column:
                worksheet.write(row_idx + 1, col_idx, safe_validated, update_required)
            
            # Add to row note for comment, but only for non-ID columns
            if safe_quote and not is_id_column:
                # Just show the quote without the "Quote:" prefix
                comment_text = f"\"{safe_quote}\""
                row_note += f"\n{excel_col}: {comment_text}\n"
            
            # Add to detailed view
            detail_worksheet.write(detail_row, 0, row_idx + 1)
            detail_worksheet.write(detail_row, 1, excel_col)
            
            # Handle potential NaN/Infinity values for Excel
            safe_original = safe_for_excel(original_value)
            
            detail_worksheet.write(detail_row, 2, safe_original)
            detail_worksheet.write(detail_row, 3, safe_validated)
            
            # Apply formatting to confidence level in detailed view
            if is_id_column:
                # For ID columns, show "ID" instead of confidence level
                detail_worksheet.write(detail_row, 4, "ID")
            else:
                # For non-ID columns, apply confidence level formatting
                if safe_confidence_level == "UNDEFINED":
                    # No formatting for UNDEFINED confidence
                    detail_worksheet.write(detail_row, 4, safe_confidence_level)
                elif safe_confidence_level == "HIGH":
                    detail_worksheet.write(detail_row, 4, safe_confidence_level, high_confidence)
                elif safe_confidence_level == "MEDIUM":
                    detail_worksheet.write(detail_row, 4, safe_confidence_level, medium_confidence)
                elif safe_confidence_level == "LOW":
                    detail_worksheet.write(detail_row, 4, safe_confidence_level, low_confidence)
            
            # Update required indicator
            if is_id_column:
                # ID columns are never marked as needing updates
                detail_worksheet.write(detail_row, 5, "No")
            else:
                detail_worksheet.write(detail_row, 5, "Yes" if update_req else "No")
                if update_req:
                    detail_worksheet.write(detail_row, 5, "Yes", update_required)
            
            sources_text = "; ".join(safe_sources) if isinstance(safe_sources, list) else str(safe_sources)
            detail_worksheet.write(detail_row, 6, sources_text, wrap_format)
            
            if safe_quote:
                # Just show the quote without the "Quote:" prefix
                comment_text = f"\"{safe_quote}\""
                detail_worksheet.write(detail_row, 7, comment_text, wrap_format)
            else:
                detail_worksheet.write(detail_row, 7, "")
            
            detail_worksheet.write(detail_row, 8, safe_reasoning, wrap_format)
            detail_row += 1
        
        # Add a summary comment to the row's primary key cell
        # Only add if we have notes AND primary key is not itself an ID column
        if row_note != "" and primary_keys and primary_keys[0] in result_df.columns:
            pk_idx = result_df.columns.get_loc(primary_keys[0])
            
            # Check if primary key is an ID column
            pk_is_id = False
            for target in config.get('validation_targets', []):
                if target.get('column') == primary_keys[0] and target.get('importance', '').upper() == 'ID':
                    pk_is_id = True
                    break
            
            # Only add comment if primary key isn't an ID column
            if not pk_is_id:
                worksheet.write_comment(row_idx + 1, pk_idx, row_note, {'width': 400, 'height': 200})
    
    worksheet.autofilter(0, 0, len(result_df), len(result_df.columns) - 1)
    detail_worksheet.autofilter(0, 0, detail_row - 1, len(detail_headers) - 1)
    reasons_worksheet.autofilter(0, 0, reasons_row - 1, len(reasons_headers) - 1)
    
    # Final stats for debugging
    logger.info(f"Added {detail_row-1} rows to detailed view")
    logger.info(f"Added {reasons_row-1} rows to reasons view")

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