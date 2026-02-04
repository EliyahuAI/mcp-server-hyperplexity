#!/bin/bash
# Fix CORS configuration for hyperplexity-storage-dev bucket

echo "======================================================================"
echo "Fixing CORS Configuration for hyperplexity-storage-dev"
echo "======================================================================"
echo ""

# Apply CORS configuration
aws s3api put-bucket-cors \
  --bucket hyperplexity-storage-dev \
  --cors-configuration file://deployment/cors-config-dev.json \
  --region us-east-1

if [ $? -eq 0 ]; then
  echo ""
  echo "✅ CORS configuration updated successfully!"
  echo ""
  echo "The bucket now allows:"
  echo "  - PDF uploads from localhost:8000 via presigned URLs"
  echo "  - All required headers (including x-amz-meta-* for metadata)"
  echo ""
  echo "Try uploading a PDF again - it should work now!"
else
  echo ""
  echo "❌ Failed to update CORS configuration"
  echo "Make sure AWS credentials are configured and you have S3 permissions"
fi
