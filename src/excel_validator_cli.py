#!/usr/bin/env python
"""
Command-line interface for Excel Validator processing.

This script allows users to:
1. Convert Excel/CSV files to JSON
2. Process validation results and update Excel files
3. Perform end-to-end validation from Excel to Excel
"""

import os
import sys
import argparse
import json
import logging
from pathlib import Path

from excel_processor import ExcelProcessor, process_file, end_to_end_process

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_row_filter(rows_arg: str):
    """Parse row filter argument into a list of indices."""
    if not rows_arg:
        return None
        
    try:
        if ',' in rows_arg:
            # Comma-separated list of indices
            return [int(idx) for idx in rows_arg.split(',')]
        elif '-' in rows_arg:
            # Range of indices
            start, end = rows_arg.split('-')
            return list(range(int(start), int(end) + 1))
        else:
            # Single index
            return [int(rows_arg)]
    except ValueError:
        logger.warning(f"Invalid row filter format: {rows_arg}. Using all rows.")
        return None

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Process Excel/CSV files and validation results",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Command: to-json
    to_json_parser = subparsers.add_parser('to-json', help='Convert Excel/CSV to JSON')
    to_json_parser.add_argument('input_file', help='Path to the input Excel or CSV file')
    to_json_parser.add_argument('--output', '-o', help='Path to save the JSON file')
    to_json_parser.add_argument('--config', '-c', help='Path to the configuration file')
    to_json_parser.add_argument('--rows', '-r', help='Row indices to process (e.g. "0,1,2" or "0-5")')
    
    # Command: process
    process_parser = subparsers.add_parser('process', help='Process validation results and update Excel')
    process_parser.add_argument('input_file', help='Path to the input Excel or CSV file')
    process_parser.add_argument('--validation', '-v', required=True, help='Path to validation results JSON or JSON string')
    process_parser.add_argument('--config', '-c', help='Path to the configuration file')
    process_parser.add_argument('--output', '-o', help='Path to save the updated Excel file')
    process_parser.add_argument('--rows', '-r', help='Row indices to process (e.g. "0,1,2" or "0-5")')
    
    # Command: end-to-end
    e2e_parser = subparsers.add_parser('end-to-end', help='Perform end-to-end processing from Excel to Excel')
    e2e_parser.add_argument('input_file', help='Path to the input Excel or CSV file')
    e2e_parser.add_argument('--config', '-c', help='Path to the configuration file')
    e2e_parser.add_argument('--output', '-o', help='Path to save the updated Excel file')
    e2e_parser.add_argument('--api-key', '-k', help='API key for Perplexity API')
    e2e_parser.add_argument('--rows', '-r', help='Row indices to process (e.g. "0,1,2" or "0-5")')
    e2e_parser.add_argument('--local', '-l', action='store_true', help='Use local validation instead of Lambda function')
    
    # Command: test
    test_parser = subparsers.add_parser('test', help='Run a test on RatioCompetitiveIntelligence data')
    test_parser.add_argument('--rows', '-r', help='Row indices to process (e.g. "0,1,2" or "0-5")', default="0-2")
    test_parser.add_argument('--api-key', '-k', help='API key for Perplexity API')
    test_parser.add_argument('--local', '-l', action='store_true', help='Use local validation instead of Lambda function')
    
    args = parser.parse_args()
    
    # If no command is provided, show help
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Handle to-json command
    if args.command == 'to-json':
        row_filter = parse_row_filter(args.rows)
        processor = ExcelProcessor(args.input_file, args.config, row_filter)
        processor.to_json(args.output)
    
    # Handle process command
    elif args.command == 'process':
        row_filter = parse_row_filter(args.rows)
        process_file(args.input_file, args.config, args.validation, args.output, row_filter)
    
    # Handle end-to-end command
    elif args.command == 'end-to-end':
        row_filter = parse_row_filter(args.rows)
        end_to_end_process(
            args.input_file, 
            args.config, 
            args.output, 
            args.api_key,
            row_filter,
            not args.local  # Use lambda if not local
        )
        
    # Handle test command
    elif args.command == 'test':
        # Get the project root directory
        root_dir = Path(__file__).parent.parent
        
        # Locate the RatioCompetitiveIntelligence files
        input_file = root_dir / "tables" / "RatioCompetitiveIntelligence" / "RatioCompetitiveIntelligence.xlsx"
        config_file = root_dir / "tables" / "RatioCompetitiveIntelligence" / "column_config.yml"
        
        # Verify files exist
        if not input_file.exists():
            logger.error(f"Test input file not found: {input_file}")
            sys.exit(1)
            
        if not config_file.exists():
            logger.error(f"Test config file not found: {config_file}")
            sys.exit(1)
        
        # Create output file path
        output_file = input_file.parent / f"{input_file.stem}_test_output.xlsx"
        
        logger.info(f"Running test with:\n  - Input: {input_file}\n  - Config: {config_file}\n  - Output: {output_file}")
        
        # Parse row filter
        row_filter = parse_row_filter(args.rows)
        
        # Run end-to-end process
        end_to_end_process(
            str(input_file), 
            str(config_file), 
            str(output_file), 
            args.api_key,
            row_filter,
            not args.local  # Use lambda if not local
        )
        
        logger.info(f"Test completed successfully. Output file: {output_file}")

if __name__ == "__main__":
    main() 