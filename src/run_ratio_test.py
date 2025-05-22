#!/usr/bin/env python
"""
Quick test script for the Excel Validator using RatioCompetitiveIntelligence dataset.

This script is a convenience wrapper that automatically finds the RatioCompetitiveIntelligence
Excel and config files and runs the end-to-end validation process on them.
"""

import os
import argparse
import logging
import tempfile
import shutil
import datetime
from pathlib import Path

from excel_processor import end_to_end_process

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Run a test validation on the RatioCompetitiveIntelligence dataset."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Test Excel Validator with RatioCompetitiveIntelligence dataset")
    parser.add_argument('--rows', '-r', default="0-2", help='Row indices to process (e.g., "0,1,2" or "0-5")')
    parser.add_argument('--api-key', '-k', help='API key for Perplexity API')
    parser.add_argument('--local', '-l', action='store_true', help='Use local validation instead of Lambda function')
    parser.add_argument('--output', '-o', help='Custom output file path')
    args = parser.parse_args()
    
    # Find the project root directory
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    
    # Find RatioCompetitiveIntelligence files
    input_file = project_root / "tables" / "RatioCompetitiveIntelligence" / "RatioCompetitiveIntelligence.xlsx"
    config_file = project_root / "tables" / "RatioCompetitiveIntelligence" / "column_config.yml"
    
    # Check if files exist
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        return 1
        
    if not config_file.exists():
        logger.error(f"Config file not found: {config_file}")
        return 1
    
    # Set default output file if not specified
    output_file = args.output
    if not output_file:
        # Use timestamp to avoid conflicts
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = input_file.parent / f"{input_file.stem}_test_{timestamp}.xlsx"
    
    # Parse row filter
    row_filter = None
    if args.rows:
        try:
            if ',' in args.rows:
                # Comma-separated list of indices
                row_filter = [int(idx) for idx in args.rows.split(',')]
            elif '-' in args.rows:
                # Range of indices
                start, end = args.rows.split('-')
                row_filter = list(range(int(start), int(end) + 1))
            else:
                # Single index
                row_filter = [int(args.rows)]
                
            logger.info(f"Processing rows: {row_filter}")
        except ValueError:
            logger.warning(f"Invalid row filter format: {args.rows}. Using first 3 rows.")
            row_filter = [0, 1, 2]
    
    # Get API key from environment if not provided
    api_key = args.api_key or os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        logger.warning("No API key provided. Set the PERPLEXITY_API_KEY environment variable or use --api-key.")
    
    # Create a temporary copy of the input file to avoid permission issues
    temp_dir = tempfile.mkdtemp()
    try:
        # Create temp copies of the files
        temp_input_file = Path(temp_dir) / input_file.name
        temp_config_file = Path(temp_dir) / config_file.name
        
        # Copy the files
        shutil.copy2(input_file, temp_input_file)
        shutil.copy2(config_file, temp_config_file)
        
        logger.info(f"Created temporary copies of input files in {temp_dir}")
        logger.info(f"Running test with:\n"
                    f"  - Input: {temp_input_file}\n"
                    f"  - Config: {temp_config_file}\n"
                    f"  - Output: {output_file}\n"
                    f"  - Rows: {row_filter or 'All'}\n"
                    f"  - Validation: {'Local' if args.local else 'Lambda'}")
        
        # Run end-to-end process with the temporary files
        end_to_end_process(
            input_file=str(temp_input_file),
            config_file=str(temp_config_file),
            output_file=str(output_file),
            api_key=api_key,
            row_filter=row_filter,
            use_lambda=not args.local
        )
        
        logger.info(f"Test completed successfully!\n"
                    f"Output file: {output_file}")
        return 0
    except Exception as e:
        logger.error(f"Error during test: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1
    finally:
        # Clean up the temporary directory
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary directory {temp_dir}: {e}")

if __name__ == "__main__":
    exit(main()) 