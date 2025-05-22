#!/usr/bin/env python3
"""
Simple wrapper script to run the lambda_test_json_clean.py with the Ratio Competitive Intelligence data.
"""

import os
import sys
import subprocess
import argparse
from datetime import datetime

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Run Lambda validation test for Ratio Competitive Intelligence")
    parser.add_argument("--rows", "-r", type=int, default=5, help="Number of rows to test (default: 5)")
    parser.add_argument("--api-key", "-k", help="API key for authentication")
    args = parser.parse_args()
    
    # Ensure directories exist
    os.makedirs("tables/RatioCompetitiveIntelligence", exist_ok=True)
    
    # Use the specific Ratio Competitive Intelligence files
    input_file = "tables/RatioCompetitiveIntelligence/RatioCompetitiveIntelligence.xlsx"
    config_file = "tables/RatioCompetitiveIntelligence/column_config.json"
    
    # Generate timestamp for the output file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"tables/RatioCompetitiveIntelligence/RatioCompetitiveIntelligence_results_{timestamp}.xlsx"
    
    # Check if input file exists
    if not os.path.exists(input_file):
        print(f"Error: Input file {input_file} not found.")
        return 1
        
    # Check if config file exists
    if not os.path.exists(config_file):
        print(f"Error: Config file {config_file} not found.")
        return 1
    
    # Construct the command
    cmd = [sys.executable, "lambda_test_json_clean.py", 
           "--input", input_file, 
           "--config", config_file, 
           "--output", output_file,
           "--rows", str(args.rows)]
    
    if args.api_key:
        cmd.extend(["--api-key", args.api_key])
    
    # Run the command
    print(f"Running command: {' '.join(cmd)}")
    process = subprocess.run(cmd)
    
    # Check result
    if process.returncode == 0:
        print(f"Validation completed successfully. Results saved to {output_file}")
        return 0
    else:
        print(f"Validation failed with return code {process.returncode}")
        return process.returncode

if __name__ == "__main__":
    sys.exit(main()) 