#!/usr/bin/env python3
"""
Adds history processing implementation to lambda_test_json_clean.py
"""
import sys
import re
from pathlib import Path

# The history processing code we want to insert
history_processing_code = '''
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
                            logger.error(f"Error writing history entry: {str(history_error)}")
'''

def main():
    """Edit the lambda_test_json_clean.py file to add history processing"""
    file_path = Path('src/lambda_test_json_clean.py')
    
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        return 1
    
    # Read the file content
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Find a suitable location to insert the history processing code
    # We want to add it at the end of the row processing loop, before starting a new row
    insert_pattern = r"""            # Add a summary comment to the row's primary key cell
            # Only add if we have notes AND primary key is not itself an ID column
            if row_note != "" and primary_keys and primary_keys\[0\] in result_df\.columns:
                pk_idx = result_df\.columns\.get_loc\(primary_keys\[0\]\)
                
                # Check if primary key is an ID column
                pk_is_id = False
                for target in config\.get\('validation_targets', \[\]\):
                    if target\.get\('column'\) == primary_keys\[0\] and target\.get\('importance', ''\)\.upper\(\) == 'ID':
                        pk_is_id = True
                        break
                
                # Only add comment if primary key isn't an ID column
                if not pk_is_id:
                    # Truncate row note if it's too long
                    if len\(row_note\) > MAX_COMMENT_LENGTH:
                        row_note = row_note\[:MAX_COMMENT_LENGTH\] \+ "\.\.\."
                    
                    try:
                        worksheet\.write_comment\(row_idx \+ 1, pk_idx, row_note, \{'width': 400, 'height': 200\}\)
                    except Exception as pk_comment_error:
                        logger\.error\(f"Error writing primary key comment: \{str\(pk_comment_error\)\}"\)"""
    
    # Check if the history processing code is already present
    if "if matched_key in validation_history:" in content:
        print("History processing code appears to be already present. No changes made.")
        return 0
    
    # Insert the history processing code
    match = re.search(insert_pattern, content)
    if match:
        print("Found insertion point, adding history processing code...")
        insertion_point = match.end()
        new_content = content[:insertion_point] + "\n" + history_processing_code + content[insertion_point:]
        
        # Write the updated content back to the file
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(new_content)
        
        print(f"Successfully added history processing code to {file_path}")
        return 0
    else:
        print("Could not find a suitable insertion point.")
        print("Please check the file and update it manually.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 