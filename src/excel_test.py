#!/usr/bin/env python3
"""
Simplified test script for Excel formatting without any Lambda dependency.
Reads the Excel file directly and writes back with proper formatting.
"""

import os
import pandas as pd
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def normalize_column_name(col):
    """Normalize column name for comparison."""
    if col is None:
        return ""
    
    # Convert to lowercase and remove common separators/spaces
    norm = str(col).lower()
    
    # Replace non-breaking space with regular space
    norm = norm.replace('\xa0', ' ')
    
    # Replace other special characters
    norm = norm.replace('\u2011', '-')  # Non-breaking hyphen
    norm = norm.replace('\u2012', '-')  # Figure dash
    norm = norm.replace('\u2013', '-')  # En dash
    norm = norm.replace('\u2014', '-')  # Em dash
    norm = norm.replace('\u2015', '-')  # Horizontal bar
    
    # Remove all spaces, hyphens, and underscores
    norm = norm.replace(" ", "").replace("-", "").replace("_", "")
    norm = norm.replace("/", "").replace("\\", "").replace(".", "")
    norm = norm.replace("(", "").replace(")", "").replace(",", "")
    
    return norm

def create_test_data():
    """Create a simple test data structure for the Excel formatting test."""
    # Example columns that would cause issues with non-breaking spaces
    test_data = {
        "RTX-1363S||Ratio Therapeutics / Lantheus||FAP": {
            "Product Name": {"value": "RTX-1363S", "confidence": 0.95, "confidence_level": "HIGH", "sources": ["https://ratiotherapeutics.com/pipeline/"], "quote": "RTX-1363S is a FAP-targeted PET tracer", "update_required": False},
            "Developer": {"value": "Ratio Therapeutics / Lantheus", "confidence": 0.95, "confidence_level": "HIGH", "sources": ["https://ratiotherapeutics.com/pipeline/"], "quote": "Co-developed by Ratio Therapeutics and Lantheus", "update_required": False},
            "Target": {"value": "FAP", "confidence": 0.95, "confidence_level": "HIGH", "sources": ["https://ratiotherapeutics.com/pipeline/"], "quote": "FAP-targeted PET tracer", "update_required": False},
            "Indication": {"value": "Solid tumors", "confidence": 0.95, "confidence_level": "HIGH", "sources": ["https://ratiotherapeutics.com/pipeline/"], "quote": "For diagnosis of solid tumors", "update_required": False},
            "Therapeutic Radionuclide": {"value": "-", "confidence": 0.95, "confidence_level": "HIGH", "sources": ["https://ratiotherapeutics.com/pipeline/"], "quote": "Diagnostic agent only", "update_required": False},
            "Diagnostic Radionuclide": {"value": "Cu-64", "confidence": 0.95, "confidence_level": "HIGH", "sources": ["https://ratiotherapeutics.com/pipeline/"], "quote": "Cu-64 labeled PET tracer", "update_required": False},
            "Modality Type": {"value": "PET Imaging Agent", "confidence": 0.95, "confidence_level": "HIGH", "sources": ["https://ratiotherapeutics.com/pipeline/"], "quote": "RTX-1363S is a FAP-targeted PET tracer", "update_required": False},
            "Development Stage": {"value": "Phase 1", "confidence": 0.95, "confidence_level": "HIGH", "sources": ["https://ratiotherapeutics.com/pipeline/"], "quote": "Phase 1 clinical trial", "update_required": False},
            "Key Trial ID": {"value": "NCT05621941", "confidence": 0.95, "confidence_level": "HIGH", "sources": ["https://clinicaltrials.gov/study/NCT05621941"], "quote": "NCT05621941", "update_required": False},
            "Projected Launch": {"value": "2027", "confidence": 0.8, "confidence_level": "MEDIUM", "sources": ["https://ratiotherapeutics.com/news/"], "quote": "Projected market launch in 2027", "update_required": False},
            "FDA-EMA Designation": {"value": "-", "confidence": 0.95, "confidence_level": "HIGH", "sources": ["https://ratiotherapeutics.com/pipeline/"], "quote": "No special designation reported", "update_required": False},
            "Strategic Partners": {"value": "Lantheus", "confidence": 0.95, "confidence_level": "HIGH", "sources": ["https://ratiotherapeutics.com/partners/"], "quote": "Strategic partnership with Lantheus", "update_required": False},
            "Recent News": {"value": "First patient dosed in Phase 1 study", "confidence": 0.95, "confidence_level": "HIGH", "sources": ["https://ratiotherapeutics.com/news/"], "quote": "05/15/2024: First patient dosed in Phase 1 study", "update_required": False},
            "holistic_validation": {"overall_confidence": "HIGH"},
            "next_check": "2025-08-21",
            "reasons": ["Most data validated with high confidence"]
        }
    }
    return test_data

def format_excel(input_file, output_file=None):
    """Read Excel file and write back with proper formatting."""
    try:
        # Generate output filename if not provided
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"tables/RatioCompetitiveIntelligence/RatioCompetitiveIntelligence_test_{timestamp}.xlsx"
        
        # Read the Excel file
        logger.info(f"Reading Excel file: {input_file}")
        df = pd.read_excel(input_file)
        logger.info(f"Read DataFrame with {len(df)} rows and {len(df.columns)} columns")
        
        # List all columns to identify non-breaking spaces
        all_columns = list(df.columns)
        logger.info(f"Original columns: {all_columns}")
        
        # Identify columns with non-breaking spaces
        nonbreaking_space_cols = [col for col in all_columns if '\xa0' in str(col)]
        logger.info(f"Columns with non-breaking spaces: {nonbreaking_space_cols}")
        
        # Create a mapping for column renaming
        column_mapping = {}
        for col in nonbreaking_space_cols:
            new_col = col.replace('\xa0', ' ')
            column_mapping[col] = new_col
            logger.info(f"Will rename '{col}' to '{new_col}'")
        
        # Rename columns with non-breaking spaces
        if column_mapping:
            df = df.rename(columns=column_mapping)
            logger.info(f"Renamed columns: {list(df.columns)}")
        
        # Remove duplicate columns (keep first occurrence)
        df = df.loc[:, ~df.columns.duplicated()]
        logger.info(f"After removing duplicates: {list(df.columns)}")
        
        # Create test data
        test_data = create_test_data()
        logger.info(f"Created test data with {len(test_data)} rows")
        
        # Use pandas ExcelWriter with xlsxwriter engine
        writer = pd.ExcelWriter(output_file, engine='xlsxwriter')
        
        # Write the cleaned dataframe to Excel
        df.to_excel(writer, sheet_name='Main View', index=False)
        logger.info(f"Wrote DataFrame to Excel")
        
        # Get the workbook and worksheet objects
        workbook = writer.book
        worksheet = writer.sheets['Main View']
        
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
        
        # Format the header row
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            max_len = max(
                df[value].astype(str).apply(len).max() if not df[value].empty else 0,
                len(str(value))
            ) + 2
            worksheet.set_column(col_num, col_num, max_len)
        
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
        
        # Variables for tracking rows in detailed view and reasons worksheets
        detail_row = 1
        reasons_row = 1
        
        # Process only the first row for this test
        row_idx = 0
        
        # Get the row key - use the combined values of first 3 columns
        row_key = "||".join([
            str(df.iloc[row_idx][df.columns[0]]),
            str(df.iloc[row_idx][df.columns[1]]),
            str(df.iloc[row_idx][df.columns[2]])
        ])
        logger.info(f"Using row key: {row_key}")
        
        # For this test, use the first key in our test data
        test_key = list(test_data.keys())[0]
        row_results = test_data[test_key]
        logger.info(f"Using test data with columns: {[k for k in row_results.keys() if k not in ['holistic_validation', 'next_check', 'reasons']]}")
        
        # Process the reasons data
        if 'holistic_validation' in row_results:
            holistic_data = row_results['holistic_validation']
            if isinstance(holistic_data, dict):
                overall_confidence = holistic_data.get('overall_confidence', '')
                reasons_worksheet.write(reasons_row, 0, row_idx + 1)
                reasons_worksheet.write(reasons_row, 1, overall_confidence)
                logger.info(f"Wrote overall confidence: {overall_confidence}")
        
        if 'next_check' in row_results:
            next_check = row_results['next_check']
            reasons_worksheet.write(reasons_row, 2, next_check)
            logger.info(f"Wrote next check: {next_check}")
        
        if 'reasons' in row_results:
            reasons = row_results['reasons']
            reasons_text = "\n".join(reasons) if isinstance(reasons, list) else str(reasons)
            reasons_worksheet.write(reasons_row, 3, reasons_text, wrap_format)
            logger.info(f"Wrote reasons: {reasons_text}")
            reasons_row += 1
        
        # Process each column in the results
        for col_name, result in row_results.items():
            # Skip special fields
            if col_name in ['holistic_validation', 'next_check', 'reasons']:
                continue
            
            # Find the matching column in the DataFrame
            excel_col = None
            if col_name in df.columns:
                excel_col = col_name
                logger.info(f"Found exact match for column: {col_name}")
            else:
                # Try to find a normalized match
                col_norm = normalize_column_name(col_name)
                for df_col in df.columns:
                    if normalize_column_name(df_col) == col_norm:
                        excel_col = df_col
                        logger.info(f"Found normalized match for column: {col_name} -> {df_col}")
                        break
            
            if not excel_col:
                logger.warning(f"Column not found: {col_name}")
                continue
            
            # Get the column index
            col_idx = df.columns.get_loc(excel_col)
            logger.info(f"Column {excel_col} is at index {col_idx}")
            
            # Extract values from the result
            validated_value = result.get('value', '')
            confidence_numeric = result.get('confidence', 0.0)
            confidence_level = result.get('confidence_level', 'MEDIUM')
            sources = result.get('sources', [])
            quote = result.get('quote', '')
            update_req = result.get('update_required', False)
            reasoning = result.get('reasoning', '')
            
            # Write to the main worksheet
            logger.info(f"Writing {validated_value} to cell ({row_idx+1}, {col_idx})")
            worksheet.write(row_idx + 1, col_idx, validated_value)
            
            # Add comment with quote if available
            if quote:
                comment_text = f"Quote: \"{quote}\""
                if sources:
                    source_text = "\n\nSources: " + ", ".join(sources)
                    comment_text += source_text
                worksheet.write_comment(row_idx + 1, col_idx, comment_text, {'width': 300, 'height': 150})
                logger.info(f"Added comment to cell ({row_idx+1}, {col_idx})")
            
            # Apply confidence-based formatting - do this AFTER writing the value
            if confidence_level == "HIGH":
                worksheet.write(row_idx + 1, col_idx, validated_value, high_confidence)
                logger.info(f"Applied HIGH confidence formatting to cell ({row_idx+1}, {col_idx})")
            elif confidence_level == "MEDIUM":
                worksheet.write(row_idx + 1, col_idx, validated_value, medium_confidence)
                logger.info(f"Applied MEDIUM confidence formatting to cell ({row_idx+1}, {col_idx})")
            elif confidence_level == "LOW":
                worksheet.write(row_idx + 1, col_idx, validated_value, low_confidence)
                logger.info(f"Applied LOW confidence formatting to cell ({row_idx+1}, {col_idx})")
            
            # Apply update required formatting if needed
            if update_req:
                worksheet.write(row_idx + 1, col_idx, validated_value, update_required)
                logger.info(f"Applied UPDATE REQUIRED formatting to cell ({row_idx+1}, {col_idx})")
            
            # Add to detailed view
            original_value = df.iloc[row_idx][excel_col]
            detail_worksheet.write(detail_row, 0, row_idx + 1)
            detail_worksheet.write(detail_row, 1, excel_col)
            detail_worksheet.write(detail_row, 2, original_value)
            detail_worksheet.write(detail_row, 3, validated_value)
            detail_worksheet.write(detail_row, 4, confidence_numeric)
            detail_worksheet.write(detail_row, 5, confidence_level)
            
            # Apply confidence-based formatting to the detailed view
            if confidence_level == "HIGH":
                detail_worksheet.write(detail_row, 5, confidence_level, high_confidence)
            elif confidence_level == "MEDIUM":
                detail_worksheet.write(detail_row, 5, confidence_level, medium_confidence)
            elif confidence_level == "LOW":
                detail_worksheet.write(detail_row, 5, confidence_level, low_confidence)
            
            # Update required in detailed view
            detail_worksheet.write(detail_row, 6, "Yes" if update_req else "No")
            if update_req:
                detail_worksheet.write(detail_row, 6, "Yes", update_required)
            
            # Sources
            sources_text = "; ".join(sources) if isinstance(sources, list) else str(sources)
            detail_worksheet.write(detail_row, 7, sources_text, wrap_format)
            
            # Quote
            if quote:
                quote_text = f"\"{quote}\""
                detail_worksheet.write(detail_row, 8, quote_text, wrap_format)
            else:
                detail_worksheet.write(detail_row, 8, "")
            
            # Reasoning
            detail_worksheet.write(detail_row, 9, reasoning, wrap_format)
            
            logger.info(f"Added row to detailed view for column {excel_col}")
            detail_row += 1
        
        # Add autofilters
        worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)
        detail_worksheet.autofilter(0, 0, detail_row - 1, len(detail_headers) - 1)
        reasons_worksheet.autofilter(0, 0, reasons_row - 1, len(reasons_headers) - 1)
        
        # Save the Excel file
        writer.close()
        logger.info(f"Saved Excel file to {output_file}")
        
        return output_file
    
    except Exception as e:
        logger.error(f"Error formatting Excel: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    # Use the clean file as input
    input_file = "tables/RatioCompetitiveIntelligence/RatioCompetitiveIntelligence.xlsx"
    format_excel(input_file) 