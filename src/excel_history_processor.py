#!/usr/bin/env python3
"""
Excel History Processor - Correct implementation.

This module implements the proper flow:
1. Load validation history from Details worksheet
2. Send history to Lambda (prevents cache hits)
3. Mark existing Detail rows as "History"
4. Prepend new results as "New" rows
"""

import pandas as pd
import logging
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
import os

logger = logging.getLogger(__name__)

class ExcelHistoryProcessor:
    """Processes validation history correctly."""
    
    @staticmethod
    def load_and_mark_history(excel_path: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Load existing Excel file and prepare validation history.
        
        Args:
            excel_path: Path to existing Excel file
            
        Returns:
            Tuple of (details_df with History marking, validation_history dict)
        """
        if not os.path.exists(excel_path):
            logger.info("No existing Excel file, starting fresh")
            return pd.DataFrame(), {}
        
        try:
            # Load existing Details worksheet
            details_df = pd.read_excel(excel_path, sheet_name='Details', engine='openpyxl')
            logger.info(f"Loaded {len(details_df)} existing detail rows")
            
            # Extract validation history from Details worksheet
            validation_history = {}
            
            for _, row in details_df.iterrows():
                row_key = row.get('Row Key', '')
                if not row_key:
                    continue
                
                if row_key not in validation_history:
                    validation_history[row_key] = {}
                
                # Extract column validations
                column_name = row.get('Column', '')
                if column_name:
                    validation_entry = {
                        'value': row.get('Value', ''),
                        'confidence_level': row.get('Confidence', 'UNKNOWN'),
                        'quote': row.get('Quote', ''),
                        'sources': [s.strip() for s in str(row.get('Sources', '')).split('\n') if s.strip()],
                        'timestamp': row.get('Timestamp', ''),
                        'validation_method': row.get('Validation Method', ''),
                        'update_required': row.get('Update Required', False),
                        'substantially_different': row.get('Substantially Different', False)
                    }
                    
                    if column_name not in validation_history[row_key]:
                        validation_history[row_key][column_name] = []
                    
                    validation_history[row_key][column_name].append(validation_entry)
            
            # Mark all existing rows as "History" (change from "New")
            details_df['New'] = 'History'
            logger.info(f"Marked {len(details_df)} existing rows as 'History'")
            
            return details_df, validation_history
            
        except Exception as e:
            logger.error(f"Error loading validation history: {e}")
            return pd.DataFrame(), {}
    
    @staticmethod
    def prepend_new_results(existing_df: pd.DataFrame, new_results: Dict[str, Dict[str, Any]], 
                           result_df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """
        Prepend new validation results to existing Details dataframe.
        
        Args:
            existing_df: Existing Details dataframe (with History marking)
            new_results: New validation results from Lambda
            result_df: Original dataframe being validated
            config: Validation configuration
            
        Returns:
            Combined dataframe with new results prepended
        """
        new_rows = []
        
        # Convert new results to Detail rows
        for row_idx, (_, row) in enumerate(result_df.iterrows()):
            # Find matching results
            matched_key = None
            row_data = None
            
            if row_idx in new_results:
                matched_key = row_idx
                row_data = new_results[row_idx]
            elif str(row_idx) in new_results:
                matched_key = str(row_idx)
                row_data = new_results[matched_key]
            
            if not row_data:
                continue
            
            # Generate row key for this row
            from row_key_utils import generate_row_key
            primary_keys = config.get('primary_key', [])
            if not primary_keys:
                # Auto-generate from ID fields
                id_fields = []
                for target in config.get('validation_targets', []):
                    if target.get('importance', '').upper() == 'ID':
                        id_fields.append(target['column'])
                primary_keys = id_fields
            
            row_dict = row.to_dict()
            row_key = generate_row_key(row_dict, primary_keys)
            
            # Process each column validation
            for column, result in row_data.items():
                if column in ['holistic_validation', 'reasons', 'next_check', '_raw_responses']:
                    continue
                
                if not isinstance(result, dict):
                    continue
                
                detail_row = {
                    'Row Key': row_key,
                    'Column': column,
                    'Value': result.get('value', ''),
                    'Confidence': result.get('confidence_level', 'UNKNOWN'),
                    'Quote': result.get('quote', ''),
                    'Sources': '\n'.join(result.get('sources', [])),
                    'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'Validation Method': result.get('validation_method', 'perplexity'),
                    'Update Required': result.get('update_required', False),
                    'Substantially Different': result.get('substantially_different', False),
                    'Consistent With Model': result.get('consistent_with_model_knowledge', True),
                    'Explanation': result.get('explanation', ''),
                    'New': 'New'  # Mark new results as "New"
                }
                
                new_rows.append(detail_row)
        
        # Create new dataframe from new rows
        new_df = pd.DataFrame(new_rows)
        logger.info(f"Created {len(new_df)} new detail rows marked as 'New'")
        
        # Prepend new results to existing (now historical) results
        if not existing_df.empty:
            # Ensure column order matches
            for col in new_df.columns:
                if col not in existing_df.columns:
                    existing_df[col] = ''
            
            combined_df = pd.concat([new_df, existing_df], ignore_index=True)
            logger.info(f"Combined: {len(new_df)} new + {len(existing_df)} history = {len(combined_df)} total rows")
        else:
            combined_df = new_df
            logger.info(f"No existing history, using {len(new_df)} new rows")
        
        return combined_df
    
    @staticmethod
    def update_excel_with_history(excel_path: str, new_results: Dict[str, Dict[str, Any]], 
                                 result_df: pd.DataFrame, config: Dict[str, Any]) -> str:
        """
        Update Excel file with proper history management.
        
        Args:
            excel_path: Path to Excel file (existing or new)
            new_results: New validation results from Lambda
            result_df: Original dataframe being validated
            config: Validation configuration
            
        Returns:
            Path to updated Excel file
        """
        # Load existing file and mark as history
        existing_details_df, validation_history = ExcelHistoryProcessor.load_and_mark_history(excel_path)
        
        # The validation_history extracted above should have been sent to Lambda
        # Now we process the new results
        
        # Prepend new results
        updated_details_df = ExcelHistoryProcessor.prepend_new_results(
            existing_details_df, new_results, result_df, config
        )
        
        # Write back to Excel
        with pd.ExcelWriter(excel_path, engine='openpyxl', mode='w') as writer:
            # Write Summary sheet
            result_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Write updated Details sheet (new results first, then history)
            updated_details_df.to_excel(writer, sheet_name='Details', index=False)
            
            # Write Reasons sheet if we have validation reasons
            reasons_data = []
            for row_key, row_results in new_results.items():
                if 'reasons' in row_results:
                    reasons = row_results['reasons']
                    for column, reason_list in reasons.items():
                        if isinstance(reason_list, list):
                            for reason in reason_list:
                                reasons_data.append({
                                    'Row Key': row_key,
                                    'Column': column,
                                    'Reason': reason
                                })
            
            if reasons_data:
                reasons_df = pd.DataFrame(reasons_data)
                reasons_df.to_excel(writer, sheet_name='Reasons', index=False)
            
            # Add formatting
            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
        
        logger.info(f"Updated Excel file with history management: {excel_path}")
        return excel_path

def integrate_with_existing_processor(existing_process_function):
    """
    Decorator to integrate history management with existing Excel processor.
    
    Usage:
        @integrate_with_existing_processor
        def process_excel_batch(...):
            ...
    """
    def wrapper(*args, **kwargs):
        # Extract key arguments
        df = args[0] if args else kwargs.get('df')
        config = args[1] if len(args) > 1 else kwargs.get('config')
        output_path = args[2] if len(args) > 2 else kwargs.get('output_path')
        
        # Check for existing Excel file
        existing_excel = None
        if os.path.exists(output_path):
            existing_excel = output_path
            logger.info(f"Found existing Excel file: {output_path}")
        
        # Load validation history before processing
        if existing_excel:
            _, validation_history = ExcelHistoryProcessor.load_and_mark_history(existing_excel)
            # Inject validation history into the processing
            kwargs['validation_history'] = validation_history
            logger.info(f"Loaded validation history for {len(validation_history)} rows")
        
        # Call original function (which will send history to Lambda)
        results = existing_process_function(*args, **kwargs)
        
        # Post-process to update Excel with proper history management
        if isinstance(results, dict) and existing_excel:
            # Assume results contains the validation results
            ExcelHistoryProcessor.update_excel_with_history(
                output_path, results, df, config
            )
        
        return results
    
    return wrapper 