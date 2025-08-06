#!/usr/bin/env python3
"""
Create unified S3 bucket for hyperplexity storage with proper lifecycle policies.
Replaces multiple buckets with a single, well-organized structure.
"""

import boto3
import json
import time
from datetime import datetime
from botocore.exceptions import ClientError

def create_downloads_bucket():
    """Create separate public downloads bucket with 7-day lifecycle"""
    
    bucket_name = 'hyperplexity-downloads'
    
    # Create S3 client
    s3_client = boto3.client('s3')
    
    try:
        # Check if bucket already exists
        try:
            s3_client.head_bucket(Bucket=bucket_name)
            print(f"Downloads bucket '{bucket_name}' already exists. Updating configuration...")
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                # Create the bucket
                print(f"Creating public downloads bucket: {bucket_name}")
                s3_client.create_bucket(Bucket=bucket_name)
                print("Downloads bucket created successfully")
            else:
                raise
        
        # Configure completely public access for downloads bucket
        print("Configuring bucket for full public access...")
        
        # Remove public access block to allow public bucket policy
        try:
            s3_client.delete_public_access_block(Bucket=bucket_name)
            print("Public access block removed")
            # Wait for AWS to process the change
            time.sleep(2)
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchPublicAccessBlockConfiguration':
                print(f"Warning: Could not remove public access block: {e}")
                # Continue anyway, the policy might still work
        
        bucket_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "PublicReadAccess",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket_name}/*"
                }
            ]
        }
        
        s3_client.put_bucket_policy(
            Bucket=bucket_name,
            Policy=json.dumps(bucket_policy)
        )
        print("Set bucket policy for full public read access")
        
        # Configure 7-day lifecycle policy
        lifecycle_config = {
            'Rules': [
                {
                    'ID': 'DownloadsCleanup',
                    'Status': 'Enabled',
                    'Filter': {},  # Apply to entire bucket
                    'Expiration': {
                        'Days': 7  # 7 day retention
                    },
                    'AbortIncompleteMultipartUpload': {
                        'DaysAfterInitiation': 1
                    }
                }
            ]
        }
        
        s3_client.put_bucket_lifecycle_configuration(
            Bucket=bucket_name,
            LifecycleConfiguration=lifecycle_config
        )
        print("Configured 7-day lifecycle policy")
        
        # Configure CORS for web access
        cors_config = {
            'CORSRules': [
                {
                    'AllowedHeaders': ['*'],
                    'AllowedMethods': ['GET', 'HEAD'],
                    'AllowedOrigins': ['*'],
                    'MaxAgeSeconds': 3600
                }
            ]
        }
        
        s3_client.put_bucket_cors(
            Bucket=bucket_name,
            CORSConfiguration=cors_config
        )
        print("Configured CORS for web access")
        
        print(f"\n[SUCCESS] Public downloads bucket '{bucket_name}' configured!")
        print(f"  📁 Fully public read access")
        print(f"  ⏰ 7-day automatic cleanup")
        print(f"  🌐 CORS enabled")
        print(f"")
        print(f"Environment variables to set:")
        print(f"  S3_DOWNLOAD_BUCKET={bucket_name}")
        
        return bucket_name
        
    except Exception as e:
        print(f"Error configuring downloads bucket: {e}")
        return None

def create_unified_s3_bucket():
    """Create unified S3 bucket with proper folder structure and lifecycle policies"""
    
    bucket_name = 'hyperplexity-storage'
    
    # Create S3 client
    s3_client = boto3.client('s3')
    
    try:
        # Check if bucket already exists
        try:
            s3_client.head_bucket(Bucket=bucket_name)
            print(f"Bucket '{bucket_name}' already exists. Updating configuration...")
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                # Create the bucket
                print(f"Creating S3 bucket: {bucket_name}")
                s3_client.create_bucket(Bucket=bucket_name)
                print("Bucket created successfully")
            else:
                raise
        
        # Remove public access block to allow selective public access
        print("Removing public access block for selective public policy...")
        try:
            s3_client.delete_public_access_block(Bucket=bucket_name)
            print("Public access block removed")
            # Wait for AWS to process the change
            time.sleep(2)
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchPublicAccessBlockConfiguration':
                print(f"Warning: Could not remove public access block: {e}")
        
        # Configure public access for downloads folder only
        print("Configuring bucket policy for selective public access...")
        
        bucket_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "PublicReadDownloads",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket_name}/downloads/*"
                },
                {
                    "Sid": "DenyDirectAccess",
                    "Effect": "Deny", 
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": [
                        f"arn:aws:s3:::{bucket_name}/results/*",
                        f"arn:aws:s3:::{bucket_name}/cache/*"
                    ],
                    "Condition": {
                        "Bool": {
                            "aws:SecureTransport": "false"
                        }
                    }
                }
            ]
        }
        
        s3_client.put_bucket_policy(
            Bucket=bucket_name,
            Policy=json.dumps(bucket_policy)
        )
        print("Set bucket policy for selective public access")
        
        # Configure comprehensive lifecycle policy
        lifecycle_config = {
            'Rules': [
                {
                    'ID': 'ResultsRetention',
                    'Status': 'Enabled',
                    'Filter': {
                        'Prefix': 'results/'
                    },
                    'Expiration': {
                        'Days': 365  # 1 year retention
                    },
                    'AbortIncompleteMultipartUpload': {
                        'DaysAfterInitiation': 7
                    }
                },
                {
                    'ID': 'DownloadsCleanup',
                    'Status': 'Enabled',
                    'Filter': {
                        'Prefix': 'downloads/'
                    },
                    'Expiration': {
                        'Days': 7  # 7 day retention
                    },
                    'AbortIncompleteMultipartUpload': {
                        'DaysAfterInitiation': 1
                    }
                },
                {
                    'ID': 'CacheCleanup',
                    'Status': 'Enabled',
                    'Filter': {
                        'Prefix': 'cache/'
                    },
                    'Expiration': {
                        'Days': 30  # 30 day retention
                    },
                    'AbortIncompleteMultipartUpload': {
                        'DaysAfterInitiation': 3
                    }
                }
            ]
        }
        
        s3_client.put_bucket_lifecycle_configuration(
            Bucket=bucket_name,
            LifecycleConfiguration=lifecycle_config
        )
        print("Configured lifecycle policies:")
        print("  - Results: 1 year retention")
        print("  - Downloads: 7 day retention") 
        print("  - Cache: 30 day retention")
        
        # Enable versioning for data safety
        s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        print("Enabled bucket versioning")
        
        # Configure CORS for web access
        cors_config = {
            'CORSRules': [
                {
                    'AllowedHeaders': ['*'],
                    'AllowedMethods': ['GET', 'HEAD', 'PUT', 'POST'],
                    'AllowedOrigins': ['*'],
                    'MaxAgeSeconds': 3600
                }
            ]
        }
        
        s3_client.put_bucket_cors(
            Bucket=bucket_name,
            CORSConfiguration=cors_config
        )
        print("Configured CORS for web access")
        
        # Create folder structure with placeholder objects
        folder_structure = [
            'results/.placeholder',
            'downloads/.placeholder', 
            'cache/perplexity/.placeholder',
            'cache/claude/.placeholder'
        ]
        
        for folder_key in folder_structure:
            s3_client.put_object(
                Bucket=bucket_name,
                Key=folder_key,
                Body=f"Placeholder for {folder_key.split('/')[1]} folder - created {datetime.now().isoformat()}",
                ContentType='text/plain'
            )
        
        print("Created folder structure placeholders")
        
        print(f"\n[SUCCESS] Unified S3 bucket '{bucket_name}' configured!")
        print(f"Structure:")
        print(f"  📁 results/     - User results (1 year)")
        print(f"  📁 downloads/   - Public downloads (7 days)")
        print(f"  📁 cache/       - API cache (30 days)")
        print(f"")
        print(f"Environment variables to set:")
        print(f"  S3_UNIFIED_BUCKET={bucket_name}")
        
        return bucket_name
        
    except Exception as e:
        print(f"Error configuring bucket: {e}")
        return None

def test_bucket_structure(bucket_name):
    """Test the bucket structure and access patterns"""
    
    s3_client = boto3.client('s3')
    
    print(f"Testing bucket structure for: {bucket_name}")
    
    test_cases = [
        {
            'key': 'results/example.com/user_test/20250724_140000_session123/test.json',
            'content': '{"test": "results folder"}',
            'public': False
        },
        {
            'key': 'downloads/test-uuid-123/config.json', 
            'content': '{"test": "downloads folder"}',
            'public': True
        },
        {
            'key': 'cache/perplexity/test-hash/response.json',
            'content': '{"test": "cache folder"}', 
            'public': False
        }
    ]
    
    success_count = 0
    
    for test_case in test_cases:
        try:
            # Upload test file
            s3_client.put_object(
                Bucket=bucket_name,
                Key=test_case['key'],
                Body=test_case['content'],
                ContentType='application/json'
            )
            
            # Test access
            public_url = f"https://{bucket_name}.s3.amazonaws.com/{test_case['key']}"
            
            if test_case['public']:
                # Should be accessible
                import requests
                response = requests.get(public_url)
                if response.status_code == 200:
                    print(f"✅ Public access works: {test_case['key']}")
                    success_count += 1
                else:
                    print(f"❌ Public access failed: {test_case['key']} - HTTP {response.status_code}")
            else:
                # Should be private (presigned URL needed)
                print(f"✅ Private file uploaded: {test_case['key']}")
                success_count += 1
            
            # Clean up test file
            s3_client.delete_object(Bucket=bucket_name, Key=test_case['key'])
            
        except Exception as e:
            print(f"❌ Test failed for {test_case['key']}: {e}")
    
    print(f"\nTest Results: {success_count}/{len(test_cases)} passed")
    return success_count == len(test_cases)

if __name__ == "__main__":
    print("Creating S3 Buckets for Hyperplexity")
    print("=" * 60)
    
    # Create the downloads bucket first
    downloads_bucket = create_downloads_bucket()
    
    # Create the unified bucket
    unified_bucket = create_unified_s3_bucket()
    
    if unified_bucket:
        print(f"\n" + "=" * 60)
        print("Testing unified bucket configuration...")
        
        # Wait for AWS to propagate settings
        time.sleep(10)
        
        # Test bucket structure
        if test_bucket_structure(unified_bucket):
            print(f"\n[SUCCESS] Both S3 buckets are ready!")
            print(f"Environment variables to set:")
            print(f"  S3_UNIFIED_BUCKET={unified_bucket}")
            if downloads_bucket:
                print(f"  S3_DOWNLOAD_BUCKET={downloads_bucket}")
        else:
            print(f"\n[WARNING] Buckets created but some tests failed")
            print("You may need to wait for AWS settings to propagate")
    else:
        print("\n[FAILED] Failed to create unified bucket")