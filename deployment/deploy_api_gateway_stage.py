#!/usr/bin/env python3
"""
Deploy API Gateway Stage
Forces API Gateway to pick up Lambda changes
"""
import boto3
import sys
from datetime import datetime

# Configuration
API_ID = 'wqamcddvub'  # Table maker/dev API
STAGE_NAME = 'dev'
REGION = 'us-east-1'

def deploy_stage():
    """Deploy API Gateway stage to pick up Lambda changes."""
    try:
        client = boto3.client('apigateway', region_name=REGION)

        print(f"Deploying API Gateway stage...")
        print(f"  API ID: {API_ID}")
        print(f"  Stage: {STAGE_NAME}")
        print(f"  Region: {REGION}")

        response = client.create_deployment(
            restApiId=API_ID,
            stageName=STAGE_NAME,
            description=f'Deploy CORS fix - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        )

        deployment_id = response['id']
        print(f"\n✅ Deployment successful!")
        print(f"   Deployment ID: {deployment_id}")
        print(f"   API URL: https://{API_ID}.execute-api.{REGION}.amazonaws.com/{STAGE_NAME}")

        # Test CORS
        print(f"\nTesting CORS headers...")
        import requests

        response = requests.options(
            f'https://{API_ID}.execute-api.{REGION}.amazonaws.com/{STAGE_NAME}/validate',
            headers={
                'Origin': 'http://localhost:8000',
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'X-Session-Token'
            }
        )

        cors_header = response.headers.get('Access-Control-Allow-Headers', '')
        print(f"   CORS Headers: {cors_header}")

        if 'X-Session-Token' in cors_header:
            print(f"   ✅ X-Session-Token is in allowed headers!")
        else:
            print(f"   ❌ X-Session-Token NOT in allowed headers")
            print(f"   ⚠️  Lambda may not have been updated yet")

        return True

    except Exception as e:
        print(f"\n❌ Deployment failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = deploy_stage()
    sys.exit(0 if success else 1)
