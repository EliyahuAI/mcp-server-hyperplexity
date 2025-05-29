#!/usr/bin/env python
"""
Mock validator script for testing the Excel Validator.

This script reads input data from a JSON file, generates mock validation results,
and writes them to an output file.
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
import random
from datetime import datetime, timedelta
from row_key_utils import generate_row_key

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_mock_validation(input_data, api_key=None):
    """
    Generate mock validation results based on input data.
    
    Args:
        input_data: List of dictionaries containing input data
        api_key: Optional API key (not used in the mock)
        
    Returns:
        Dictionary with validation results
    """
    # Initial structure of validation results
    validation_results = {
        "data": {},
        "cache_stats": {
            "hits": random.randint(1, 5),
            "misses": random.randint(3, 10),
            "multiplex_validations": len(input_data),
            "single_validations": random.randint(5, 20)
        }
    }
    
    # Mock confidence levels and sources
    confidence_levels = ["HIGH", "MEDIUM", "LOW"]
    confidence_weights = [0.6, 0.3, 0.1]  # Biased toward HIGH confidence
    
    mock_sources = [
        "https://example.com/source1",
        "https://example.com/source2",
        "https://docs.example.org/reference",
        "https://api.example.com/docs"
    ]
    
    mock_quotes = [
        "This is a reliable and verified piece of information.",
        "According to our research, this data point is accurate.",
        "The value appears to be correct based on multiple sources.",
        "The information has been cross-checked with official documentation."
    ]
    
    # Assuming RatioCompetitiveIntelligence data has these primary keys
    ratio_primary_keys = ["Product Name", "Developer", "Target"]
    
    # Process each row in the input data
    for row_idx, row in enumerate(input_data):
        # Try to identify if this is RatioCompetitiveIntelligence data
        if all(key in row for key in ratio_primary_keys):
            # This looks like RatioCompetitiveIntelligence data, use its primary keys
            row_key_parts = [str(row.get(key, "")) for key in ratio_primary_keys]
            row_key = "||".join(row_key_parts)
            logger.info(f"Using RatioCompetitiveIntelligence primary key: {row_key}")
        else:
            # Fall back to using the first field as the key
            primary_key = list(row.keys())[0] if row else "unknown"
            row_key = generate_row_key(row, primary_key_columns)
            logger.info(f"Using generic primary key: {row_key}")
        
        # Initialize validation results for this row
        validation_results["data"][row_key] = {
            "validation_results": {}
        }
        
        # Process each field in the row
        for field_name, field_value in row.items():
            # Skip empty values
            if field_value is None or field_value == "":
                continue
                
            # Generate confidence level (biased toward HIGH)
            confidence_level = random.choices(confidence_levels, weights=confidence_weights)[0]
            confidence = 0.95 if confidence_level == "HIGH" else 0.75 if confidence_level == "MEDIUM" else 0.5
            
            # Select random sources and quotes
            num_sources = random.randint(1, 3)
            sources = random.sample(mock_sources, num_sources)
            quote = random.choice(mock_quotes)
            
            # Determine if update is required (20% chance)
            update_required = random.random() < 0.2
            
            # Add validation result for this field
            validation_results["data"][row_key]["validation_results"][field_name] = {
                "value": field_value,
                "confidence": confidence,
                "confidence_level": confidence_level,
                "sources": sources,
                "quote": quote,
                "update_required": update_required,
                "answer": field_value,  # In a real validator, this might differ from the input value
                "main_source": sources[0] if sources else None,
                "explanation": f"Validation for field {field_name} completed with {confidence_level} confidence."
            }
        
        # Add holistic validation
        low_confidence_fields = [
            field for field, result in validation_results["data"][row_key]["validation_results"].items()
            if result.get("confidence_level") == "LOW"
        ]
        
        concerns = []
        if low_confidence_fields:
            for field in low_confidence_fields:
                concerns.append(f"Field '{field}' has LOW confidence")
        
        validation_results["data"][row_key]["holistic_validation"] = {
            "is_consistent": True,
            "overall_confidence": "MEDIUM" if not low_confidence_fields else "LOW",
            "concerns": concerns,
            "needs_review": bool(concerns),
            "priority_fields": low_confidence_fields
        }
        
        # Add next check date (1 year from now)
        next_check = datetime.now() + timedelta(days=365)
        validation_results["data"][row_key]["next_check"] = next_check.isoformat()
    
    return validation_results

def main():
    """Main function for the validator script."""
    parser = argparse.ArgumentParser(description="Mock validator for Excel Validator testing")
    parser.add_argument("--input", "-i", required=True, help="Path to input JSON file")
    parser.add_argument("--output", "-o", required=True, help="Path to output JSON file")
    parser.add_argument("--api-key", "-k", help="API key (not used in the mock)")
    
    args = parser.parse_args()
    
    try:
        # Load input data
        with open(args.input, 'r', encoding='utf-8') as f:
            input_data = json.load(f)
            
        logger.info(f"Loaded input data with {len(input_data)} records")
        
        # Generate mock validation results
        validation_results = generate_mock_validation(input_data, args.api_key)
        
        # Write validation results to output file
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(validation_results, f, indent=2)
            
        logger.info(f"Generated mock validation results and saved to {args.output}")
        return 0
    except Exception as e:
        logger.error(f"Error processing data: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    sys.exit(main()) 