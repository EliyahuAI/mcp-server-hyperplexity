"""
Simple Squarespace order polling for credit purchases.
Polls Squarespace Commerce API for new orders and adds credits.
"""

import json
import logging
import requests
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

SQUARESPACE_API_KEY = None  # Set via environment variable or SSM
SQUARESPACE_API_URL = "https://api.squarespace.com/1.0/commerce/orders"
_cached_api_key = None

def get_squarespace_api_key():
    """Get Squarespace API key from SSM Parameter Store."""
    global _cached_api_key
    
    if _cached_api_key:
        return _cached_api_key
    
    try:
        import boto3
        import os
        
        # Try environment variable first
        api_key = os.environ.get('SQUARESPACE_API_KEY')
        if api_key:
            _cached_api_key = api_key
            return api_key
        
        # Get from SSM Parameter Store
        ssm_client = boto3.client('ssm')
        response = ssm_client.get_parameter(
            Name='Hyperplexity_API_Key',
            WithDecryption=True
        )
        
        _cached_api_key = response['Parameter']['Value']
        logger.info("Successfully retrieved Squarespace API key from SSM")
        return _cached_api_key
        
    except Exception as e:
        logger.error(f"Failed to get Squarespace API key: {e}")
        return None

def poll_squarespace_orders(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Poll Squarespace for recent orders and process credit purchases."""
    try:
        # Get API key from SSM
        api_key = get_squarespace_api_key()
        if not api_key:
            logger.error("SQUARESPACE_API_KEY not available")
            return create_response(500, {'error': 'API key not configured'})
        
        # Get orders from last hour (or since last check)
        now = datetime.now(timezone.utc)
        since_time = (now - timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
        until_time = now.isoformat().replace('+00:00', 'Z')
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'User-Agent': 'Hyperplexity/1.0',
            'Content-Type': 'application/json'
        }
        
        # Get recent orders (both FULFILLED and PENDING - PENDING means payment completed)
        params = {
            'modifiedAfter': since_time,
            'modifiedBefore': until_time
            # Don't filter by fulfillmentStatus - we'll check it in code
        }
        
        response = requests.get(SQUARESPACE_API_URL, headers=headers, params=params)
        
        if response.status_code != 200:
            logger.error(f"Squarespace API error: {response.status_code} - {response.text}")
            return create_response(500, {'error': 'Failed to fetch orders'})
        
        orders = response.json().get('result', [])
        processed_count = 0
        
        for order in orders:
            # Only process orders that have been paid (PENDING or FULFILLED)
            status = order.get('fulfillmentStatus', '').upper()
            if status not in ['FULFILLED', 'PENDING']:
                continue
                
            if is_credit_purchase(order):
                result = process_credit_order(order)
                if result['success']:
                    processed_count += 1
        
        logger.info(f"Processed {processed_count} credit orders out of {len(orders)} total orders")
        
        return create_response(200, {
            'message': f'Processed {processed_count} credit orders',
            'total_orders_checked': len(orders)
        })
        
    except Exception as e:
        logger.error(f"Error polling Squarespace orders: {str(e)}")
        return create_response(500, {'error': str(e)})

def is_credit_purchase(order: Dict[str, Any]) -> bool:
    """Check if order is for credits based on product name or SKU."""
    try:
        # Check line items for credit products
        line_items = order.get('lineItems', [])
        
        for item in line_items:
            product_name = item.get('productName', '').lower()
            sku = item.get('sku', '').lower()
            
            # Check if this is a credit product
            if any(keyword in product_name for keyword in ['credit', 'hyperplexity', 'validation']):
                return True
            if any(keyword in sku for keyword in ['credit', 'hpx', 'validation']):
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking if credit purchase: {e}")
        return False

def process_credit_order(order: Dict[str, Any]) -> Dict[str, Any]:
    """Process a credit order and add balance to user account."""
    try:
        # Extract order details
        order_id = order.get('id')
        
        # Try to find a verified user email using the new mapping logic
        email_mapping_result = find_verified_user_email(order)
        
        if not email_mapping_result['found']:
            logger.warning(f"No verified user found for order {order_id}: {email_mapping_result['reason']}")
            
            # Leave as pending and handle refund/notification
            mark_order_pending(order_id, order, email_mapping_result['reason'])
            return {
                'success': False, 
                'error': 'No verified user found', 
                'reason': email_mapping_result['reason'],
                'status': 'pending_verification'
            }
        
        customer_email = email_mapping_result['email']
        
        # Check if already processed
        if is_order_already_processed(order_id):
            logger.info(f"Order {order_id} already processed")
            return {'success': True, 'message': 'Already processed'}
        
        # Calculate credit amount from order total
        grand_total = order.get('grandTotal', {})
        
        # Squarespace API returns either 'cents' (integer) or 'value' (string)
        if 'cents' in grand_total:
            amount_cents = grand_total.get('cents', 0)
            amount = Decimal(str(amount_cents)) / 100  # Convert cents to dollars
        elif 'value' in grand_total:
            amount_value = grand_total.get('value', '0')
            amount = Decimal(str(amount_value))  # Already in dollars
        else:
            logger.warning(f"Unknown grandTotal format for order {order_id}: {grand_total}")
            amount = Decimal('0')
        
        logger.info(f"Order {order_id} amount calculation: grandTotal={grand_total}, final_amount=${amount}")
        
        # Import account functions
        try:
            from dynamodb_schemas import add_to_balance, check_user_balance
        except ImportError:
            logger.error("Failed to import account management functions")
            return {'success': False, 'error': 'System error'}
        
        # Add credits to balance
        success = add_to_balance(
            email=customer_email,
            amount=amount,
            transaction_type='store_purchase',
            description=f'Credits purchased via Squarespace (verified: {email_mapping_result["matched_field"]})',
            payment_id=order_id
        )
        
        if success:
            # Mark order as processed
            mark_order_processed(order_id, order)
            
            # Get new balance
            new_balance = check_user_balance(customer_email)
            
            # Send confirmation email
            try:
                from email_sender import send_credit_confirmation_email
                send_credit_confirmation_email(
                    email_address=customer_email,
                    amount_purchased=float(amount),
                    new_balance=float(new_balance) if new_balance else 0,
                    transaction_id=order_id
                )
            except Exception as e:
                logger.warning(f"Failed to send confirmation email: {e}")
            
            logger.info(f"Successfully added ${amount} credits to {customer_email}")
            return {
                'success': True,
                'amount_added': float(amount),
                'new_balance': float(new_balance) if new_balance else 0
            }
        else:
            return {'success': False, 'error': 'Failed to add balance'}
            
    except Exception as e:
        logger.error(f"Error processing credit order: {str(e)}")
        return {'success': False, 'error': str(e)}

def is_order_already_processed(order_id: str) -> bool:
    """Check if order was already processed."""
    try:
        import boto3
        
        s3_client = boto3.client('s3')
        bucket_name = 'hyperplexity-storage'
        key = f"payments/processed/squarespace_{order_id}.json"
        
        try:
            s3_client.head_object(Bucket=bucket_name, Key=key)
            return True
        except s3_client.exceptions.NoSuchKey:
            return False
            
    except Exception as e:
        logger.error(f"Error checking order status: {e}")
        return False

def mark_order_processed(order_id: str, order_data: Dict[str, Any]):
    """Mark order as processed and optionally fulfill in Squarespace."""
    try:
        import boto3
        
        s3_client = boto3.client('s3')
        bucket_name = 'hyperplexity-storage'
        key = f"payments/processed/squarespace_{order_id}.json"
        
        processed_data = {
            'order_id': order_id,
            'processed_at': datetime.now().isoformat(),
            'order_data': order_data
        }
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json.dumps(processed_data, indent=2),
            ContentType='application/json'
        )
        
        # Optional: Mark order as fulfilled in Squarespace
        try:
            fulfill_order_in_squarespace(order_id)
        except Exception as e:
            logger.warning(f"Could not fulfill order {order_id} in Squarespace: {e}")
        
    except Exception as e:
        logger.error(f"Failed to mark order as processed: {e}")

def find_verified_user_email(order: Dict[str, Any]) -> Dict[str, Any]:
    """
    Find and verify user email using the following priority:
    1. Verified Email field (if exists)
    2. Alternative Email field (if exists) 
    3. Customer Email field
    
    Returns dict with 'found', 'email', 'matched_field', and 'reason' keys.
    """
    try:
        order_id = order.get('id')
        
        # Try to extract emails in priority order
        email_candidates = []
        
        # 1. Check for Verified Email field (custom form submission or direct field)
        verified_email = extract_verified_email_from_order(order)
        if verified_email:
            email_candidates.append(('verified_email', verified_email))
        
        # 2. Check for Alternative Email field
        alternative_email = extract_alternative_email_from_order(order)
        if alternative_email:
            email_candidates.append(('alternative_email', alternative_email))
        
        # 3. Check standard Customer Email
        customer_email = order.get('customerEmail', '').lower().strip()
        if customer_email:
            email_candidates.append(('customer_email', customer_email))
        
        if not email_candidates:
            return {
                'found': False,
                'email': None,
                'matched_field': None,
                'reason': 'No email addresses found in order'
            }
        
        # Check each email candidate against verified users in DynamoDB
        for field_name, email in email_candidates:
            if is_user_verified(email):
                logger.info(f"Order {order_id}: Found verified user {email} via {field_name}")
                return {
                    'found': True,
                    'email': email,
                    'matched_field': field_name,
                    'reason': f'Verified user found via {field_name}'
                }
        
        # No verified users found
        attempted_emails = [email for _, email in email_candidates]
        return {
            'found': False,
            'email': None,
            'matched_field': None,
            'reason': f'None of the emails are verified users: {attempted_emails}'
        }
        
    except Exception as e:
        logger.error(f"Error finding verified user email: {e}")
        return {
            'found': False,
            'email': None,
            'matched_field': None,
            'reason': f'Error during email verification: {str(e)}'
        }

def extract_verified_email_from_order(order: Dict[str, Any]) -> Optional[str]:
    """Extract Verified Email field from Squarespace order."""
    try:
        # Check direct field first
        verified_email = order.get('verifiedEmail') or order.get('verified_email')
        if verified_email:
            return verified_email.lower().strip()
        
        # Check line item customizations (this is where Squarespace stores custom product fields)
        line_items = order.get('lineItems', [])
        if line_items:  # Make sure line_items is not None
            for item in line_items or []:
                customizations = item.get('customizations', [])
                if customizations:  # Make sure customizations is not None
                    for customization in customizations or []:
                        label = customization.get('label', '').lower()
                        if 'verified' in label and 'email' in label:
                            value = customization.get('value', '').strip()
                            if value:
                                logger.info(f"Found verified email in customizations: {value}")
                                return value.lower()
        
        # Check custom form submissions
        form_submissions = order.get('formSubmission', [])
        for field in form_submissions:
            label = field.get('label', '').lower()
            if 'verified' in label and 'email' in label:
                value = field.get('value', '').strip()
                if value:
                    logger.info(f"Found verified email in form submission: {value}")
                    return value.lower()
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting verified email: {e}")
        return None

def extract_alternative_email_from_order(order: Dict[str, Any]) -> Optional[str]:
    """Extract Alternative Email field from Squarespace order."""
    try:
        # Check direct field first
        alt_email = order.get('alternativeEmail') or order.get('alternative_email')
        if alt_email:
            return alt_email.lower().strip()
        
        # Check line item customizations for alternative email fields
        line_items = order.get('lineItems', [])
        if line_items:  # Make sure line_items is not None
            for item in line_items or []:
                customizations = item.get('customizations', [])
                if customizations:  # Make sure customizations is not None
                    for customization in customizations or []:
                        label = customization.get('label', '').lower()
                        # Check for Hyperplexity Email first (highest priority)
                        if 'hyperplexity' in label and 'email' in label:
                            value = customization.get('value', '').strip()
                            if value:
                                logger.info(f"Found Hyperplexity email in customizations: {value}")
                                return value.lower()
                        # Check for other alternative email patterns
                        if any(keyword in label for keyword in ['alternative', 'alternate', 'backup', 'secondary']):
                            if 'email' in label:
                                value = customization.get('value', '').strip()
                                if value:
                                    logger.info(f"Found alternative email in customizations: {value}")
                                    return value.lower()
        
        # Check billing address email as fallback
        billing_email = order.get('billingAddress', {}).get('email')
        if billing_email:
            return billing_email.lower().strip()
        
        # Check form submissions for "Email to fund" or similar fields
        form_submissions = order.get('formSubmission', [])
        for field in form_submissions:
            label = field.get('label', '').lower()
            value = field.get('value', '').strip()

            # Check for Hyperplexity Email first (highest priority)
            if 'hyperplexity' in label and 'email' in label:
                if value:
                    logger.info(f"Found Hyperplexity email in form submission: {value}")
                    return value.lower()

            # Check for specific labels that indicate funding email
            if 'email to fund' in label or 'fund' in label and 'email' in label:
                if value:
                    logger.info(f"Found funding email in form submission: {value}")
                    return value.lower()

            # Check for general alternative email patterns
            if any(keyword in label for keyword in ['alternative', 'alternate', 'backup', 'secondary']):
                if 'email' in label and value:
                    logger.info(f"Found alternative email in form submission: {value}")
                    return value.lower()
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting alternative email: {e}")
        return None

def is_user_verified(email: str) -> bool:
    """Check if user email is verified in DynamoDB user validation table."""
    try:
        import boto3
        from dynamodb_schemas import DynamoDBSchemas
        
        email = email.lower().strip()
        
        # Check the user-validation table for validated status
        validation_table = boto3.resource('dynamodb', region_name='us-east-1').Table(
            DynamoDBSchemas.USER_VALIDATION_TABLE
        )
        
        response = validation_table.get_item(Key={'email': email})
        
        if 'Item' in response:
            validation_record = response['Item']
            is_validated = validation_record.get('validated', False)
            
            logger.info(f"User {email} validation status: validated={is_validated}")
            return is_validated
        
        logger.info(f"User {email} not found in user validation table")
        return False
        
    except Exception as e:
        logger.error(f"Error checking user verification status for {email}: {e}")
        return False

def mark_order_pending(order_id: str, order_data: Dict[str, Any], reason: str):
    """Mark order as pending for manual review and potential refund."""
    try:
        import boto3
        
        s3_client = boto3.client('s3')
        bucket_name = 'hyperplexity-storage'
        key = f"payments/pending/squarespace_{order_id}.json"
        
        pending_data = {
            'order_id': order_id,
            'status': 'pending_verification',
            'reason': reason,
            'marked_pending_at': datetime.now().isoformat(),
            'order_data': order_data,
            'requires_manual_review': True,
            'refund_eligible': True
        }
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json.dumps(pending_data, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"Marked order {order_id} as pending: {reason}")
        
        # Send notification about pending order
        try:
            send_pending_order_notification(order_id, order_data, reason)
        except Exception as e:
            logger.warning(f"Failed to send pending order notification: {e}")
        
    except Exception as e:
        logger.error(f"Failed to mark order as pending: {e}")

def send_pending_order_notification(order_id: str, order_data: Dict[str, Any], reason: str):
    """Send notification about orders that couldn't be fulfilled due to email verification issues."""
    try:
        from email_sender import send_email
        
        # Extract order details
        customer_email = order_data.get('customerEmail', 'N/A')
        grand_total = order_data.get('grandTotal', {})
        amount = 'N/A'
        
        if 'cents' in grand_total:
            amount = f"${grand_total.get('cents', 0) / 100:.2f}"
        elif 'value' in grand_total:
            amount = f"${grand_total.get('value', '0')}"
        
        subject = f"Squarespace Order Pending Verification - {order_id}"
        
        body = f"""
Squarespace Order Requires Manual Review

Order ID: {order_id}
Customer Email: {customer_email}
Amount: {amount}
Reason: {reason}

Order has been marked as pending and may require a refund if customer cannot be verified.

Next Steps:
1. Manually verify customer identity
2. If verified, process payment manually
3. If not verified, issue refund through Squarespace

Order details stored at: payments/pending/squarespace_{order_id}.json
        """.strip()
        
        # Send to admin email (configure as needed)
        admin_email = "admin@hyperplexity.com"  # Update with actual admin email
        
        send_email(
            to_email=admin_email,
            subject=subject,
            body=body,
            from_email="noreply@hyperplexity.com"
        )
        
        logger.info(f"Sent pending order notification for {order_id}")
        
    except Exception as e:
        logger.error(f"Error sending pending order notification: {e}")

def fulfill_order_in_squarespace(order_id: str) -> bool:
    """Mark an order as fulfilled in Squarespace."""
    try:
        api_key = get_squarespace_api_key()
        if not api_key:
            return False
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'User-Agent': 'Hyperplexity/1.0',
            'Content-Type': 'application/json'
        }
        
        # Fulfill the order
        fulfill_url = f"{SQUARESPACE_API_URL}/{order_id}/fulfillments"
        fulfill_data = {
            "shouldSendNotification": False  # Don't send fulfillment email
        }
        
        response = requests.post(fulfill_url, headers=headers, json=fulfill_data, timeout=10)
        
        if response.status_code in [200, 201]:
            logger.info(f"Successfully fulfilled order {order_id}")
            return True
        else:
            logger.warning(f"Failed to fulfill order {order_id}: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error fulfilling order {order_id}: {e}")
        return False

def get_pending_orders() -> List[Dict[str, Any]]:
    """Get all pending orders that need manual review."""
    try:
        import boto3
        
        s3_client = boto3.client('s3')
        bucket_name = 'hyperplexity-storage'
        prefix = 'payments/pending/'
        
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix
        )
        
        pending_orders = []
        
        if 'Contents' in response:
            for obj in response['Contents']:
                key = obj['Key']
                if key.endswith('.json'):
                    # Get the object content
                    obj_response = s3_client.get_object(Bucket=bucket_name, Key=key)
                    order_data = json.loads(obj_response['Body'].read().decode('utf-8'))
                    pending_orders.append(order_data)
        
        logger.info(f"Found {len(pending_orders)} pending orders")
        return pending_orders
        
    except Exception as e:
        logger.error(f"Error retrieving pending orders: {e}")
        return []

def manually_process_order(order_id: str, verified_email: str) -> Dict[str, Any]:
    """Manually process a pending order with a verified email address."""
    try:
        import boto3
        
        s3_client = boto3.client('s3')
        bucket_name = 'hyperplexity-storage'
        
        # Get the pending order data
        pending_key = f"payments/pending/squarespace_{order_id}.json"
        
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=pending_key)
            pending_data = json.loads(response['Body'].read().decode('utf-8'))
        except s3_client.exceptions.NoSuchKey:
            return {'success': False, 'error': 'Pending order not found'}
        
        order_data = pending_data.get('order_data', {})
        
        # Check if the verified email is actually verified
        if not is_user_verified(verified_email):
            return {'success': False, 'error': 'Provided email is not verified'}
        
        # Process the order with the verified email
        result = process_order_with_email(order_data, verified_email)
        
        if result['success']:
            # Remove from pending and mark as processed
            s3_client.delete_object(Bucket=bucket_name, Key=pending_key)
            
            # Mark as processed
            mark_order_processed(order_id, order_data)
            
            logger.info(f"Successfully manually processed order {order_id} for {verified_email}")
            return {
                'success': True,
                'message': f'Order processed for {verified_email}',
                'amount_added': result.get('amount_added'),
                'new_balance': result.get('new_balance')
            }
        else:
            return result
            
    except Exception as e:
        logger.error(f"Error manually processing order {order_id}: {e}")
        return {'success': False, 'error': str(e)}

def process_order_with_email(order_data: Dict[str, Any], email: str) -> Dict[str, Any]:
    """Process an order with a specific verified email address."""
    try:
        order_id = order_data.get('id')
        
        # Calculate credit amount from order total
        grand_total = order_data.get('grandTotal', {})
        
        # Squarespace API returns either 'cents' (integer) or 'value' (string)
        if 'cents' in grand_total:
            amount_cents = grand_total.get('cents', 0)
            amount = Decimal(str(amount_cents)) / 100  # Convert cents to dollars
        elif 'value' in grand_total:
            amount_value = grand_total.get('value', '0')
            amount = Decimal(str(amount_value))  # Already in dollars
        else:
            logger.warning(f"Unknown grandTotal format for order {order_id}: {grand_total}")
            amount = Decimal('0')
        
        # Import account functions
        try:
            from dynamodb_schemas import add_to_balance, check_user_balance
        except ImportError:
            logger.error("Failed to import account management functions")
            return {'success': False, 'error': 'System error'}
        
        # Add credits to balance
        success = add_to_balance(
            email=email,
            amount=amount,
            transaction_type='store_purchase_manual',
            description=f'Credits purchased via Squarespace (manually processed)',
            payment_id=order_id
        )
        
        if success:
            # Get new balance
            new_balance = check_user_balance(email)
            
            # Send confirmation email
            try:
                from email_sender import send_credit_confirmation_email
                send_credit_confirmation_email(
                    email_address=email,
                    amount_purchased=float(amount),
                    new_balance=float(new_balance) if new_balance else 0,
                    transaction_id=order_id
                )
            except Exception as e:
                logger.warning(f"Failed to send confirmation email: {e}")
            
            logger.info(f"Successfully added ${amount} credits to {email} (manual processing)")
            return {
                'success': True,
                'amount_added': float(amount),
                'new_balance': float(new_balance) if new_balance else 0
            }
        else:
            return {'success': False, 'error': 'Failed to add balance'}
            
    except Exception as e:
        logger.error(f"Error processing order with email: {str(e)}")
        return {'success': False, 'error': str(e)}

def initiate_refund_process(order_id: str, reason: str = "Unable to verify customer") -> Dict[str, Any]:
    """Mark an order for refund processing."""
    try:
        import boto3
        
        s3_client = boto3.client('s3')
        bucket_name = 'hyperplexity-storage'
        
        # Move from pending to refund queue
        pending_key = f"payments/pending/squarespace_{order_id}.json"
        refund_key = f"payments/refunds/squarespace_{order_id}.json"
        
        try:
            # Get pending order data
            response = s3_client.get_object(Bucket=bucket_name, Key=pending_key)
            pending_data = json.loads(response['Body'].read().decode('utf-8'))
            
            # Create refund record
            refund_data = {
                **pending_data,
                'refund_status': 'pending_refund',
                'refund_reason': reason,
                'refund_initiated_at': datetime.now().isoformat(),
                'requires_manual_refund': True
            }
            
            # Save to refund queue
            s3_client.put_object(
                Bucket=bucket_name,
                Key=refund_key,
                Body=json.dumps(refund_data, indent=2),
                ContentType='application/json'
            )
            
            # Remove from pending
            s3_client.delete_object(Bucket=bucket_name, Key=pending_key)
            
            # Send refund notification
            send_refund_notification(order_id, refund_data, reason)
            
            logger.info(f"Initiated refund process for order {order_id}")
            return {'success': True, 'message': 'Refund process initiated'}
            
        except s3_client.exceptions.NoSuchKey:
            return {'success': False, 'error': 'Pending order not found'}
            
    except Exception as e:
        logger.error(f"Error initiating refund for order {order_id}: {e}")
        return {'success': False, 'error': str(e)}

def send_refund_notification(order_id: str, order_data: Dict[str, Any], reason: str):
    """Send notification about orders that need to be refunded."""
    try:
        from email_sender import send_email
        
        # Extract order details
        customer_email = order_data.get('order_data', {}).get('customerEmail', 'N/A')
        grand_total = order_data.get('order_data', {}).get('grandTotal', {})
        amount = 'N/A'
        
        if 'cents' in grand_total:
            amount = f"${grand_total.get('cents', 0) / 100:.2f}"
        elif 'value' in grand_total:
            amount = f"${grand_total.get('value', '0')}"
        
        subject = f"REFUND REQUIRED - Squarespace Order {order_id}"
        
        body = f"""
REFUND REQUIRED - Squarespace Order

Order ID: {order_id}
Customer Email: {customer_email}
Amount: {amount}
Reason: {reason}

ACTION REQUIRED:
Process refund through Squarespace Commerce dashboard or API.

Steps:
1. Login to Squarespace Commerce dashboard
2. Find order {order_id}
3. Process full refund
4. Update refund status in system

Order details stored at: payments/refunds/squarespace_{order_id}.json
        """.strip()
        
        # Send to admin email (configure as needed)
        admin_email = "admin@hyperplexity.com"  # Update with actual admin email
        
        send_email(
            to_email=admin_email,
            subject=subject,
            body=body,
            from_email="noreply@hyperplexity.com"
        )
        
        logger.info(f"Sent refund notification for order {order_id}")
        
    except Exception as e:
        logger.error(f"Error sending refund notification: {e}")

def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create HTTP response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body)
    }

# Manual trigger endpoint
def check_orders_now(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Manual endpoint to check orders immediately."""
    return poll_squarespace_orders(event, context)

# Pending order management endpoints
def list_pending_orders(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """List all orders pending verification."""
    try:
        pending_orders = get_pending_orders()
        
        # Simplify order data for response
        simplified_orders = []
        for order in pending_orders:
            order_data = order.get('order_data', {})
            simplified_orders.append({
                'order_id': order.get('order_id'),
                'customer_email': order_data.get('customerEmail'),
                'amount': order_data.get('grandTotal', {}),
                'reason': order.get('reason'),
                'marked_pending_at': order.get('marked_pending_at'),
                'refund_eligible': order.get('refund_eligible', True)
            })
        
        return create_response(200, {
            'pending_orders': simplified_orders,
            'total_count': len(simplified_orders)
        })
        
    except Exception as e:
        logger.error(f"Error listing pending orders: {e}")
        return create_response(500, {'error': str(e)})

def process_pending_order(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Manually process a pending order with verified email."""
    try:
        body = json.loads(event.get('body', '{}'))
        order_id = body.get('order_id')
        verified_email = body.get('verified_email')
        
        if not order_id or not verified_email:
            return create_response(400, {
                'error': 'Missing required fields: order_id and verified_email'
            })
        
        result = manually_process_order(order_id, verified_email)
        
        status_code = 200 if result['success'] else 400
        return create_response(status_code, result)
        
    except Exception as e:
        logger.error(f"Error processing pending order: {e}")
        return create_response(500, {'error': str(e)})

def refund_pending_order(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Mark a pending order for refund."""
    try:
        body = json.loads(event.get('body', '{}'))
        order_id = body.get('order_id')
        reason = body.get('reason', 'Unable to verify customer')
        
        if not order_id:
            return create_response(400, {'error': 'Missing required field: order_id'})
        
        result = initiate_refund_process(order_id, reason)
        
        status_code = 200 if result['success'] else 400
        return create_response(status_code, result)
        
    except Exception as e:
        logger.error(f"Error initiating refund: {e}")
        return create_response(500, {'error': str(e)})