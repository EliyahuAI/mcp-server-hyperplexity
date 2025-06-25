import boto3
from datetime import datetime, timedelta

# Initialize S3 client
s3_client = boto3.client('s3', region_name='us-east-1')

# Buckets
CACHE_BUCKET = 'perplexity-cache'
RESULTS_BUCKET = 'perplexity-results'

def check_bucket_contents(bucket_name, prefix=''):
    """Check contents of an S3 bucket"""
    print(f"\n{'='*60}")
    print(f"S3 Bucket: {bucket_name}")
    if prefix:
        print(f"Prefix: {prefix}")
    print("="*60)
    
    try:
        # List objects
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix,
            MaxKeys=50
        )
        
        if 'Contents' not in response:
            print("No objects found")
            return
            
        objects = response['Contents']
        print(f"Found {len(objects)} objects")
        
        # Sort by last modified
        objects.sort(key=lambda x: x['LastModified'], reverse=True)
        
        # Show recent objects
        for obj in objects[:20]:  # Show max 20 most recent
            key = obj['Key']
            size = obj['Size']
            modified = obj['LastModified']
            age = datetime.now(modified.tzinfo) - modified
            
            print(f"\n  {key}")
            print(f"    Size: {size:,} bytes")
            print(f"    Modified: {modified.strftime('%Y-%m-%d %H:%M:%S')} UTC ({age.total_seconds()/60:.1f} min ago)")
            
            # Check if this matches our test sessions
            if any(session_id in key for session_id in [
                'bb43b6d5-2e1e-4532-b041-954ebeb74091',  # From test_email_functionality
                '4d6b51b9-46e8-41ce-85ca-5ee549525181',  # Preview test
                'cfc12d7b-a40d-4c57-befc-f5402913b'     # Direct invocation test
            ]):
                print("    ⚠️  MATCHES TEST SESSION!")
                
    except Exception as e:
        print(f"Error checking bucket: {e}")

def check_specific_sessions():
    """Check for specific test session files"""
    print("\n" + "="*60)
    print("Checking for specific test sessions")
    print("="*60)
    
    test_sessions = [
        ('bb43b6d5-2e1e-4532-b041-954ebeb74091', 'test_email_functionality.py'),
        ('4d6b51b9-46e8-41ce-85ca-5ee549525181', 'preview mode test'),
        ('cfc12d7b-a40d-4c57-befc-f5402913b', 'direct lambda invocation')
    ]
    
    for session_id, description in test_sessions:
        print(f"\nSession: {session_id} ({description})")
        
        # Check uploads in cache bucket
        try:
            upload_prefix = f"uploads/{session_id}/"
            response = s3_client.list_objects_v2(
                Bucket=CACHE_BUCKET,
                Prefix=upload_prefix
            )
            
            if 'Contents' in response:
                print(f"  ✓ Found {len(response['Contents'])} uploaded files")
                for obj in response['Contents']:
                    print(f"    - {obj['Key'].split('/')[-1]}")
            else:
                print("  ✗ No uploaded files found")
                
        except Exception as e:
            print(f"  Error checking uploads: {e}")
            
        # Check results
        try:
            results_prefix = f"results/{session_id}/"
            response = s3_client.list_objects_v2(
                Bucket=RESULTS_BUCKET,
                Prefix=results_prefix
            )
            
            if 'Contents' in response:
                print(f"  ✓ Found {len(response['Contents'])} result files")
                for obj in response['Contents']:
                    print(f"    - {obj['Key'].split('/')[-1]} ({obj['Size']:,} bytes)")
            else:
                print("  ✗ No result files found")
                
        except Exception as e:
            print(f"  Error checking results: {e}")

if __name__ == "__main__":
    print("S3 Results Check")
    
    # Check cache bucket uploads
    check_bucket_contents(CACHE_BUCKET, 'uploads/')
    
    # Check results bucket
    check_bucket_contents(RESULTS_BUCKET, 'results/')
    
    # Check specific sessions
    check_specific_sessions() 