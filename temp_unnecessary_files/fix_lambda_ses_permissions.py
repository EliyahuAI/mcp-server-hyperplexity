import boto3
import json

# Initialize IAM client
iam_client = boto3.client('iam', region_name='us-east-1')

# Lambda execution role name
ROLE_NAME = 'chatGPT-role-j84fj9y7'

def add_ses_permissions():
    """Add SES permissions to the Lambda execution role"""
    
    print(f"Adding SES permissions to role: {ROLE_NAME}")
    print("="*60)
    
    # Define the SES policy
    ses_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ses:SendRawEmail",
                    "ses:SendEmail"
                ],
                "Resource": [
                    "arn:aws:ses:us-east-1:400232868802:identity/eliyahu@eliyahu.ai",
                    "arn:aws:ses:us-east-1:400232868802:identity/*"  # Or restrict to specific emails
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ses:GetSendQuota",
                    "ses:GetSendStatistics"
                ],
                "Resource": "*"
            }
        ]
    }
    
    policy_name = 'PerplexityValidatorSESPolicy'
    
    try:
        # First, check if the role exists
        print(f"\n1. Checking if role exists...")
        try:
            role = iam_client.get_role(RoleName=ROLE_NAME)
            print(f"   ✓ Role found: {role['Role']['Arn']}")
        except iam_client.exceptions.NoSuchEntityException:
            print(f"   ✗ Role {ROLE_NAME} not found!")
            return False
        
        # Check existing policies
        print(f"\n2. Checking existing inline policies...")
        existing_policies = iam_client.list_role_policies(RoleName=ROLE_NAME)
        print(f"   Existing inline policies: {existing_policies['PolicyNames']}")
        
        # Add or update the SES policy
        print(f"\n3. Adding/updating SES policy...")
        iam_client.put_role_policy(
            RoleName=ROLE_NAME,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(ses_policy)
        )
        print(f"   ✓ Policy '{policy_name}' added successfully!")
        
        # Verify the policy was added
        print(f"\n4. Verifying policy...")
        policy_doc = iam_client.get_role_policy(
            RoleName=ROLE_NAME,
            PolicyName=policy_name
        )
        print(f"   ✓ Policy verified and active")
        
        print(f"\n✅ SUCCESS! SES permissions added to role {ROLE_NAME}")
        print("\nThe Lambda function now has permission to:")
        print("  - Send emails via SES")
        print("  - Use the verified email address: eliyahu@eliyahu.ai")
        print("\nYou can now test the email functionality again!")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error adding permissions: {e}")
        
        # Check if it's a permissions issue
        if 'AccessDenied' in str(e):
            print("\n⚠️  You don't have permission to modify IAM roles.")
            print("You need to:")
            print("1. Use AWS Console to add SES permissions to the role")
            print("2. Or run this script with IAM admin credentials")
            
            # Print the policy for manual addition
            print("\n📋 Policy to add manually:")
            print(json.dumps(ses_policy, indent=2))
            
        return False

if __name__ == "__main__":
    print("Lambda SES Permissions Fixer")
    print("This will add SES email sending permissions to the Lambda execution role")
    
    add_ses_permissions() 