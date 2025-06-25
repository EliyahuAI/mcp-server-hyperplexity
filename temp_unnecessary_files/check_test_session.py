import boto3
from datetime import datetime
import json

# Initialize S3 client
s3_client = boto3.client('s3', region_name='us-east-1')

# Test session ID
SESSION_ID = "37322e06-8172-4101-8a9a-c198f9270090"

def check_session_files():
    """Check S3 for files related to our test session"""
    
    print(f"Checking S3 for session: {SESSION_ID}")
    print("="*60)
    
    # Check cache bucket for uploads
    print("\nChecking uploads in perplexity-cache...")
    try:
        response = s3_client.list_objects_v2(
            Bucket='perplexity-cache',
            Prefix=f'uploads/{SESSION_ID}/'
        )
        
        if 'Contents' in response:
            print(f"✓ Found {len(response['Contents'])} uploaded files:")
            for obj in response['Contents']:
                print(f"  - {obj['Key']}")
                print(f"    Size: {obj['Size']:,} bytes")
                print(f"    Modified: {obj['LastModified']}")
        else:
            print("✗ No uploaded files found")
    except Exception as e:
        print(f"Error: {e}")
    
    # Check results bucket
    print("\nChecking results in perplexity-results...")
    try:
        response = s3_client.list_objects_v2(
            Bucket='perplexity-results',
            Prefix=f'results/{SESSION_ID}/'
        )
        
        if 'Contents' in response:
            print(f"✓ Found {len(response['Contents'])} result files:")
            for obj in response['Contents']:
                print(f"  - {obj['Key']}")
                print(f"    Size: {obj['Size']:,} bytes")
                print(f"    Modified: {obj['LastModified']}")
                
                # If it's the results zip, check if it's still placeholder
                if obj['Size'] < 1000:  # Small file likely placeholder
                    print("    ⚠️  Small file - likely still placeholder")
                else:
                    print("    ✓ Full results file")
        else:
            print("✗ No result files found")
    except Exception as e:
        print(f"Error: {e}")
    
    # Check email logs
    print("\nChecking email logs in perplexity-cache...")
    try:
        response = s3_client.list_objects_v2(
            Bucket='perplexity-cache',
            Prefix=f'email_logs/{SESSION_ID}/'
        )
        
        if 'Contents' in response:
            print(f"✓ Found {len(response['Contents'])} email log files:")
            for obj in response['Contents']:
                print(f"  - {obj['Key']}")
                
                # Try to read email metadata
                if 'email_metadata.json' in obj['Key']:
                    try:
                        metadata_response = s3_client.get_object(
                            Bucket='perplexity-cache',
                            Key=obj['Key']
                        )
                        metadata = json.loads(metadata_response['Body'].read())
                        print(f"    Email sent to: {metadata.get('Recipient')}")
                        print(f"    Message ID: {metadata.get('MessageID')}")
                        print(f"    Timestamp: {metadata.get('Timestamp')}")
                    except:
                        pass
        else:
            print("✗ No email logs found")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_session_files() 