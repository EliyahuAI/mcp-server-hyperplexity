#!/bin/bash
# Fix CORS configuration for both dev and production buckets

echo "======================================================================"
echo "Fixing CORS Configuration for ALL Buckets"
echo "======================================================================"
echo ""

CORS_CONFIG="deployment/cors-config-dev.json"
REGION="us-east-1"

# Fix production bucket
echo "Updating PRODUCTION bucket (hyperplexity-storage)..."
aws s3api put-bucket-cors \
  --bucket hyperplexity-storage \
  --cors-configuration file://$CORS_CONFIG \
  --region $REGION

if [ $? -eq 0 ]; then
  echo "✅ Production bucket updated successfully!"
else
  echo "❌ Failed to update production bucket"
fi

echo ""

# Fix dev bucket
echo "Updating DEV bucket (hyperplexity-storage-dev)..."
aws s3api put-bucket-cors \
  --bucket hyperplexity-storage-dev \
  --cors-configuration file://$CORS_CONFIG \
  --region $REGION

if [ $? -eq 0 ]; then
  echo "✅ Dev bucket updated successfully!"
else
  echo "❌ Failed to update dev bucket"
fi

echo ""
echo "======================================================================"
echo "Done! Both buckets now allow PDF uploads from:"
echo "  - https://eliyahu.ai (production)"
echo "  - https://hyperplexity.ai (production)"
echo "  - http://localhost:8000 (development)"
echo "======================================================================"
