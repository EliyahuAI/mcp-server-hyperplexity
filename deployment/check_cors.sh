#!/bin/bash
# Check current CORS configuration for both buckets

echo "======================================================================"
echo "Checking CORS Configuration"
echo "======================================================================"
echo ""

echo "PRODUCTION bucket (hyperplexity-storage):"
echo "-------------------------------------------"
aws s3api get-bucket-cors --bucket hyperplexity-storage --region us-east-1 2>&1
echo ""
echo ""

echo "DEV bucket (hyperplexity-storage-dev):"
echo "-------------------------------------------"
aws s3api get-bucket-cors --bucket hyperplexity-storage-dev --region us-east-1 2>&1
echo ""
