import boto3
import json
import zipfile
import io
from datetime import datetime

# Initialize S3 client
s3_client = boto3.client('s3', region_name='us-east-1')

# Test session
SESSION_ID = "37322e06-8172-4101-8a9a-c198f9270090"
RESULTS_KEY = f"results/{SESSION_ID}/20250609_162504_results.zip"

def download_and_examine_results():
    """Download and examine the results file"""
    
    print(f"Downloading results for session: {SESSION_ID}")
    print("="*60)
    
    try:
        # Download the file
        response = s3_client.get_object(
            Bucket='perplexity-results',
            Key=RESULTS_KEY
        )
        
        zip_content = response['Body'].read()
        print(f"✓ Downloaded {len(zip_content):,} bytes")
        print(f"  Last Modified: {response['LastModified']}")
        
        # Save locally for inspection
        local_filename = f"test_results_{SESSION_ID[:8]}.zip"
        with open(local_filename, 'wb') as f:
            f.write(zip_content)
        print(f"\n✓ Saved to: {local_filename}")
        
        # Examine ZIP contents
        print("\nZIP contents:")
        print("-"*40)
        
        with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zip_file:
            for info in zip_file.filelist:
                print(f"  {info.filename}")
                print(f"    Size: {info.file_size:,} bytes")
                print(f"    Modified: {datetime(*info.date_time)}")
                
                # Read and show snippets of text files
                if info.filename.endswith('.txt') or info.filename.endswith('.json'):
                    content = zip_file.read(info.filename).decode('utf-8')
                    lines = content.split('\n')
                    print(f"    First few lines:")
                    for line in lines[:5]:
                        if line.strip():
                            print(f"      {line[:80]}...")
                    print()
                    
                # Check if it's enhanced Excel
                if info.filename.endswith('.xlsx'):
                    print(f"    ✓ Enhanced Excel file found!")
                    
        # Check for validation results JSON
        try:
            with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zip_file:
                if 'validation_results.json' in zip_file.namelist():
                    results_json = json.loads(zip_file.read('validation_results.json'))
                    summary = results_json.get('summary', {})
                    print("\nValidation Summary:")
                    print(f"  Total rows: {summary.get('total_rows', 'N/A')}")
                    print(f"  Fields validated: {len(summary.get('fields_validated', []))}")
                    if summary.get('fields_validated'):
                        print(f"    {', '.join(summary['fields_validated'])}")
                    print(f"  Confidence distribution:")
                    for level, count in summary.get('confidence_distribution', {}).items():
                        print(f"    {level}: {count}")
        except Exception as e:
            print(f"\nCouldn't parse validation results: {e}")
            
    except Exception as e:
        print(f"Error downloading results: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    download_and_examine_results() 