@echo off
echo Deploying Lambda Function with Dependencies Layer...
python create_package.py --deploy --region us-east-1 --s3-bucket perplexity-cache --verify --use-layer
pause 