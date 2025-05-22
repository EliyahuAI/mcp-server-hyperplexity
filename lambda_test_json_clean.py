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
        logger.info("Invoking Lambda function...")
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
        
        # Use pandas ExcelWriter with xlsxwriter engine
        writer = pd.ExcelWriter(output_path, engine='xlsxwriter')
        
        # Create a copy of the original DataFrame to avoid modifying the input
        result_df = df.copy()
        
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
        worksheet = writer.sheets['Main View']
        
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
        detail_worksheet = workbook.add_worksheet('Detailed View')
        detail_headers = [
            "Row", "Column", "Original Value", "Validated Value", "Confidence",
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
        detail_worksheet.set_column(6, 6, 15)
        detail_worksheet.set_column(7, 7, 50)
        detail_worksheet.set_column(8, 8, 50)
        detail_worksheet.set_column(9, 9, 80)
        
        # Create Reasons worksheet
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
                        if part_norm and part_norm not in normalize_column_name(result_key):
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
                    
                    # Extract chemical elements (typically 2-3 letters possibly with numbers)
                    elements = re.findall(r'(?:[A-Z][a-z]?|[0-9]{1,3}[A-Z][a-z]?)', product_name)
                    identifiers.extend(elements)
                    
                    # Extract any sequence of 3+ letters (could be targets, etc.)
                    words = re.findall(r'[A-Za-z]{3,}', product_name)
                    identifiers.extend(words)
                    
                    # Special case for common prefixes/formats in radiopharmaceuticals
                    if 'Cu' in product_name or '64Cu' in product_name or 'RTX' in product_name:
                        identifiers.extend(['Cu', 'RTX', '64Cu'])
                    
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
            
            row_note = "Validation Notes:\n"
            
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
                confidence_numeric = None
                original_value = result_df.iloc[row_idx][excel_col]
                
                if isinstance(result, dict):
                    validated_value = result.get('value', '')
                    confidence_numeric = result.get('confidence', 0.0)
                    confidence_level = result.get('confidence_level', 'MEDIUM')
                    sources = result.get('sources', [])
                    quote = result.get('quote', '')
                    update_req = result.get('update_required', False)
                    reasoning = result.get('reasoning', '')
                elif isinstance(result, tuple) and len(result) >= 4:
                    validated_value = result[0]
                    confidence_numeric = result[1]
                    sources = result[2]
                    confidence_level = result[3]
                    quote = result[4] if len(result) > 4 else ""
                    update_req = result[6] if len(result) > 6 else False
                    reasoning = result[5] if len(result) > 5 else ""
                
                # Log what we're about to write for debugging
                logger.info(f"Writing to cell ({row_idx+1}, {col_idx}) column '{excel_col}': value='{validated_value}', confidence={confidence_level}")
                
                # Write value
                worksheet.write(row_idx + 1, col_idx, validated_value)
                
                # Add comment with quote if available
                if quote:
                    comment_text = f"Quote: \"{quote}\""
                    if sources:
                        source_text = "\n\nSources: " + ", ".join(sources)
                        comment_text += source_text
                    worksheet.write_comment(row_idx + 1, col_idx, comment_text, {'width': 300, 'height': 150})
                
                # Apply confidence-based formatting - do this AFTER writing the value
                if confidence_level == "HIGH":
                    worksheet.write(row_idx + 1, col_idx, validated_value, high_confidence)
                elif confidence_level == "MEDIUM":
                    worksheet.write(row_idx + 1, col_idx, validated_value, medium_confidence)
                elif confidence_level == "LOW":
                    worksheet.write(row_idx + 1, col_idx, validated_value, low_confidence)
                
                if update_req:
                    worksheet.write(row_idx + 1, col_idx, validated_value, update_required)
                
                # Add to detailed view
                detail_worksheet.write(detail_row, 0, row_idx + 1)
                detail_worksheet.write(detail_row, 1, excel_col)
                detail_worksheet.write(detail_row, 2, original_value)
                detail_worksheet.write(detail_row, 3, validated_value)
                detail_worksheet.write(detail_row, 4, confidence_numeric)
                detail_worksheet.write(detail_row, 5, confidence_level)
                
                # Apply formatting to confidence level in detailed view
                if confidence_level == "HIGH":
                    detail_worksheet.write(detail_row, 5, confidence_level, high_confidence)
                elif confidence_level == "MEDIUM":
                    detail_worksheet.write(detail_row, 5, confidence_level, medium_confidence)
                elif confidence_level == "LOW":
                    detail_worksheet.write(detail_row, 5, confidence_level, low_confidence)
                
                detail_worksheet.write(detail_row, 6, "Yes" if update_req else "No")
                if update_req:
                    detail_worksheet.write(detail_row, 6, "Yes", update_required)
                
                sources_text = "; ".join(sources) if isinstance(sources, list) else str(sources)
                detail_worksheet.write(detail_row, 7, sources_text, wrap_format)
                
                if quote:
                    quote_text = f"\"{quote}\""
                    detail_worksheet.write(detail_row, 8, quote_text, wrap_format)
                else:
                    detail_worksheet.write(detail_row, 8, "")
                
                detail_worksheet.write(detail_row, 9, reasoning, wrap_format)
                detail_row += 1
                
                # Add to row note for comment
                if quote:
                    row_note += f"\n{excel_col}: \"{quote}\"\n"
            
            # Add a summary comment to the row's primary key cell
            if row_note != "Validation Notes:\n" and primary_keys and primary_keys[0] in result_df.columns:
                pk_idx = result_df.columns.get_loc(primary_keys[0])
                worksheet.write_comment(row_idx + 1, pk_idx, row_note, {'width': 400, 'height': 200})
        
        worksheet.autofilter(0, 0, len(result_df), len(result_df.columns) - 1)
        detail_worksheet.autofilter(0, 0, detail_row - 1, len(detail_headers) - 1)
        reasons_worksheet.autofilter(0, 0, reasons_row - 1, len(reasons_headers) - 1)
        
        # Final stats for debugging
        logger.info(f"Added {detail_row-1} rows to detailed view")
        logger.info(f"Added {reasons_row-1} rows to reasons view")
        
        writer.close()
        logger.info(f"Results saved to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error saving results to Excel: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

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
        args = parser.parse_args()
        
        # Load config from the JSON file
        logger.info(f"Loading configuration from: {args.config}")
        config = load_config_file(args.config)
        
        # Load Excel data
        logger.info(f"Loading data from: {args.input}")
        df = load_excel_data(args.input)
        
        # Take the specified number of rows
        test_df = df.head(args.rows)
        logger.info(f"Testing with {len(test_df)} rows")
        
        # Process each row
        all_results = {}
        for index, row in test_df.iterrows():
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
            
            # Save payload for debugging
            with open(f"lambda_payload_row_{index+1}.json", "w") as f:
                json.dump(payload, f, indent=2)
            
            # Invoke Lambda function
            response = invoke_lambda(payload)
            
            # Save the raw response for debugging
            with open(f"lambda_response_row_{index+1}.json", "w") as f:
                json.dump(response, f, indent=2)
            
            # Process response
            results = process_lambda_response(response, row_data, row_key)
            if results:
                # Merge into all_results
                all_results.update(results)
                logger.info(f"Added results for row {index+1}")
            
            # Add a delay to avoid rate limiting
            time.sleep(1)
        
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
    except Exception as e:
        logger.error(f"Error in test: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 