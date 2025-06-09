#!/usr/bin/env python3
"""
Applies all the needed history changes to lambda_test_json_clean.py
"""
import re
import sys
from pathlib import Path

def main():
    """
    Apply the following changes to lambda_test_json_clean.py:
    1. Add date_format variable
    2. Add history worksheet creation
    3. Add history_row variable
    4. Add extraction of validation history from results
    5. Add history worksheet processing
    6. Add history worksheet autofilter and stats
    """
    file_path = Path('src/lambda_test_json_clean.py')
    
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        return 1

    # Read the content
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Add date_format variable
    if "date_format = workbook.add_format({'num_format': 'yyyy-mm-dd'})" not in content:
        print("Adding date_format variable...")
        wrap_format_pattern = r'(\s+wrap_format = workbook\.add_format\({\'text_wrap\': True}\))'
        date_format_code = r'\1\n        date_format = workbook.add_format({\'num_format\': \'yyyy-mm-dd\'})'
        content = re.sub(wrap_format_pattern, date_format_code, content)
    
    # 2. Add history worksheet creation
    if "history_worksheet = workbook.add_worksheet('History')" not in content:
        print("Adding history worksheet creation...")
        reasons_pattern = r"""(\s+# Create Reasons worksheet.*?
        reasons_worksheet\.set_column\(3, 3, 100\))"""
        
        history_worksheet_code = r"""\1
        
        # Create History worksheet
        try:
            history_worksheet = writer.book.get_worksheet_by_name('History')
            # If it exists, clear it first
            history_worksheet.clear()
        except (AttributeError, ValueError):
            # Sheet doesn't exist or can't be accessed, create a new one
            history_worksheet = workbook.add_worksheet('History')
        
        # Set up history worksheet headers
        history_headers = ["Row Key", "Field", "Date", "Value", "Confidence", "Quote", "Sources"]
        for col_num, header in enumerate(history_headers):
            history_worksheet.write(0, col_num, header, header_format)
        
        # Set column widths for history worksheet
        history_worksheet.set_column(0, 0, 40)  # Row key
        history_worksheet.set_column(1, 1, 20)  # Field
        history_worksheet.set_column(2, 2, 15)  # Date
        history_worksheet.set_column(3, 3, 40)  # Value
        history_worksheet.set_column(4, 4, 15)  # Confidence
        history_worksheet.set_column(5, 5, 50)  # Quote
        history_worksheet.set_column(6, 6, 50)  # Sources"""
        
        content = re.sub(reasons_pattern, history_worksheet_code, content, flags=re.DOTALL)
    
    # 3. Add history_row variable
    if "history_row = 1" not in content:
        print("Adding history_row variable...")
        detail_row_pattern = r'(\s+detail_row = 1\s+reasons_row = 1)'
        history_row_code = r'\1\n        history_row = 1'
        content = re.sub(detail_row_pattern, history_row_code, content)
    
    # 4. Add extraction of validation history from results
    if "# Extract validation history from results_dict" not in content:
        print("Adding extraction of validation history...")
        extract_pattern = r'(\s+# Log all result keys for debugging\s+logger.info\(f"Result keys available: {result_keys}"\))'
        
        extract_code = r"""\1
        
        # Extract validation history from results_dict for later use
        validation_history = {}
        for row_key, row_data in cleaned_results_dict.items():
            if 'validation_history' in row_data:
                validation_history[row_key] = row_data['validation_history']
                # Remove from cleaned results to avoid duplication
                del cleaned_results_dict[row_key]['validation_history']"""
                
        content = re.sub(extract_pattern, extract_code, content)
    
    # 5. Add history worksheet processing
    if "# Process validation history for this row" not in content:
        print("Adding history worksheet processing...")
        pk_pattern = r"""(\s+# Add a summary comment to the row's primary key cell.*?
                    except Exception as pk_comment_error:
                        logger\.error\(f"Error writing primary key comment: {str\(pk_comment_error\)}".*?\n)"""
        
        history_code = r"""\1
            
            # Process validation history for this row if available
            if matched_key in validation_history:
                row_history = validation_history[matched_key]
                
                # For each column with history, add entries to the History tab
                for column, history_entries in row_history.items():
                    for entry in history_entries:
                        try:
                            # Extract data from history entry
                            timestamp = entry.get('timestamp', '')
                            value = entry.get('value', '')
                            confidence_level = entry.get('confidence_level', '')
                            quote = entry.get('quote', '')
                            sources = entry.get('sources', [])
                            
                            # Write history entry to the History worksheet
                            history_worksheet.write(history_row, 0, matched_key)
                            history_worksheet.write(history_row, 1, column)
                            
                            # Try to parse the timestamp as datetime if possible
                            try:
                                if isinstance(timestamp, str) and timestamp:
                                    dt_timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                    history_worksheet.write_datetime(history_row, 2, dt_timestamp, date_format)
                                else:
                                    history_worksheet.write(history_row, 2, str(timestamp))
                            except (ValueError, TypeError):
                                # If timestamp can't be parsed, just write it as a string
                                history_worksheet.write(history_row, 2, str(timestamp))
                            
                            # Write the rest of the fields
                            history_worksheet.write(history_row, 3, str(value))
                            
                            # Apply confidence formatting
                            if confidence_level == "HIGH":
                                history_worksheet.write(history_row, 4, confidence_level, high_confidence)
                            elif confidence_level == "MEDIUM":
                                history_worksheet.write(history_row, 4, confidence_level, medium_confidence)
                            elif confidence_level == "LOW":
                                history_worksheet.write(history_row, 4, confidence_level, low_confidence)
                            else:
                                history_worksheet.write(history_row, 4, str(confidence_level))
                            
                            # Write quote and sources
                            if quote:
                                # Truncate if needed
                                if isinstance(quote, str) and len(quote) > 1000:
                                    quote_text = quote[:1000] + "..."
                                else:
                                    quote_text = quote
                                history_worksheet.write(history_row, 5, quote_text, wrap_format)
                            else:
                                history_worksheet.write(history_row, 5, "")
                            
                            # Format sources as a string
                            if isinstance(sources, list):
                                sources_text = "; ".join(sources[:3])
                                if len(sources) > 3:
                                    sources_text += f" (+{len(sources) - 3} more)"
                            else:
                                sources_text = str(sources)
                            history_worksheet.write(history_row, 6, sources_text)
                            
                            history_row += 1
                        except Exception as history_error:
                            logger.error(f"Error writing history entry: {str(history_error)}")"""
                            
        content = re.sub(pk_pattern, history_code, content, flags=re.DOTALL)
    
    # 6. Add history worksheet autofilter and stats
    if "history_worksheet.autofilter" not in content:
        print("Adding history worksheet autofilter and stats...")
        filter_pattern = r"""(\s+# Try adding autofilter.*?
        logger\.info\(f"Added {reasons_row-1} rows to reasons view"\))"""
        
        autofilter_code = r"""\1
    
    try:
        history_worksheet.autofilter(0, 0, history_row - 1, len(history_headers) - 1)
    except Exception as history_filter_error:
        logger.error(f"Error adding autofilter to history worksheet: {str(history_filter_error)}")
        
    # Log history stats
    logger.info(f"Added {history_row-1} rows to history view")"""
        
        content = re.sub(filter_pattern, autofilter_code, content, flags=re.DOTALL)
    
    # Write the changes back to the file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Successfully applied all history changes to lambda_test_json_clean.py")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 