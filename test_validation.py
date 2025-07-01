#!/usr/bin/env python3
"""
Enhanced end-to-end test for validation system with command-line arguments
Supports custom files, modes, and organized output with timestamps
"""

import argparse
import requests
import json
import time
import boto3
import os
import sys
from datetime import datetime
from pathlib import Path

# Configuration
API_URL = "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate"
STATUS_URL = "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/status"
EMAIL = "Eliyahu@Eliyahu.AI"

# AWS clients
s3_client = boto3.client('s3', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
tracking_table = dynamodb.Table('perplexity-validator-call-tracking')

def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Test perplexity validator with various modes and options',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_validation.py
    Run all tests with default files
    
  python test_validation.py --mode sync_preview --max-rows 5
    Run only sync preview with 5 rows
    
  python test_validation.py --excel "path/to/file.xlsx" --config "path/to/config.json"
    Use custom files for testing
    
  python test_validation.py --name "congress_test" --output-dir "test_results"
    Custom test name and output directory
"""
    )
    
    # File arguments
    parser.add_argument('--excel', 
                       default=r"tables\CongressesMasterList\Congresses Master List_Verified1.xlsx",
                       help='Path to Excel file (default: Congress Master List)')
    
    parser.add_argument('--config',
                       default=r"tables\CongressesMasterList\congress_config.json",
                       help='Path to config JSON file')
    
    # Test mode
    parser.add_argument('--mode',
                       choices=['all', 'sync_preview', 'async_preview', 'full_validation'],
                       default='all',
                       help='Test mode to run (default: all)')
    
    # Row limits
    parser.add_argument('--max-rows',
                       type=int,
                       default=10,
                       help='Maximum rows for full validation (default: 10)')
    
    parser.add_argument('--preview-rows',
                       type=int,
                       default=3,
                       help='Rows for preview tests (default: 3)')
    
    # Output configuration
    parser.add_argument('--name',
                       help='Test name to append to timestamp (e.g., "congress_test")')
    
    parser.add_argument('--output-dir',
                       default='test_results',
                       help='Output directory for test results (default: test_results)')
    
    # Email override
    parser.add_argument('--email',
                       default=EMAIL,
                       help=f'Email address for testing (default: {EMAIL})')
    
    # Verbosity
    parser.add_argument('-v', '--verbose',
                       action='store_true',
                       help='Verbose output')
    
    return parser.parse_args()

def setup_output_directory(args):
    """Create timestamped output directory"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Build directory name
    if args.name:
        dir_name = f"{timestamp}_{args.name}"
    else:
        dir_name = timestamp
    
    # Create full path
    output_path = Path(args.output_dir) / dir_name
    output_path.mkdir(parents=True, exist_ok=True)
    
    return output_path

def log_output(output_dir, filename, content):
    """Save output to file in the test directory"""
    filepath = output_dir / filename
    
    # Ensure directory exists
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        if isinstance(content, dict):
            json.dump(content, f, indent=2, default=str)
        else:
            f.write(str(content))
    
    return filepath

def print_test_header(test_name, args, output_dir):
    """Print formatted test header with configuration"""
    print("\n" + "="*80)
    print(f"🧪 {test_name}")
    print("="*80)
    print(f"📅 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Output Dir: {output_dir}")
    print(f"📧 Email: {args.email}")
    print(f"📄 Excel: {Path(args.excel).name}")
    print(f"⚙️  Config: {Path(args.config).name}")
    print("-"*80)

def get_dynamodb_record(session_id):
    """Get DynamoDB record for a session"""
    try:
        response = tracking_table.get_item(Key={'session_id': session_id})
        return response.get('Item')
    except Exception as e:
        print(f"❌ Error getting DynamoDB record: {e}")
        return None

def get_s3_preview(session_id, email):
    """Get preview results from S3"""
    # Force lowercase for email parts
    if '@' in email:
        user, domain = email.lower().split('@')
        # Try new format first, then old format
        paths = [
            f"preview_results/{domain}/{user}/{session_id}.json",  # New format
            f"preview_results/{domain}/{user}/{session_id.replace('_preview', '')}_preview.json",  # Old format
        ]
    else:
        paths = []
    
    for path in paths:
        try:
            response = s3_client.get_object(Bucket='perplexity-results', Key=path)
            content = json.loads(response['Body'].read())
            print(f"✅ Found S3 preview at: {path}")
            return content, path
        except s3_client.exceptions.NoSuchKey:
            continue
        except Exception as e:
            if 'verbose' in globals() and verbose:
                print(f"Error checking {path}: {e}")
    
    return None, None

def wait_for_dynamodb_update(session_id, timeout=10):
    """Wait for DynamoDB to be updated with a timeout"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        record = get_dynamodb_record(session_id)
        if record and record.get('status') != 'queued':
            return record
        time.sleep(1)
    return get_dynamodb_record(session_id)  # One final check

def check_network_connectivity():
    """Check network connectivity to AWS services"""
    print("\n🔍 Checking network connectivity...")
    
    # Check DNS resolution
    try:
        import socket
        api_host = API_URL.split('//')[1].split('/')[0]
        ip = socket.gethostbyname(api_host)
        print(f"✅ DNS resolution OK: {api_host} -> {ip}")
    except socket.gaierror as e:
        print(f"❌ DNS resolution failed: {e}")
        print(f"   Please check your internet connection")
        return False
    
    # Check API Gateway connectivity
    try:
        response = requests.get(f"{STATUS_URL}/test", timeout=5)
        if response.status_code in [200, 400, 404]:  # Any response means connection works
            print(f"✅ API Gateway reachable (status: {response.status_code})")
        else:
            print(f"⚠️  API Gateway returned unexpected status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot reach API Gateway: {type(e).__name__}")
        return False
    
    # Check AWS connectivity
    try:
        s3_client.list_buckets()
        print(f"✅ AWS S3 connectivity OK")
    except Exception as e:
        print(f"⚠️  AWS S3 connectivity issue: {type(e).__name__}")
        print(f"   (This may be OK if using IAM roles)")
    
    return True

def test_sync_preview(args, output_dir):
    """Test synchronous preview"""
    print_test_header("SYNC PREVIEW TEST", args, output_dir)
    
    # Check if files exist
    if not os.path.exists(args.excel):
        print(f"❌ Excel file not found: {args.excel}")
        return None
    if not os.path.exists(args.config):
        print(f"❌ Config file not found: {args.config}")
        return None
    
    # Read files
    with open(args.excel, 'rb') as excel_file:
        with open(args.config, 'r') as config_file:
            config_data = json.load(config_file)
            
            files = {
                'excel_file': (Path(args.excel).name, excel_file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                'config_file': (Path(args.config).name, json.dumps(config_data), 'application/json')
            }
            data = {
                'email': args.email
            }
            
            print(f"📤 Sending sync preview request ({args.preview_rows} rows)...")
            print(f"   Excel size: {os.path.getsize(args.excel):,} bytes")
            print(f"   Config size: {os.path.getsize(args.config):,} bytes")
            
            start_time = time.time()
            response = requests.post(
                f"{API_URL}?preview_first_row=true&max_rows={args.preview_rows}",
                files=files,
                data=data
            )
            request_time = time.time() - start_time
    
    print(f"⏱️  Request time: {request_time:.2f}s")
    print(f"📡 Response status: {response.status_code}")
    
    # Save raw response
    log_output(output_dir, "01_sync_preview_response.json", {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": response.text,
        "request_time": request_time
    })
    
    if response.status_code == 200:
        result = response.json()
        log_output(output_dir, "01_sync_preview_result.json", result)
        
        print(f"✅ Success!")
        if 'session_id' in result:
            print(f"Session ID: {result.get('session_id')}")
        print(f"Reference PIN: {result.get('reference_pin')}")
        
        # Display and save preview table
        if 'markdown_table' in result:
            print("\n📋 PREVIEW OUTPUT:")
            print("-" * 80)
            print(result['markdown_table'])
            print("-" * 80)
            log_output(output_dir, "01_sync_preview_table.md", result['markdown_table'])
        
        # Get DynamoDB record
        if 'session_id' in result:
            print("\n⏳ Waiting for DynamoDB update...")
            db_record = wait_for_dynamodb_update(result['session_id'])
            if db_record:
                log_output(output_dir, "01_sync_preview_dynamodb.json", db_record)
                print(f"📊 DynamoDB Status: {db_record.get('status')}")
                print(f"   Total cost: ${float(db_record.get('total_cost_usd', 0)):.6f}")
                print(f"   Processing time: {float(db_record.get('processing_time_seconds', 0)):.2f}s")
                print(f"   Total tokens: {db_record.get('total_tokens', 0)}")
        
        return result
    else:
        print(f"❌ Failed: {response.text}")
        return None

def test_async_preview(args, output_dir):
    """Test asynchronous preview"""
    print_test_header("ASYNC PREVIEW TEST", args, output_dir)
    
    with open(args.excel, 'rb') as excel_file:
        with open(args.config, 'r') as config_file:
            config_data = json.load(config_file)
            
            files = {
                'excel_file': (Path(args.excel).name, excel_file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                'config_file': (Path(args.config).name, json.dumps(config_data), 'application/json')
            }
            data = {
                'email': args.email
            }
            
            print(f"📤 Sending async preview request ({args.preview_rows} rows)...")
            response = requests.post(
                f"{API_URL}?preview_first_row=true&async=true&max_rows={args.preview_rows}",
                files=files,
                data=data
            )
    
    print(f"📡 Response status: {response.status_code}")
    log_output(output_dir, "02_async_preview_initial_response.json", {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": response.text if response.status_code != 200 else response.json()
    })
    
    if response.status_code == 200:
        result = response.json()
        session_id = result.get('session_id')
        print(f"✅ Queued!")
        print(f"Session ID: {session_id}")
        print(f"Reference PIN: {result.get('reference_pin')}")
        
        # Poll for completion
        print("\n⏳ Polling for completion...")
        completed = False
        max_polls = 30  # Poll for up to 150 seconds
        
        for i in range(max_polls):
            time.sleep(5)
            
            # Check status via API
            status_response = requests.get(f"{STATUS_URL}/{session_id}?preview=true")
            if status_response.status_code == 200:
                status_data = status_response.json()
                status = status_data.get('status')
                print(f"   Poll {i+1}: Status = {status}")
                
                if i == 0:  # Save first status check
                    log_output(output_dir, "02_async_preview_status_first.json", status_data)
                
                if status in ['completed', 'preview_completed']:
                    log_output(output_dir, "02_async_preview_status_final.json", status_data)
                    completed = True
                    break
                elif status == 'preview_error':
                    print(f"❌ Preview failed with error")
                    log_output(output_dir, "02_async_preview_error.json", status_data)
                    break
        
        if completed:
            print("✅ Preview completed!")
            
            # Get S3 preview results
            preview_data, s3_path = get_s3_preview(session_id, args.email)
            if preview_data:
                log_output(output_dir, "02_async_preview_s3_results.json", preview_data)
                log_output(output_dir, "02_async_preview_s3_path.txt", s3_path)
                
                if 'markdown_table' in preview_data:
                    print("\n📋 PREVIEW OUTPUT (from S3):")
                    print("-" * 80)
                    print(preview_data['markdown_table'])
                    print("-" * 80)
                    log_output(output_dir, "02_async_preview_table.md", preview_data['markdown_table'])
                
                # Save cost estimates
                if 'cost_estimates' in preview_data:
                    print(f"\n💰 Cost Estimates:")
                    estimates = preview_data['cost_estimates']
                    print(f"   Preview cost: ${estimates.get('preview_cost', 0):.3f}")
                    print(f"   Estimated total: ${estimates.get('estimated_total_cost', 0):.2f}")
                    print(f"   Estimated time: {preview_data.get('estimated_total_time_minutes', 0):.1f} minutes")
            
            # Get DynamoDB record
            db_record = get_dynamodb_record(session_id)
            if db_record:
                log_output(output_dir, "02_async_preview_dynamodb.json", db_record)
                print(f"\n📊 DynamoDB Metrics:")
                print(f"   Status: {db_record.get('status')}")
                print(f"   Total cost: ${float(db_record.get('total_cost_usd', 0)):.6f}")
                print(f"   Processing time: {float(db_record.get('processing_time_seconds', 0)):.2f}s")
        else:
            print("⏱️  Timeout waiting for preview completion")
        
        return result
    else:
        print(f"❌ Failed: {response.text}")
        return None

def test_full_validation(args, output_dir):
    """Test full validation"""
    print_test_header("FULL VALIDATION TEST", args, output_dir)
    
    with open(args.excel, 'rb') as excel_file:
        with open(args.config, 'r') as config_file:
            config_data = json.load(config_file)
            
            files = {
                'excel_file': (Path(args.excel).name, excel_file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                'config_file': (Path(args.config).name, json.dumps(config_data), 'application/json')
            }
            data = {
                'email': args.email
            }
            
            print(f"📤 Sending full validation request (max {args.max_rows} rows)...")
            response = requests.post(
                f"{API_URL}?max_rows={args.max_rows}",
                files=files,
                data=data
            )
    
    print(f"📡 Response status: {response.status_code}")
    log_output(output_dir, "03_full_validation_initial_response.json", {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": response.text if response.status_code != 200 else response.json()
    })
    
    if response.status_code == 200:
        result = response.json()
        session_id = result.get('session_id')
        reference_pin = result.get('reference_pin')
        print(f"✅ Started!")
        print(f"Session ID: {session_id}")
        print(f"Reference PIN: {reference_pin}")
        
        # Monitor progress
        print("\n⏳ Monitoring progress...")
        completed = False
        max_polls = 60  # Poll for up to 5 minutes
        
        for i in range(max_polls):
            time.sleep(5)
            
            # Check DynamoDB for detailed progress
            db_record = get_dynamodb_record(session_id)
            if db_record:
                status = db_record.get('status')
                processed = db_record.get('processed_rows', 0)
                total = db_record.get('total_rows', 0)
                print(f"   Poll {i+1}: Status = {status}, Processed = {processed}/{total}")
                
                if i == 0:  # Save first status
                    log_output(output_dir, "03_full_validation_dynamodb_first.json", db_record)
                
                if status == 'completed':
                    log_output(output_dir, "03_full_validation_dynamodb_final.json", db_record)
                    completed = True
                    break
                elif status == 'error':
                    print(f"❌ Error: {db_record.get('error_messages', [])}")
                    log_output(output_dir, "03_full_validation_error.json", db_record)
                    break
        
        if completed:
            print("\n✅ Validation completed!")
            print(f"\n📊 Final DynamoDB Metrics:")
            print(f"   Total rows: {db_record.get('total_rows')}")
            print(f"   Processed rows: {db_record.get('processed_rows')}")
            print(f"   Total cost: ${float(db_record.get('total_cost_usd', 0)):.6f}")
            print(f"   Processing time: {float(db_record.get('processing_time_seconds', 0)):.2f}s")
            print(f"   Total tokens: {db_record.get('total_tokens')}")
            
            # Quality metrics
            print(f"\n📈 Quality Metrics:")
            print(f"   HIGH confidence: {db_record.get('high_confidence_count', 0)}")
            print(f"   MEDIUM confidence: {db_record.get('medium_confidence_count', 0)}")
            print(f"   LOW confidence: {db_record.get('low_confidence_count', 0)}")
            print(f"   Accuracy score: {float(db_record.get('validation_accuracy_score', 0)):.2%}")
            
            if db_record.get('email_sent'):
                print(f"\n📧 Email Status:")
                print(f"   Sent: {db_record.get('email_sent')}")
                print(f"   Status: {db_record.get('email_delivery_status')}")
                print(f"   Message ID: {db_record.get('email_message_id')}")
            
            # Save S3 paths
            s3_info = {
                "excel_s3_key": db_record.get('excel_s3_key'),
                "config_s3_key": db_record.get('config_s3_key'),
                "results_s3_key": db_record.get('results_s3_key')
            }
            log_output(output_dir, "03_full_validation_s3_paths.json", s3_info)
        else:
            print("⏱️  Timeout waiting for validation completion")
        
        return result
    else:
        print(f"❌ Failed: {response.text}")
        return None 

def generate_summary(results, output_dir, args):
    """Generate test summary report"""
    summary = {
        "test_timestamp": datetime.now().isoformat(),
        "test_name": args.name,
        "configuration": {
            "email": args.email,
            "excel_file": args.excel,
            "config_file": args.config,
            "mode": args.mode,
            "max_rows": args.max_rows,
            "preview_rows": args.preview_rows,
            "output_directory": str(output_dir)
        },
        "results": {},
        "overall_status": "PASSED"
    }
    
    # Markdown summary
    md_lines = [
        f"# Test Summary Report",
        f"",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Test Name**: {args.name or 'unnamed'}",
        f"**Mode**: {args.mode}",
        f"",
        f"## Configuration",
        f"- **Email**: {args.email}",
        f"- **Excel**: {Path(args.excel).name}",
        f"- **Config**: {Path(args.config).name}",
        f"- **Max Rows**: {args.max_rows}",
        f"- **Preview Rows**: {args.preview_rows}",
        f"",
        f"## Test Results",
        f""
    ]
    
    # Process each test result
    for test_name, result in results.items():
        if result is None:
            status = "FAILED"
            summary["overall_status"] = "FAILED"
            details = "Test failed or was skipped"
        else:
            status = "PASSED"
            details = f"Session ID: {result.get('session_id', 'N/A')}"
        
        summary["results"][test_name] = {
            "status": status,
            "details": result if result else {"error": "Test failed"}
        }
        
        md_lines.append(f"### {test_name.replace('_', ' ').title()}")
        md_lines.append(f"- **Status**: {status}")
        md_lines.append(f"- **Details**: {details}")
        md_lines.append(f"")
    
    # Save summary files
    log_output(output_dir, "00_test_summary.json", summary)
    log_output(output_dir, "00_test_summary.md", "\n".join(md_lines))
    
    return summary

def main():
    """Main test runner"""
    args = parse_arguments()
    
    # Set global verbose flag
    global verbose
    verbose = args.verbose
    
    # Setup output directory
    output_dir = setup_output_directory(args)
    
    print(f"🚀 PERPLEXITY VALIDATOR END-TO-END TEST")
    print(f"📅 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Output directory: {output_dir}")
    print(f"📧 Email: {args.email}")
    print(f"📄 Excel: {args.excel}")
    print(f"⚙️  Config: {args.config}")
    print(f"🎯 Mode: {args.mode}")
    
    # Check network connectivity before starting tests
    if not check_network_connectivity():
        print("\n❌ Network connectivity check failed!")
        print("Please check your internet connection and try again.")
        return 1
    
    # Save test configuration
    test_config = {
        "timestamp": datetime.now().isoformat(),
        "arguments": vars(args),
        "environment": {
            "api_url": API_URL,
            "status_url": STATUS_URL,
            "python_version": sys.version
        }
    }
    log_output(output_dir, "00_test_config.json", test_config)
    
    # Run tests based on mode
    results = {}
    
    try:
        if args.mode == 'all':
            # Run all tests
            results['sync_preview'] = test_sync_preview(args, output_dir)
            results['async_preview'] = test_async_preview(args, output_dir)
            results['full_validation'] = test_full_validation(args, output_dir)
        elif args.mode == 'sync_preview':
            results['sync_preview'] = test_sync_preview(args, output_dir)
        elif args.mode == 'async_preview':
            results['async_preview'] = test_async_preview(args, output_dir)
        elif args.mode == 'full_validation':
            results['full_validation'] = test_full_validation(args, output_dir)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test error: {str(e)}")
        import traceback
        error_details = traceback.format_exc()
        print(error_details)
        log_output(output_dir, "00_test_error.txt", error_details)
    
    # Generate summary
    summary = generate_summary(results, output_dir, args)
    
    # Final output
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    print(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 Overall Status: {summary['overall_status']}")
    
    for test_name, test_data in summary['results'].items():
        status_icon = "✅" if test_data['status'] == "PASSED" else "❌"
        print(f"{status_icon} {test_name.replace('_', ' ').title()}: {test_data['status']}")
    
    print(f"\n📁 All outputs saved to: {output_dir}")
    print(f"📝 Summary available at: {output_dir / '00_test_summary.md'}")
    
    # Return exit code based on overall status
    return 0 if summary['overall_status'] == "PASSED" else 1

if __name__ == "__main__":
    sys.exit(main()) 