#!/usr/bin/env python3
"""
Batch Validator - Easy command-line wrapper for Excel batch processing

Example usage:
  python batch_validate.py my_data.xlsx config.json --batch-size 20
"""

import os
import sys
import argparse
from datetime import datetime

def main():
    """Command-line interface for Excel batch validation."""
    parser = argparse.ArgumentParser(description="Batch validate Excel file through Lambda")
    parser.add_argument("excel_file", help="Path to Excel file to validate")
    parser.add_argument("config_file", help="Path to configuration JSON file")
    parser.add_argument("--output", "-o", help="Output Excel file path (default: auto-generated)")
    parser.add_argument("--batch-size", "-b", type=int, default=10, 
                        help="Number of rows per batch (default: 10)")
    parser.add_argument("--max-rows", "-m", type=int, 
                        help="Maximum number of rows to process")
    parser.add_argument("--api-key", "-k", help="API key for authentication")
    args = parser.parse_args()
    
    # Validate input files exist
    if not os.path.exists(args.excel_file):
        print(f"Error: Excel file not found: {args.excel_file}")
        return 1
    
    if not os.path.exists(args.config_file):
        print(f"Error: Config file not found: {args.config_file}")
        return 1
    
    # Set default output path if not specified
    if not args.output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        input_name = os.path.splitext(os.path.basename(args.excel_file))[0]
        args.output = f"validation_results_{input_name}_{timestamp}.xlsx"
    
    # Construct the command to run excel_batch_processor.py
    cmd = [
        sys.executable, "excel_batch_processor.py",
        "--input", args.excel_file,
        "--config", args.config_file,
        "--output", args.output,
        "--batch-size", str(args.batch_size)
    ]
    
    if args.max_rows:
        cmd.extend(["--max-rows", str(args.max_rows)])
    
    if args.api_key:
        cmd.extend(["--api-key", args.api_key])
    
    # Print command and run
    print(f"Running: {' '.join(cmd)}")
    
    # Use os.execv to replace the current process with the new one
    # This avoids having to handle stdout/stderr redirection
    os.execv(sys.executable, cmd)

if __name__ == "__main__":
    sys.exit(main()) 