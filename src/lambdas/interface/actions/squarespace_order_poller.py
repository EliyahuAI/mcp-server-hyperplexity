"""
Simple Squarespace order polling for credit purchases.
Polls Squarespace Commerce API for new orders and adds credits.
"""

import json
import logging
import requests
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List

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
        since_time = (datetime.utcnow() - timedelta(hours=1)).isoformat() + 'Z'
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'User-Agent': 'Hyperplexity/1.0',
            'Content-Type': 'application/json'
        }
        
        # Get recent orders
        params = {
            'modifiedAfter': since_time,
            'fulfillmentStatus': 'FULFILLED'  # Only completed orders
        }
        
        response = requests.get(SQUARESPACE_API_URL, headers=headers, params=params)
        
        if response.status_code != 200:
            logger.error(f"Squarespace API error: {response.status_code} - {response.text}")
            return create_response(500, {'error': 'Failed to fetch orders'})
        
        orders = response.json().get('result', [])
        processed_count = 0
        
        for order in orders:
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
        customer_email = order.get('customerEmail', '').lower().strip()
        
        if not customer_email:
            logger.warning(f"No customer email for order {order_id}")
            return {'success': False, 'error': 'No customer email'}
        
        # Check if already processed
        if is_order_already_processed(order_id):
            logger.info(f"Order {order_id} already processed")
            return {'success': True, 'message': 'Already processed'}
        
        # Calculate credit amount from order total
        grand_total = order.get('grandTotal', {})
        amount_cents = grand_total.get('cents', 0)
        amount = Decimal(str(amount_cents)) / 100  # Convert cents to dollars
        
        # Import account functions
        try:
            from shared.dynamodb_schemas import add_to_balance, check_user_balance
        except ImportError:
            logger.error("Failed to import account management functions")
            return {'success': False, 'error': 'System error'}
        
        # Add credits to balance
        success = add_to_balance(
            email=customer_email,
            amount=amount,
            transaction_type='store_purchase',
            description=f'Credits purchased via Squarespace',
            payment_id=order_id
        )
        
        if success:
            # Mark order as processed
            mark_order_processed(order_id, order)
            
            # Get new balance
            new_balance = check_user_balance(customer_email)
            
            # Send confirmation email
            try:
                from shared.email_sender import send_credit_confirmation_email
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
    """Mark order as processed."""
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
        
    except Exception as e:
        logger.error(f"Failed to mark order as processed: {e}")

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