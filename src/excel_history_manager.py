#!/usr/bin/env python3
"""
Excel History Manager - handles validation history independently of Lambda function.

This module implements the correct architecture where:
1. Previous validation results are loaded from Excel
2. Fresh validation is always requested from Lambda (bypassing cache)
3. New vs old results are compared locally
4. Both historical and new results are written to Excel
"""

import pandas as pd
import logging
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
import json

logger = logging.getLogger(__name__)

class ExcelHistoryManager:
    """Manages validation history by comparing old and new results locally."""
    
    def __init__(self, excel_path: str = None):
        """
        Initialize the history manager.
        
        Args:
            excel_path: Path to existing Excel file with previous results (optional)
        """
        self.excel_path = excel_path
        self.previous_results = {}
        
        if excel_path:
            self.load_previous_results()
    
    def load_previous_results(self) -> Dict[str, Dict[str, Any]]:
        """
        Load previous validation results from Excel file.
        
        Returns:
            Dictionary mapping row keys to their previous validation results
        """
        if not self.excel_path:
            logger.info("No Excel path provided, starting fresh")
            return {}
        
        try:
            from lambda_test_json_clean import load_validation_history_from_excel
            
            # Load validation history from Details worksheet
            validation_history = load_validation_history_from_excel(self.excel_path)
            
            if validation_history:
                logger.info(f"Loaded previous results for {len(validation_history)} rows")
                
                # Convert validation history to results format
                previous_results = {}
                for row_key, row_history in validation_history.items():
                    if row_history:
                        # Convert history entries back to results format
                        row_results = {}
                        for column, entries in row_history.items():
                            if entries:
                                # Use the most recent entry
                                latest_entry = entries[0]  # Assuming entries are sorted by timestamp
                                row_results[column] = {
                                    'value': latest_entry.get('value', ''),
                                    'confidence_level': latest_entry.get('confidence_level', 'UNKNOWN'),
                                    'quote': latest_entry.get('quote', ''),
                                    'sources': latest_entry.get('sources', []),
                                    'timestamp': latest_entry.get('timestamp', ''),
                                    'update_required': False,
                                    'substantially_different': False,
                                    'consistent_with_model_knowledge': True,
                                    'explanation': f"Previous validation from {latest_entry.get('timestamp', 'unknown date')}"
                                }
                        
                        if row_results:
                            previous_results[row_key] = row_results
                
                self.previous_results = previous_results
                logger.info(f"Converted to {len(previous_results)} previous result sets")
                return previous_results
            else:
                logger.info("No previous validation history found")
                return {}
                
        except Exception as e:
            logger.warning(f"Could not load previous results: {e}")
            return {}
    
    def force_fresh_validation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Modify payload to force fresh validation (bypass Lambda cache).
        
        Args:
            payload: Lambda payload
            
        Returns:
            Modified payload that will bypass cache
        """
        # Add cache-busting elements
        payload['cache_buster'] = {
            'timestamp': datetime.now().isoformat(),
            'force_fresh': True,
            'run_id': datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        }
        
        # Remove validation_history to force fresh validation
        if 'validation_history' in payload:
            del payload['validation_history']
        
        logger.info("Added cache-busting elements to force fresh validation")
        return payload
    
    def compare_results(self, new_results: Dict[str, Dict[str, Any]], row_key: str) -> Dict[str, Dict[str, Any]]:
        """
        Compare new results with previous results and mark as New/History.
        
        Args:
            new_results: New validation results from Lambda
            row_key: Row key for the results
            
        Returns:
            Combined results with New/History markers
        """
        combined_results = {}
        
        # Get previous results for this row
        previous_row_results = self.previous_results.get(row_key, {})
        
        # Process new results
        if row_key in new_results:
            new_row_results = new_results[row_key]
            
            for column, new_result in new_row_results.items():
                if column in ['holistic_validation', 'reasons', 'next_check', '_raw_responses']:
                    continue
                
                if not isinstance(new_result, dict):
                    continue
                
                # Check if this column had previous results
                previous_result = previous_row_results.get(column)
                
                # Determine if this is truly new or just a repeat
                is_new = True
                if previous_result:
                    # Compare key aspects to determine if it's actually different
                    prev_value = previous_result.get('value', '')
                    new_value = new_result.get('value', '')
                    prev_confidence = previous_result.get('confidence_level', '')
                    new_confidence = new_result.get('confidence_level', '')
                    
                    # Consider it "new" only if value or confidence changed significantly
                    if (prev_value == new_value and 
                        prev_confidence == new_confidence):
                        is_new = False
                
                # Create result entry with New/History marker
                result_entry = new_result.copy()
                result_entry['status'] = 'New' if is_new else 'Updated'
                result_entry['timestamp'] = datetime.now().isoformat()
                
                # Add to combined results
                if row_key not in combined_results:
                    combined_results[row_key] = {}
                
                combined_results[row_key][column] = result_entry
                
                # If we have previous results, also add them as history entries
                if previous_result and is_new:
                    # Add previous result as history
                    history_entry = previous_result.copy()
                    history_entry['status'] = 'History'
                    
                    # Create a unique key for the history entry
                    history_key = f"{column}_history"
                    combined_results[row_key][history_key] = history_entry
        
        # Add any previous results that don't have new counterparts
        for column, previous_result in previous_row_results.items():
            if row_key not in new_results or column not in new_results[row_key]:
                # This column wasn't validated this time, keep as history
                history_entry = previous_result.copy()
                history_entry['status'] = 'History'
                
                if row_key not in combined_results:
                    combined_results[row_key] = {}
                
                combined_results[row_key][column] = history_entry
        
        return combined_results
    
    def create_enhanced_results(self, new_results: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Create enhanced results that include both new and historical data.
        
        Args:
            new_results: Fresh validation results from Lambda
            
        Returns:
            Enhanced results with New/History markers
        """
        enhanced_results = {}
        
        # Process each row
        for row_key in new_results.keys():
            combined = self.compare_results(new_results, row_key)
            enhanced_results.update(combined)
        
        # Also add any historical rows that weren't processed this time
        for historical_row_key in self.previous_results.keys():
            if historical_row_key not in new_results:
                # This entire row is historical
                historical_results = {}
                for column, result in self.previous_results[historical_row_key].items():
                    history_entry = result.copy()
                    history_entry['status'] = 'History'
                    historical_results[column] = history_entry
                
                if historical_results:
                    enhanced_results[historical_row_key] = historical_results
        
        logger.info(f"Created enhanced results with {len(enhanced_results)} total rows")
        return enhanced_results

def create_fresh_validation_payload(row_data: Dict[str, Any], config: Dict[str, Any], row_key: str) -> Dict[str, Any]:
    """
    Create a Lambda payload that will force fresh validation (bypass cache).
    
    Args:
        row_data: Row data to validate
        config: Validation configuration
        row_key: Row key
        
    Returns:
        Payload that will bypass Lambda cache
    """
    from lambda_test_json_clean import create_lambda_payload
    
    # Create basic payload without validation history
    payload = create_lambda_payload(row_data, config, row_key, validation_history={})
    
    # Add cache-busting elements
    payload['cache_buster'] = {
        'timestamp': datetime.now().isoformat(),
        'force_fresh': True,
        'run_id': datetime.now().strftime("%Y%m%d_%H%M%S_%f"),
        'bypass_cache': True
    }
    
    # Add explicit instruction to ignore cache
    if 'config' in payload:
        payload['config']['force_fresh_validation'] = True
        payload['config']['ignore_cache'] = True
    
    logger.info("Created fresh validation payload with cache-busting elements")
    return payload

def process_with_history_management(df: pd.DataFrame, config: Dict[str, Any], output_path: str, 
                                   input_excel_path: str = None, **kwargs) -> str:
    """
    Process validation with proper history management.
    
    Args:
        df: DataFrame with data to validate
        config: Validation configuration
        output_path: Path for output Excel file
        input_excel_path: Path to existing Excel file with previous results
        **kwargs: Additional arguments for validation processing
        
    Returns:
        Path to the created Excel file
    """
    # Initialize history manager
    history_manager = ExcelHistoryManager(input_excel_path)
    
    # Process validation with fresh results
    from lambda_test_json_clean import invoke_lambda, process_lambda_response, generate_row_key
    
    all_results = {}
    
    for index, row in df.iterrows():
        try:
            # Clean row data
            row_data = {}
            for col, val in row.to_dict().items():
                if not (isinstance(val, float) and pd.isna(val)):
                    if not pd.isna(val) and val is not None:
                        row_data[col] = str(val)
                    else:
                        row_data[col] = None
            
            # Generate row key
            primary_keys = config.get('primary_key', [])
            if not primary_keys:
                # Auto-generate from ID fields
                id_fields = []
                for target in config.get('validation_targets', []):
                    if target.get('importance', '').upper() == 'ID':
                        id_fields.append(target['column'])
                primary_keys = id_fields
            
            row_key = generate_row_key(row_data, primary_keys)
            logger.info(f"Processing row {index+1}: {row_key}")
            
            # Create fresh validation payload (bypass cache)
            payload = create_fresh_validation_payload(row_data, config, row_key)
            
            # Invoke Lambda function
            response = invoke_lambda(payload)
            
            # Process response
            results = process_lambda_response(response, row_data, row_key)
            if results:
                all_results.update(results)
                logger.info(f"Got fresh results for row {index+1}")
            
        except Exception as e:
            logger.error(f"Error processing row {index+1}: {str(e)}")
            continue
    
    # Enhance results with history management
    enhanced_results = history_manager.create_enhanced_results(all_results)
    
    # Save to Excel with enhanced results
    from lambda_test_json_clean import save_results_to_excel
    final_output_path = save_results_to_excel(df, enhanced_results, output_path, config)
    
    logger.info(f"Saved enhanced results with history to {final_output_path}")
    return final_output_path 