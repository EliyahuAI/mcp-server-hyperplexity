#!/usr/bin/env python3
"""
Convert JSON test data to Excel format
"""
import json
import pandas as pd
import argparse
from pathlib import Path

def main():
    """Convert JSON test data to Excel format."""
    parser = argparse.ArgumentParser(description='Convert JSON test data to Excel')
    parser.add_argument('--input', default='deployment/ratio_competitive_intelligence_history_test.json',
                        help='Input JSON file path')
    parser.add_argument('--output', default='deployment/test_data.xlsx',
                        help='Output Excel file path')
    args = parser.parse_args()
    
    # Load JSON data
    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extract rows from JSON
    rows = data.get('validation_data', {}).get('rows', [])
    if not rows:
        print("No rows found in the JSON file")
        return 1
    
    # Convert to DataFrame
    df = pd.DataFrame(rows)
    
    # Write to Excel
    df.to_excel(args.output, index=False)
    print(f"Successfully converted {len(rows)} rows to Excel: {args.output}")
    
    return 0

if __name__ == "__main__":
    main() 