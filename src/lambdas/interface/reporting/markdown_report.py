"""
Functions for creating Markdown reports from validation results.
"""
import json
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# It's better to initialize clients once if the module is loaded.
# However, for strict lazy loading, this could be moved inside the function.
s3_client = boto3.client('s3')


def create_markdown_table_from_results(validation_results, preview_row_count=3, config_s3_key=None, s3_cache_bucket=None, qc_results=None):
    """Convert real validation results from validator Lambda to markdown table format.
    Always shows the first 3 rows in a transposed table format with confidence emojis.
    Fields are ordered by: ID fields first, then by search_group ascending, with a Search Group column at the end.
    ID fields show blue circles (🔵) with their actual values from the original Excel data.
    """
    if not validation_results:
        return "No validation results available."
    
    # Get confidence emoji mapping
    def get_confidence_emoji(confidence_level):
        confidence_map = {
            'HIGH': '🟢',
            'MEDIUM': '🟡',
            'LOW': '🔴',
            'ID': '🔵',  # Blue circle for ID fields
            'UNKNOWN': '❓'
        }
        return confidence_map.get(confidence_level, '❓')
    
    # Load config to get field information and ordering
    field_config_map = {}
    all_config_fields = []  # Preserve original order from config
    
    if config_s3_key and s3_cache_bucket:
        try:
            config_response = s3_client.get_object(Bucket=s3_cache_bucket, Key=config_s3_key)
            config_content = json.loads(config_response['Body'].read().decode('utf-8'))
            
            for target in config_content.get('validation_targets', []):
                field_name = target.get('column')
                if field_name:
                    field_config_map[field_name] = target
                    all_config_fields.append(field_name)  # Preserve order from config
        except Exception as e:
            print(f"Warning: Could not load config from {config_s3_key}: {e}")
    
    # Get first few rows based on preview_row_count
    sorted_row_keys = list(validation_results.keys())[:preview_row_count]
    
    # Get all field names from validation results
    validation_field_names = set()
    for row_key in sorted_row_keys:
        if isinstance(validation_results[row_key], dict):
            validation_field_names.update(validation_results[row_key].keys())
    
    # Create comprehensive field list: all config fields (in order), plus any extra validation fields
    field_keys = []
    
    # First, add all config fields in their original order
    for field_name in all_config_fields:
        if field_name not in field_keys:  # Avoid duplicates
            field_keys.append(field_name)
    
    # Then add any validation fields not in config (excluding internal/meta fields)
    for field_name in sorted(list(validation_field_names)): # sort for consistent order
        if field_name not in field_keys and field_name not in ['holistic_validation', 'reasons', 'next_check', '_raw_responses', 'validation_history']:
            field_keys.append(field_name)
    
    # Sort function: ID fields first, then preserve original config order
    def get_field_sort_key(field_name):
        config = field_config_map.get(field_name, {})
        importance = config.get('importance', 'MEDIUM')
        
        # Get original position in config for ordering
        try:
            config_position = all_config_fields.index(field_name)
        except ValueError:
            config_position = 9999  # Put fields not in config at the end
        
        # ID fields come first (sort key 0), then preserve original config order
        if importance == 'ID':
            return (0, config_position)
        else:
            return (1, config_position)
    
    # Sort field keys
    field_keys.sort(key=get_field_sort_key)
    
    # Create transposed table: fields as rows, data rows as columns
    table_lines = []
    
    # Add legend as a separate sentence before the table - ID first
    legend = "**Confidence Legend:** 🔵 ID/Input • 🟢 High • 🟡 Medium • 🔴 Low\n\n"
    
    # Create header row - no search group column
    header = "| Field"
    for i, row_key in enumerate(sorted_row_keys):
        row_number = i + 1
        header += f" | Row {row_number}"
    header += " |"
    table_lines.append(header)
    
    # Create separator row - no search group column
    separator = "|" + "-" * 26
    for _ in sorted_row_keys:
        separator += "|" + "-" * 31
    separator += "|"
    table_lines.append(separator)
    
    # Create data rows (one for each field)
    for field_name in field_keys:
        # Truncate long field names
        if len(field_name) > 24:
            display_field = field_name[:21] + "..."
        else:
            display_field = field_name
        
        # Escape pipe characters in field name
        display_field = display_field.replace('|', '\\|')
        
        row_line = f"| {display_field:<24}"
        
        # Check if this is an ID field
        config = field_config_map.get(field_name, {})
        is_id_field = config.get('importance') == 'ID'
        
        # Add values for each data row
        for row_key in sorted_row_keys:
            row_results = validation_results[row_key]
            field_result = row_results.get(field_name, {})
            
            if isinstance(field_result, dict) and field_result:
                # Check for QC data first (highest priority) but hide QC visibility from user
                confidence = field_result.get('confidence_level', 'UNKNOWN')
                value = field_result.get('value', '')

                # Check if QC results are available and override validation data (behind the scenes)
                if qc_results and row_key in qc_results:
                    row_qc_data = qc_results[row_key]
                    if field_name in row_qc_data:
                        field_qc_data = row_qc_data[field_name]
                        if isinstance(field_qc_data, dict) and field_qc_data.get('qc_applied', False):
                            # Use QC data when available, but display as normal validation
                            qc_confidence = field_qc_data.get('qc_confidence', '')
                            qc_value = field_qc_data.get('qc_entry', '')
                            if qc_confidence:
                                confidence = qc_confidence
                            if qc_value:
                                value = qc_value

                # Get confidence emoji (use normal validation style - no QC indicators visible to user)
                emoji = get_confidence_emoji(confidence)

                # Prepare value with emoji prefix
                if value:
                    display_value = f"{emoji} {value}"
                else:
                    display_value = f"{emoji} (empty)"
                
            else:
                # Field not in validation results - show N/A
                display_value = "N/A"
            
            # Truncate long values, but preserve URLs as clickable links
            if len(str(display_value)) > 29:
                # Check if the value contains a URL
                import re
                url_pattern = r'https?://[^\s]+'
                url_match = re.search(url_pattern, str(display_value))

                if url_match:
                    # Extract the URL
                    full_url = url_match.group()
                    # Create a clickable markdown link with truncated display text
                    truncated_text = str(display_value)[:22] + "..."
                    display_value = f"[{truncated_text}]({full_url})"
                else:
                    display_value = str(display_value)[:26] + "..."
            
            # Escape pipe characters
            display_value = display_value.replace('|', '\\|')
            
            row_line += f" | {display_value:<29}"
        
        # End the row - no search group column
        row_line += " |"
        
        table_lines.append(row_line)
    
    # Return legend + table
    return legend + '\n'.join(table_lines)

def create_markdown_table(validation_results):
    """Convert validation results to markdown table format (legacy function for backwards compatibility)."""
    if not validation_results or 'results' not in validation_results:
        return "No validation results available."
    
    results = validation_results['results']
    if not results:
        return "No validation results found."
    
    # Create markdown table
    table_lines = [
        "| Field   | Confidence | Value                     |",
        "|---------|------------|--------------------------|"
    ]
    
    for result in results:
        field = result.get('field', 'Unknown')
        confidence = result.get('confidence', 'UNKNOWN')
        value = result.get('value', '')
        
        # Truncate long values, but preserve URLs as clickable links
        if len(str(value)) > 25:
            # Check if the value contains a URL
            import re
            url_pattern = r'https?://[^\s]+'
            url_match = re.search(url_pattern, str(value))

            if url_match:
                # Extract the URL
                full_url = url_match.group()
                # Create a clickable markdown link with truncated display text
                truncated_text = str(value)[:19] + "..."
                value = f"[{truncated_text}]({full_url})"
            else:
                value = str(value)[:22] + "..."
        
        # Escape any pipe characters in the value
        value = str(value).replace('|', '\\|')
        
        table_lines.append(f"| {field:<7} | {confidence:<10} | {value:<25} |")
    
    return '\n'.join(table_lines) 