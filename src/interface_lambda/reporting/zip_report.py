"""
Functions for creating ZIP file reports.
"""
import io
import zipfile
from datetime import datetime
import json
import csv
from io import StringIO

def create_placeholder_zip():
    """Create a placeholder ZIP file indicating processing is in progress."""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add a README file
        readme_content = """
Processing in Progress
=====================

Your Excel file is currently being processed by the Perplexity Validator.

Processing Status: IN PROGRESS
Started: {timestamp}

Please check back in a few minutes. This file will be automatically 
replaced with your validation results once processing is complete.

If processing takes longer than expected, please contact support.
        """.format(timestamp=datetime.utcnow().isoformat() + 'Z').strip()
        
        zip_file.writestr('README.txt', readme_content)
        zip_file.writestr('STATUS.txt', 'PROCESSING')
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()

def create_validation_result_zip(validation_results, session_id, total_rows):
    """Create a ZIP file with real validation results."""
    zip_buffer = io.BytesIO()
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        
        # Create validation results JSON
        results_data = {
            "session_id": session_id,
            "timestamp": timestamp,
            "validation_results": validation_results,
            "summary": {
                "total_rows": total_rows,
                "fields_validated": [],
                "confidence_distribution": {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
            }
        }
        
        # Analyze results for summary
        if validation_results:
            all_fields = set()
            confidence_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
            
            for row_key, row_data in validation_results.items():
                for field_name, field_data in row_data.items():
                    if isinstance(field_data, dict) and 'confidence_level' in field_data:
                        all_fields.add(field_name)
                        conf_level = field_data.get('confidence_level', 'UNKNOWN')
                        if conf_level in confidence_counts:
                            confidence_counts[conf_level] += 1
            
            results_data["summary"]["fields_validated"] = list(all_fields)
            results_data["summary"]["confidence_distribution"] = confidence_counts
        
        # Add JSON file
        zip_file.writestr('validation_results.json', json.dumps(results_data, indent=2))
        
        # Create a summary report
        summary_report = f"""
Validation Results Summary
=========================

Session ID: {session_id}
Generated: {timestamp}
Total Rows Processed: {total_rows}

Fields Validated: {', '.join(results_data['summary']['fields_validated'])}

Confidence Distribution:
- HIGH: {results_data['summary']['confidence_distribution']['HIGH']} fields
- MEDIUM: {results_data['summary']['confidence_distribution']['MEDIUM']} fields  
- LOW: {results_data['summary']['confidence_distribution']['LOW']} fields

Processing Details:
==================
{json.dumps(validation_results, indent=2) if validation_results else 'No validation results'}
        """.strip()
        
        zip_file.writestr('SUMMARY.txt', summary_report)
        
        # Add completion marker
        zip_file.writestr('COMPLETED.txt', f'Validation completed at {timestamp}')
        
        # Create CSV report for easy viewing
        if validation_results:
            # Use Python's csv module for proper escaping
            csv_buffer = StringIO()
            csv_writer = csv.writer(csv_buffer)
            
            # Write header
            csv_writer.writerow(['Field', 'Value', 'Confidence', 'Sources', 'Quote'])
            
            for row_key, row_data in validation_results.items():
                for field_name, field_data in row_data.items():
                    if isinstance(field_data, dict) and 'confidence_level' in field_data:
                        value = str(field_data.get('value', ''))
                        confidence = field_data.get('confidence_level', 'UNKNOWN')
                        sources = ', '.join(field_data.get('sources', []))[:100] + '...' if len(field_data.get('sources', [])) > 0 else ''
                        quote = str(field_data.get('quote', ''))[:100] + '...' if len(str(field_data.get('quote', ''))) > 100 else str(field_data.get('quote', ''))
                        
                        csv_writer.writerow([field_name, value, confidence, sources, quote])
            
            zip_file.writestr('validation_results.csv', csv_buffer.getvalue())
            csv_buffer.close()
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue() 

def create_enhanced_result_zip(validation_results, session_id, total_rows, excel_file_content, config_data, reference_pin=None, input_filename='input.xlsx', config_filename='config.json', metadata=None):
    """Create enhanced ZIP file with color-coded Excel and comprehensive reports."""
    from .excel_report import create_enhanced_excel_with_validation

    zip_buffer = io.BytesIO()
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        
        # Create validation results JSON
        results_data = {
            "session_id": session_id,
            "timestamp": timestamp,
            "reference_pin": reference_pin,
            "validation_results": validation_results,
            "summary": {
                "total_rows": total_rows,
                "fields_validated": [],
                "confidence_distribution": {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
            }
        }
        
        # Add token usage metadata if available
        if metadata:
            results_data["metadata"] = metadata
        
        # Analyze results for summary
        if validation_results:
            all_fields = set()
            confidence_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
            
            for row_key, row_data in validation_results.items():
                for field_name, field_data in row_data.items():
                    if isinstance(field_data, dict) and 'confidence_level' in field_data:
                        all_fields.add(field_name)
                        conf_level = field_data.get('confidence_level', 'UNKNOWN')
                        if conf_level in confidence_counts:
                            confidence_counts[conf_level] += 1
            
            results_data["summary"]["fields_validated"] = list(all_fields)
            results_data["summary"]["confidence_distribution"] = confidence_counts
        
        # Add JSON file
        zip_file.writestr('validation_results.json', json.dumps(results_data, indent=2))
        
        # Create enhanced Excel file
        if excel_file_content and validation_results:
            try:
                excel_buffer = create_enhanced_excel_with_validation(
                    excel_file_content, validation_results, config_data, session_id
                )
                if excel_buffer:
                    zip_file.writestr('validation_results_enhanced.xlsx', excel_buffer.getvalue())
                else:
                    # In case of error in excel creation, we can log it.
                    # The function create_enhanced_excel_with_validation should have its own logging.
                    pass
            except Exception as e:
                # Log this error
                pass
        
        # Create CSV report for easy viewing
        if validation_results:
            # Use Python's csv module for proper escaping
            csv_buffer = StringIO()
            csv_writer = csv.writer(csv_buffer)
            
            # Write header
            csv_writer.writerow(['Row', 'Field', 'Original_Value', 'Validated_Value', 'Confidence', 'Sources', 'Quote'])
            
            for row_key, row_data in validation_results.items():
                for field_name, field_data in row_data.items():
                    if isinstance(field_data, dict) and 'confidence_level' in field_data:
                        original = str(field_data.get('original_value', ''))
                        value = str(field_data.get('value', ''))
                        confidence = field_data.get('confidence_level', 'UNKNOWN')
                        sources = ', '.join(field_data.get('sources', []))[:100] + '...' if len(field_data.get('sources', [])) > 0 else ''
                        quote = str(field_data.get('quote', ''))[:100] + '...' if len(str(field_data.get('quote', ''))) > 100 else str(field_data.get('quote', ''))
                        
                        csv_writer.writerow([row_key, field_name, original, value, confidence, sources, quote])
            
            zip_file.writestr('validation_results.csv', csv_buffer.getvalue())
            csv_buffer.close()
        
        # Add original input and config files to the ZIP
        if excel_file_content:
            zip_file.writestr(f'original_files/{input_filename}', excel_file_content)
        
        if config_data:
            if isinstance(config_data, dict):
                config_json = json.dumps(config_data, indent=2)
            else:
                config_json = str(config_data)
            zip_file.writestr(f'original_files/{config_filename}', config_json)
        
        # Create enhanced summary report
        pin_section = f"""
Reference Pin: {reference_pin}
""" if reference_pin else ""
        
        # Generate token usage section
        token_usage_section = ""
        if metadata and 'token_usage' in metadata:
            token_usage = metadata['token_usage']
            token_usage_section = f"""

Token Usage & Cost Analysis:
============================
Total Tokens: {token_usage.get('total_tokens', 0):,}
Total Cost: ${token_usage.get('total_cost', 0.0):.6f}
API Calls: {token_usage.get('api_calls', 0)} new, {token_usage.get('cached_calls', 0)} cached

Provider Breakdown:
"""
            # Add provider-specific details
            if 'by_provider' in token_usage:
                for provider, provider_data in token_usage['by_provider'].items():
                    if provider_data.get('calls', 0) > 0:
                        if provider == 'perplexity':
                            token_usage_section += f"""- Perplexity API: {provider_data.get('prompt_tokens', 0):,} prompt + {provider_data.get('completion_tokens', 0):,} completion = {provider_data.get('total_tokens', 0):,} tokens
  Cost: ${provider_data.get('input_cost', 0.0):.6f} input + ${provider_data.get('output_cost', 0.0):.6f} output = ${provider_data.get('total_cost', 0.0):.6f} total
  Calls: {provider_data.get('calls', 0)}
"""
                        elif provider == 'anthropic':
                            token_usage_section += f"""- Anthropic API: {provider_data.get('input_tokens', 0):,} input + {provider_data.get('output_tokens', 0):,} output
  Cache: {provider_data.get('cache_creation_tokens', 0):,} creation + {provider_data.get('cache_read_tokens', 0):,} read = {provider_data.get('total_tokens', 0):,} total tokens
  Cost: ${provider_data.get('input_cost', 0.0):.6f} input + ${provider_data.get('output_cost', 0.0):.6f} output = ${provider_data.get('total_cost', 0.0):.6f} total
  Calls: {provider_data.get('calls', 0)}
"""
            
            # Add model breakdown
            if 'by_model' in token_usage and token_usage['by_model']:
                token_usage_section += f"\nModel Breakdown:\n"
                for model, model_data in token_usage['by_model'].items():
                    api_provider = model_data.get('api_provider', 'unknown')
                    token_usage_section += f"- {model} ({api_provider}): {model_data.get('total_tokens', 0):,} tokens, ${model_data.get('total_cost', 0.0):.6f}, {model_data.get('calls', 0)} calls\n"
        
        summary_report = f"""
Enhanced Validation Results Summary
==================================

Session ID: {session_id}{pin_section}
Generated: {timestamp}
Total Rows Processed: {total_rows}

Fields Validated: {', '.join(results_data['summary']['fields_validated'])}

Confidence Distribution:
- HIGH: {results_data['summary']['confidence_distribution']['HIGH']} fields
- MEDIUM: {results_data['summary']['confidence_distribution']['MEDIUM']} fields  
- LOW: {results_data['summary']['confidence_distribution']['LOW']} fields{token_usage_section}

Files Included:
==============
- validation_results_enhanced.xlsx : Color-coded Excel with comments and multiple sheets
- validation_results.json          : Raw validation data in JSON format
- validation_results.csv           : Simple CSV format for basic analysis
- SUMMARY.txt                      : This summary file
- COMPLETED.txt                    : Processing completion marker
- original_files/{input_filename}  : Original input file
- original_files/{config_filename} : Original configuration file

Enhanced Excel Features:
=======================
✅ Color-coded confidence levels:
   - GREEN: HIGH confidence
   - YELLOW: MEDIUM confidence  
   - RED: LOW confidence
✅ Cell comments with quotes and sources
✅ Multiple worksheets: Results, Details, Reasons
✅ Comprehensive validation tracking
✅ Professional formatting with xlsxwriter

Processing Details:
==================
{json.dumps(validation_results, indent=2) if validation_results else 'No validation results'}
        """.strip()
        
        zip_file.writestr('SUMMARY.txt', summary_report)
        
        # Add completion marker
        zip_file.writestr('COMPLETED.txt', f'Enhanced validation completed at {timestamp}')
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue() 