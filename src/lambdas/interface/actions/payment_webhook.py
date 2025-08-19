"""
Payment webhook handler for SquareSpace store integration.
Processes completed payments from SquareSpace and adds credits to user accounts.
"""

import json
import logging
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

def handle_payment_webhook(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle payment completion webhooks from SquareSpace."""
    try:
        # Parse the webhook payload
        if 'body' in event:
            if isinstance(event['body'], str):
                payload = json.loads(event['body'])
            else:
                payload = event['body']
        else:
            payload = event
        
        logger.info(f"Received payment webhook: {json.dumps(payload, indent=2)}")
        
        # Extract payment information from SquareSpace webhook
        # Note: Adjust these field names based on actual SquareSpace webhook format
        payment_data = extract_squarespace_payment_data(payload)
        
        if not payment_data:
            logger.error("Failed to extract payment data from webhook")
            return create_response(400, {'error': 'Invalid webhook payload'})
        
        # Process the payment and add credits
        result = process_payment_completion(payment_data)
        
        if result['success']:
            logger.info(f"Successfully processed payment: {payment_data.get('transaction_id')}")
            return create_response(200, {'message': 'Payment processed successfully'})
        else:
            logger.error(f"Failed to process payment: {result.get('error')}")
            return create_response(500, {'error': 'Failed to process payment'})
            
    except Exception as e:
        logger.error(f"Error processing payment webhook: {str(e)}")
        import traceback
        traceback.print_exc()
        return create_response(500, {'error': 'Internal server error'})

def extract_squarespace_payment_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract payment data from SquareSpace webhook payload."""
    try:
        # This is a template - adjust based on actual SquareSpace webhook format
        # Common SquareSpace webhook fields (may vary):
        event_type = payload.get('eventType')
        order_data = payload.get('data', {})
        
        if event_type != 'order.create' and event_type != 'order.paid':
            logger.info(f"Ignoring webhook event type: {event_type}")
            return None
        
        # Extract customer and payment information
        customer_email = order_data.get('customerEmail')
        if not customer_email:
            # Try alternative field names
            customer_email = order_data.get('billingAddress', {}).get('email')
        
        # Extract amount - SquareSpace typically uses cents
        total_amount = order_data.get('grandTotal', {}).get('value', 0)
        if isinstance(total_amount, (int, float)):
            amount = Decimal(str(total_amount)) / 100  # Convert cents to dollars
        else:
            amount = Decimal(str(total_amount))
        
        # Extract transaction ID
        transaction_id = order_data.get('id') or order_data.get('orderNumber')
        
        # Extract custom fields if user provided email in checkout
        custom_fields = order_data.get('formSubmission', [])
        for field in custom_fields:
            if field.get('label', '').lower() in ['email', 'account email', 'user email']:
                customer_email = field.get('value') or customer_email
                break
        
        if not customer_email or not transaction_id or amount <= 0:
            logger.error(f"Missing required payment data - email: {customer_email}, transaction_id: {transaction_id}, amount: {amount}")
            return None
        
        return {
            'customer_email': customer_email.lower().strip(),
            'amount': float(amount),
            'transaction_id': str(transaction_id),
            'payment_method': order_data.get('paymentMethod', 'squarespace'),
            'order_data': order_data,
            'webhook_timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error extracting SquareSpace payment data: {str(e)}")
        return None

def process_payment_completion(payment_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process completed payment and add credits to user account."""
    try:
        from ..core.unified_s3_manager import UnifiedS3Manager
        
        # Import account management functions
        try:
            from dynamodb_schemas import add_to_balance, check_user_balance, get_domain_multiplier
            from shared.websocket_client import send_balance_update_to_user
        except ImportError:
            logger.error("Failed to import account management functions")
            return {'success': False, 'error': 'Account management not available'}
        
        email = payment_data['customer_email']
        amount = Decimal(str(payment_data['amount']))
        transaction_id = payment_data['transaction_id']
        
        # Check if this transaction was already processed
        if is_transaction_already_processed(transaction_id):
            logger.info(f"Transaction {transaction_id} already processed, skipping")
            return {'success': True, 'message': 'Transaction already processed'}
        
        # Add credits to user balance
        success = add_to_balance(
            email=email,
            amount=amount,
            transaction_type='store_purchase',
            description=f'Credits purchased via SquareSpace store',
            payment_id=transaction_id
        )
        
        if not success:
            logger.error(f"Failed to add balance for {email}")
            return {'success': False, 'error': 'Failed to add balance'}
        
        # Get updated balance
        new_balance = check_user_balance(email)
        
        # Send balance update via WebSocket if user is connected
        try:
            broadcast_balance_update_to_user(email, {
                'type': 'balance_update',
                'new_balance': float(new_balance) if new_balance else 0,
                'transaction': {
                    'amount': float(amount),
                    'description': 'Credits purchased via SquareSpace store',
                    'transaction_id': transaction_id,
                    'purchase_method': 'squarespace_store'
                },
                'message': f'✅ ${float(amount):.2f} credits added! New balance: ${float(new_balance):.4f}'
            })
        except Exception as e:
            logger.warning(f"Failed to send WebSocket balance update: {e}")
        
        # Send confirmation email
        try:
            send_credit_purchase_confirmation_email(payment_data, new_balance)
        except Exception as e:
            logger.warning(f"Failed to send confirmation email: {e}")
        
        # Mark transaction as processed
        mark_transaction_processed(transaction_id, payment_data)
        
        logger.info(f"Successfully added ${amount} credits to {email}, new balance: ${new_balance}")
        
        return {
            'success': True,
            'amount_added': float(amount),
            'new_balance': float(new_balance) if new_balance else 0,
            'transaction_id': transaction_id
        }
        
    except Exception as e:
        logger.error(f"Error processing payment completion: {str(e)}")
        return {'success': False, 'error': str(e)}

def is_transaction_already_processed(transaction_id: str) -> bool:
    """Check if transaction was already processed."""
    try:
        import boto3
        
        s3_client = boto3.client('s3')
        bucket_name = 'hyperplexity-storage'  # Use unified bucket
        key = f"payments/processed/{transaction_id}.json"
        
        try:
            s3_client.head_object(Bucket=bucket_name, Key=key)
            return True
        except s3_client.exceptions.NoSuchKey:
            return False
        except Exception as e:
            logger.warning(f"Error checking transaction status: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error in transaction check: {e}")
        return False

def mark_transaction_processed(transaction_id: str, payment_data: Dict[str, Any]):
    """Mark transaction as processed to prevent duplicates."""
    try:
        import boto3
        
        s3_client = boto3.client('s3')
        bucket_name = 'hyperplexity-storage'
        key = f"payments/processed/{transaction_id}.json"
        
        processed_data = {
            'transaction_id': transaction_id,
            'processed_at': datetime.now().isoformat(),
            'payment_data': payment_data
        }
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json.dumps(processed_data, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"Marked transaction {transaction_id} as processed")
        
    except Exception as e:
        logger.error(f"Failed to mark transaction as processed: {e}")

def broadcast_balance_update_to_user(email: str, balance_data: Dict[str, Any]):
    """Broadcast balance update to all WebSocket connections for a user."""
    try:
        import os
        import boto3
        
        # Get API Gateway Management client
        endpoint_url = os.environ.get('WEBSOCKET_API_URL')
        if not endpoint_url:
            logger.warning("WEBSOCKET_API_URL not configured, cannot send balance updates")
            return
        
        # Convert WebSocket URL to HTTPS endpoint for API Gateway Management
        if endpoint_url.startswith('wss://'):
            endpoint_url = endpoint_url.replace('wss://', 'https://')
        if not endpoint_url.endswith('/prod'):
            endpoint_url = endpoint_url.rstrip('/') + '/prod'
        
        api_client = boto3.client('apigatewaymanagementapi', endpoint_url=endpoint_url)
        
        # Get all WebSocket connections for this user
        # Note: In a real implementation, you'd need a way to map emails to connection IDs
        # For now, we'll try to find connections by scanning recent sessions
        try:
            from dynamodb_schemas import get_connections_for_user_email
            connection_ids = get_connections_for_user_email(email)
            
            if not connection_ids:
                logger.info(f"No WebSocket connections found for user {email}")
                return
            
            # Send balance update to all connections
            sent_count = 0
            for connection_id in connection_ids:
                try:
                    api_client.post_to_connection(
                        ConnectionId=connection_id,
                        Data=json.dumps(balance_data)
                    )
                    sent_count += 1
                    logger.info(f"Sent balance update to connection {connection_id}")
                except api_client.exceptions.GoneException:
                    logger.info(f"Stale connection {connection_id}, removing")
                    # Remove stale connection
                    from dynamodb_schemas import remove_websocket_connection
                    remove_websocket_connection(connection_id)
                except Exception as e:
                    logger.error(f"Failed to send to connection {connection_id}: {e}")
            
            logger.info(f"Balance update sent to {sent_count} connections for {email}")
            
        except ImportError:
            logger.warning("WebSocket connection functions not available")
        except Exception as e:
            logger.error(f"Error finding user connections: {e}")
            
    except Exception as e:
        logger.error(f"Error broadcasting balance update: {e}")

def send_credit_purchase_confirmation_email(payment_data: Dict[str, Any], new_balance: Decimal):
    """Send confirmation email for credit purchase."""
    try:
        from shared.email_sender import send_credit_confirmation_email
        
        # This function would need to be implemented in email_sender.py
        send_credit_confirmation_email(
            email_address=payment_data['customer_email'],
            amount_purchased=payment_data['amount'],
            new_balance=float(new_balance),
            transaction_id=payment_data['transaction_id']
        )
        
    except ImportError:
        logger.info("Credit confirmation email function not available")
    except Exception as e:
        logger.error(f"Error sending confirmation email: {e}")

def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create HTTP response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, X-Amz-Date, Authorization, X-Api-Key, X-Amz-Security-Token'
        },
        'body': json.dumps(body)
    }

def handle_webhook_request(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main handler for webhook requests."""
    try:
        # Handle CORS preflight requests
        if event.get('httpMethod') == 'OPTIONS':
            return create_response(200, {'message': 'CORS preflight'})
        
        # Only accept POST requests for webhooks
        if event.get('httpMethod') != 'POST':
            return create_response(405, {'error': 'Method not allowed'})
        
        # Process the webhook
        return handle_payment_webhook(event)
        
    except Exception as e:
        logger.error(f"Error in webhook handler: {str(e)}")
        return create_response(500, {'error': 'Internal server error'})