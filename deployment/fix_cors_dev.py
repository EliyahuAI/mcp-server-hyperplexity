#!/usr/bin/env python3
"""
Fix CORS configuration for hyperplexity-storage-dev bucket to allow PDF uploads.
This adds support for presigned URL uploads with metadata headers.
"""

import boto3
import json

def fix_cors_for_dev_bucket():
    """Update CORS configuration for the dev bucket"""

    bucket_name = 'hyperplexity-storage-dev'
    s3_client = boto3.client('s3')

    print(f"Updating CORS configuration for bucket: {bucket_name}")

    # CORS configuration that allows presigned URL uploads
    cors_config = {
        'CORSRules': [
            {
                'ID': 'DownloadRule',
                'AllowedHeaders': ['Content-Type', 'Authorization', 'X-Session-Token'],
                'AllowedMethods': ['GET', 'HEAD'],  # Only read operations for downloads
                'AllowedOrigins': [
                    'https://hyperplexity.ai',
                    'https://www.hyperplexity.ai',
                    'https://eliyahu.ai',
                    'https://www.eliyahu.ai',
                    'http://localhost:8000',  # Local development
                    'http://localhost:3000'   # Additional local dev port
                ],
                'ExposeHeaders': ['ETag', 'Content-Length', 'Content-Disposition'],
                'MaxAgeSeconds': 600
            },
            {
                'ID': 'UploadRule',
                'AllowedHeaders': ['*'],  # Allow all headers for presigned URL uploads (includes x-amz-meta-*, x-amz-security-token, etc.)
                'AllowedMethods': ['PUT', 'POST'],  # Write operations
                'AllowedOrigins': [
                    'https://hyperplexity.ai',
                    'https://www.hyperplexity.ai',
                    'https://eliyahu.ai',
                    'https://www.eliyahu.ai',
                    'http://localhost:8000',
                    'http://localhost:3000'
                ],
                'ExposeHeaders': ['ETag'],  # Expose ETag for upload confirmation
                'MaxAgeSeconds': 600
            }
        ]
    }

    try:
        # Apply CORS configuration
        s3_client.put_bucket_cors(
            Bucket=bucket_name,
            CORSConfiguration=cors_config
        )

        print("✅ CORS configuration updated successfully!")
        print("\nUpdated rules:")
        print("  - DownloadRule: GET/HEAD from allowed origins")
        print("  - UploadRule: PUT/POST with all headers allowed (for presigned URLs)")
        print("\nAllowed origins:")
        print("  - https://hyperplexity.ai")
        print("  - https://www.hyperplexity.ai")
        print("  - https://eliyahu.ai")
        print("  - https://www.eliyahu.ai")
        print("  - http://localhost:8000 (dev)")
        print("  - http://localhost:3000 (dev)")

        return True

    except Exception as e:
        print(f"❌ Error updating CORS configuration: {e}")
        return False

if __name__ == "__main__":
    print("=" * 70)
    print("Fixing CORS Configuration for Dev Bucket")
    print("=" * 70)
    print()

    if fix_cors_for_dev_bucket():
        print("\n[SUCCESS] Dev bucket CORS configuration fixed!")
        print("\nYou should now be able to upload PDFs from localhost:8000")
    else:
        print("\n[FAILED] Could not update CORS configuration")
        print("Make sure AWS credentials are configured correctly")
