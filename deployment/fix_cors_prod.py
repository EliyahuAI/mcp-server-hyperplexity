#!/usr/bin/env python3
"""
Fix CORS configuration for hyperplexity-storage (PRODUCTION) bucket.
"""

import boto3
import json

def fix_cors_for_prod_bucket():
    """Update CORS configuration for the production bucket"""

    bucket_name = 'hyperplexity-storage'
    s3_client = boto3.client('s3')

    print(f"Updating CORS configuration for bucket: {bucket_name}")

    # Load the CORS configuration from file
    with open('deployment/cors-config-dev.json', 'r') as f:
        cors_config = json.load(f)

    try:
        # Apply CORS configuration
        s3_client.put_bucket_cors(
            Bucket=bucket_name,
            CORSConfiguration=cors_config
        )

        print("✅ CORS configuration updated successfully!")
        print("\nUpdated rules:")
        print("  - Combined rule: GET/HEAD/PUT/POST with all headers allowed")
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
    print("Fixing CORS Configuration for Production Bucket")
    print("=" * 70)
    print()

    if fix_cors_for_prod_bucket():
        print("\n[SUCCESS] Production bucket CORS configuration fixed!")
        print("\nYou should now be able to upload PDFs from eliyahu.ai/chex")
    else:
        print("\n[FAILED] Could not update CORS configuration")
        print("Make sure AWS credentials are configured correctly")
