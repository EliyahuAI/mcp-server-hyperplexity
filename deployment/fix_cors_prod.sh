#!/bin/bash
# Fix CORS configuration for hyperplexity-storage (PRODUCTION) bucket

echo "======================================================================"
echo "Fixing CORS Configuration for hyperplexity-storage (PRODUCTION)"
echo "======================================================================"
echo ""

# Apply CORS configuration (same config works for both dev and prod)
aws s3api put-bucket-cors \
  --bucket hyperplexity-storage \
  --cors-configuration file://deployment/cors-config-dev.json \
  --region us-east-1

if [ $? -eq 0 ]; then
  echo ""
  echo "✅ CORS configuration updated successfully!"
  echo ""
  echo "The production bucket now allows:"
  echo "  - PDF uploads from eliyahu.ai via presigned URLs"
  echo "  - All required headers (including x-amz-meta-* for metadata)"
  echo ""
  echo "Try uploading a PDF from eliyahu.ai/chex - it should work now!"
else
  echo ""
  echo "❌ Failed to update CORS configuration"
  echo "Make sure AWS credentials are configured and you have S3 permissions"
fi
