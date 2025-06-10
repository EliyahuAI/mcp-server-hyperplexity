#!/usr/bin/env python3
"""
Test full validation through the API Gateway interface.
Accepts command-line arguments for flexible testing.
"""
import requests
import json
import os
import argparse
from datetime import datetime
from pathlib import Path

# API endpoint
API_URL = "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate"

# Default values
DEFAULT_EMAIL = "eliyahu@eliyahu.ai"
DEFAULT_EXCEL = "tables/RatioCompetitiveIntelligence/RatioCompetitiveIntelligence.xlsx"
DEFAULT_CONFIG = "tables/RatioCompetitiveIntelligence/column_config.json"
DEFAULT_BATCH_SIZE = 10


def test_full_validation(excel_file, config_file, email=None, max_rows=None, batch_size=None, preview_mode=False):
    """Test full validation with specified parameters"""
    
    print("="*60)
    print("Full Validation Test" if not preview_mode else "Preview Mode Test")
    print("="*60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Convert to Path objects
    excel_path = Path(excel_file)
    config_path = Path(config_file)
    
    # Check if files exist
    if not excel_path.exists():
        print(f"Error: Excel file not found: {excel_path}")
        return False
        
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        return False
        
    print(f"\nConfiguration:")
    print(f"  Excel file: {excel_path}")
    print(f"  Config file: {config_path}")
    print(f"  Email: {email or 'Not provided (download mode)'}")
    print(f"  Max rows: {max_rows if max_rows else 'ALL (no limit)'}")
    print(f"  Batch size: {batch_size or DEFAULT_BATCH_SIZE}")
    print(f"  Mode: {'Preview first row' if preview_mode else 'Full validation'}")
    
    # Prepare the request parameters
    params = {
        'preview_first_row': 'true' if preview_mode else 'false',
        'batch_size': str(batch_size or DEFAULT_BATCH_SIZE)
    }
    
    if max_rows:
        params['max_rows'] = str(max_rows)
    
    # Read files
    with open(excel_path, 'rb') as f:
        excel_content = f.read()
        
    with open(config_path, 'r') as f:
        config_content = f.read()
    
    # Create multipart form data
    files = {
        'excel_file': (excel_path.name, excel_content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
        'config_file': (config_path.name, config_content, 'application/json')
    }
    
    # Add email to form data if provided
    data = {}
    if email:
        data['email'] = email
    
    print(f"\nFile sizes:")
    print(f"  Excel: {len(excel_content):,} bytes ({len(excel_content)/1024/1024:.2f} MB)")
    print(f"  Config: {len(config_content):,} bytes")
    
    print(f"\nSending request to API...")
    print(f"Parameters: {params}")
    
    try:
        response = requests.post(
            API_URL,
            params=params,
            files=files,
            data=data if data else None
        )
        
        print(f"\nResponse status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            if preview_mode:
                # Preview mode response
                print("\n=== PREVIEW MODE RESULTS ===")
                if 'markdown_table' in result:
                    print("\nValidation preview:")
                    print(result['markdown_table'])
                    print(f"\nTotal rows in file: {result.get('total_rows', 'Unknown')}")
                    print(f"First row processing time: {result.get('first_row_processing_time', 'Unknown'):.2f}s")
                    print(f"Estimated total time: {result.get('estimated_total_processing_time', 'Unknown'):.2f}s")
                else:
                    print("No preview table in response")
                    print(json.dumps(result, indent=2))
            
            else:
                # Full validation mode
                print("\nResponse:")
                print(json.dumps(result, indent=2))
                
                # Check if processing started successfully
                if result.get('status') == 'processing_started':
                    print("\n" + "="*60)
                    print("✅ SUCCESS - FULL VALIDATION STARTED!")
                    print("="*60)
                    
                    session_id = result.get('session_id', 'N/A')
                    print(f"\nSession ID: {session_id}")
                    
                    if email and email in result.get('message', ''):
                        print(f"\n📧 Email will be sent to {email} when complete.")
                        print("\nExpected email contents:")
                        print("  • Enhanced Excel file with color-coded validation results")
                        print(f"  • {max_rows if max_rows else 'ALL'} rows validated")
                        print("  • Multiple worksheets: Results, Details, Reasons")
                        print("  • Cell comments with quotes and sources")
                    else:
                        download_url = result.get('download_url')
                        if download_url:
                            print(f"\n💾 Download URL: {download_url}")
                            print("Note: File will be available once processing completes")
                    
                    print(f"\n⏱️  Estimated processing time: {result.get('processing_time', 'Unknown')} seconds")
                    
                elif result.get('status') == 'timeout':
                    print("\n⚠️ Preview timeout - validation may take longer than expected")
                else:
                    print("\n⚠️ Unexpected response status")
                    
            return True
                
        else:
            print(f"\n❌ Error response:")
            print(response.text)
            return False
            
    except Exception as e:
        print(f"\n❌ Error making request: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test full validation through API Gateway interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with default files
  python test_full_validation.py
  
  # Test with specific files
  python test_full_validation.py -e my_data.xlsx -c my_config.json
  
  # Limit to 10 rows with email
  python test_full_validation.py --max-rows 10 --email user@example.com
  
  # Preview mode (test first row only)
  python test_full_validation.py --preview
  
  # Custom batch size
  python test_full_validation.py --batch-size 20
""")
    
    parser.add_argument("-e", "--excel", 
                        default=DEFAULT_EXCEL,
                        help=f"Excel file path (default: {DEFAULT_EXCEL})")
    parser.add_argument("-c", "--config", 
                        default=DEFAULT_CONFIG,
                        help=f"Config JSON file path (default: {DEFAULT_CONFIG})")
    parser.add_argument("--email", 
                        default=DEFAULT_EMAIL,
                        help=f"Email address for results (default: {DEFAULT_EMAIL})")
    parser.add_argument("--max-rows", 
                        type=int, 
                        help="Maximum number of rows to process")
    parser.add_argument("--batch-size", 
                        type=int,
                        default=DEFAULT_BATCH_SIZE,
                        help=f"Batch size for processing (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--preview", 
                        action="store_true",
                        help="Preview mode - validate first row only")
    parser.add_argument("--no-email",
                        action="store_true",
                        help="Don't send email (get download URL instead)")
    
    args = parser.parse_args()
    
    # Handle email option
    email = None if args.no_email else args.email
    
    # Run test
    success = test_full_validation(
        excel_file=args.excel,
        config_file=args.config,
        email=email,
        max_rows=args.max_rows,
        batch_size=args.batch_size,
        preview_mode=args.preview
    )
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main()) 